#!/usr/bin/env python3
"""mdream Python vs JS vs html2text benchmark comparison.

Compares three HTML-to-Markdown engines on the same corpora and reports
median/p95 wall-clock conversion time, output size, and output token count:

  1. mdream (Python) — the PyO3 binding from crates/python, one-shot
     ``mdream.convert(html)`` with default options. Requires the binding to
     be built and installed (``cd crates/python && maturin develop``).
  2. mdream (JS) — ``@mdream/js`` ``htmlToMarkdown()`` invoked through a
     warmed node subprocess (``bench/python/js-worker.mjs``). Like
     ``bench/cli-compare.sh`` treats non-JS runtimes, the worker process is
     started once and warmed up before measurement, so node startup is
     excluded; per-run time is measured inside the worker around the
     conversion call itself, excluding JSON/pipe overhead.
  3. html2text — the pip-installed upstream package, ``HTML2Text`` with
     ``body_width = 0`` (no hard wrapping), the closest equivalent feature
     configuration to mdream's unwrapped GFM output per the fair-comparison
     rules in ``bench/README.md``.

Corpora (real public web pages plus real emails, PII-scrubbed):

  - ``packages/mdream/test/fixtures/wikipedia-small.html``
  - ``packages/mdream/test/fixtures/github-markdown-complete.html``
  - ``packages/mdream/test/fixtures/wikipedia-largest.html``
  - ``bench/python/fixtures/emails/*.html`` — real HTML email bodies from the
    motivating linear-inbox case, committed only after PII scrubbing. The
    committed stand-ins and the scrub checklist live in
    ``bench/python/NOTES.md``; raw unscrubbed email HTML is never committed.

Token counting uses tiktoken with the ``cl100k_base`` encoding — the encoding
llm-cost's gpt-4 path resolves to — so the reported token counts approximate
the JS harness's llm-cost gpt-4 numbers (``bench/token-usage.ts``) and stay
comparable with existing bench reports. This is an approximation, not a
byte-identical port of the JS tokenizer.

Harness-only pip dependencies (``tiktoken``, ``html2text``) are never
dependencies of the mdream Python package, which stays dependency-free:

    pip install tiktoken html2text

Usage:

    python bench/python-compare.py [--runs N] [--warmup W]
        [--engines python,js,html2text] [--skip-missing] [--output PATH]

By default every engine must be available; use ``--skip-missing`` to run the
comparison with whichever engines are installed (missing ones are reported as
n/a). The Markdown report is printed to stdout and saved next to the run
artifacts under ``bench/python/results/``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JS_WORKER = Path(__file__).resolve().parent / "python" / "js-worker.mjs"
RESULTS_DIR = Path(__file__).resolve().parent / "python" / "results"
EMAILS_DIR = Path(__file__).resolve().parent / "python" / "fixtures" / "emails"

ENGINE_ORDER = ("python", "js", "html2text")
ENGINE_LABELS = {
    "python": "mdream (Python)",
    "js": "mdream (JS)",
    "html2text": "html2text",
}

WEB_FIXTURES = (
    ("wikipedia-small", REPO_ROOT / "packages/mdream/test/fixtures/wikipedia-small.html"),
    ("github-markdown-complete", REPO_ROOT / "packages/mdream/test/fixtures/github-markdown-complete.html"),
    ("wikipedia-largest", REPO_ROOT / "packages/mdream/test/fixtures/wikipedia-largest.html"),
)


class EngineError(RuntimeError):
    """Raised when an engine is requested but unavailable."""


def load_corpora() -> list[tuple[str, str]]:
    corpora: list[tuple[str, str]] = []
    for name, path in WEB_FIXTURES:
        if not path.is_file():
            raise EngineError(f"missing web fixture: {path}")
        corpora.append((name, path.read_text(encoding="utf-8")))
    for path in sorted(EMAILS_DIR.glob("*.html")):
        corpora.append((f"email-{path.stem}", path.read_text(encoding="utf-8")))
    if not corpora:
        raise EngineError("no corpora found")
    return corpora


# ── Engines ────────────────────────────────────────────────────────────────


def make_python_engine() -> "callable":
    try:
        import mdream
    except ImportError as exc:
        raise EngineError(
            "mdream Python binding not importable — build and install it first: "
            "cd crates/python && maturin develop (see crates/python/README.md)"
        ) from exc

    def convert(html: str) -> str:
        return mdream.convert(html).markdown

    return convert


class JsEngine:
    """Warmed node subprocess running @mdream/js htmlToMarkdown()."""

    def __init__(self) -> None:
        try:
            self._proc = subprocess.Popen(
                ["node", str(JS_WORKER)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise EngineError("node not found on PATH") from exc
        # Probe the worker with a tiny request; a failed import exits nonzero.
        probe = self._request("<h1>probe</h1>")
        if probe is None:
            self.close()
            raise EngineError(
                "@mdream/js worker failed to start — build the JS engine first: "
                "pnpm install && pnpm --filter @mdream/js build (repo root)"
            )

    def _request(self, html: str) -> dict | None:
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        try:
            self._proc.stdin.write(json.dumps({"html": html}) + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline()
        except (BrokenPipeError, ValueError):
            return None
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def convert(self, html: str) -> tuple[str, float]:
        """Return (markdown, elapsed_ms) — time measured inside the worker."""
        response = self._request(html)
        if response is None or "markdown" not in response:
            raise EngineError("mdream (JS) worker returned an invalid response")
        return response["markdown"], float(response.get("elapsedMs", 0.0))

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.stdin.close() if self._proc.stdin else None
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def make_html2text_engine() -> "callable":
    try:
        import html2text
    except ImportError as exc:
        raise EngineError("html2text not installed — pip install html2text") from exc

    handler = html2text.HTML2Text()
    # Closest equivalent feature configuration to mdream's unwrapped output
    # (fair-comparison rules in bench/README.md).
    handler.body_width = 0
    return handler.handle


def make_token_counter() -> "callable":
    try:
        import tiktoken
    except ImportError as exc:
        raise EngineError("tiktoken not installed — pip install tiktoken") from exc

    # cl100k_base is the encoding llm-cost's gpt-4 path resolves to; using it
    # here keeps the numbers comparable with the JS harness reports.
    encoding = tiktoken.get_encoding("cl100k_base")

    def count(text: str) -> int:
        return len(encoding.encode_ordinary(text))

    return count


# ── Measurement ────────────────────────────────────────────────────────────


def percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return float("nan")
    index = max(0, min(len(sorted_values) - 1, round(fraction * (len(sorted_values) - 1))))
    return sorted_values[index]


def format_ms(value: float) -> str:
    if value != value:  # NaN
        return "n/a"
    return f"{value:.1f}"


def format_chars(value: int) -> str:
    return f"{value / 1024:.1f} KB"


def run_comparison(engines: dict[str, object], corpora: list[tuple[str, str]], runs: int, warmup: int, count_tokens: "callable") -> dict:
    results: dict[tuple[str, str], dict] = {}
    js_engine = engines.get("js")
    for corpus_name, html in corpora:
        for engine_id, convert in engines.items():
            times: list[float] = []
            output = ""
            for _ in range(warmup):
                if engine_id == "js":
                    output, _elapsed = js_engine.convert(html)
                else:
                    convert(html)
            for _ in range(runs):
                if engine_id == "js":
                    output, elapsed_ms = js_engine.convert(html)
                    times.append(elapsed_ms)
                else:
                    start = time.perf_counter_ns()
                    output = convert(html)
                    times.append((time.perf_counter_ns() - start) / 1_000_000)
            sorted_times = sorted(times)
            results[(engine_id, corpus_name)] = {
                "median": statistics.median(sorted_times),
                "p95": percentile(sorted_times, 0.95),
                "chars": len(output),
                "tokens": count_tokens(output),
            }
            print(
                f"  {ENGINE_LABELS[engine_id]:<18} {corpus_name:<28}"
                f" median {format_ms(results[(engine_id, corpus_name)]['median']):>8} ms"
                f"  p95 {format_ms(results[(engine_id, corpus_name)]['p95']):>8} ms"
                f"  {format_chars(len(output)):>9}"
                f"  {results[(engine_id, corpus_name)]['tokens']:>7} tokens",
                flush=True,
            )
    return results


def build_report(engines: dict[str, object], missing: list[str], corpora: list[tuple[str, str]], results: dict, runs: int, warmup: int) -> str:
    available = [engine for engine in ENGINE_ORDER if engine in engines]
    labels = [ENGINE_LABELS[engine] for engine in available]
    corpus_names = [name for name, _html in corpora]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def matrix(formatter) -> list[str]:
        lines = ["| Engine | " + " | ".join(corpus_names) + " |", "| --- | " + " | ".join(["---"] * len(corpus_names)) + " |"]
        for engine in available:
            cells = [formatter(results[(engine, name)]) for name in corpus_names]
            lines.append(f"| {ENGINE_LABELS[engine]} | " + " | ".join(cells) + " |")
        return lines

    lines: list[str] = [
        "# mdream Python vs JS vs html2text — benchmark comparison",
        "",
        f"Generated: {stamp}",
        "",
        f"Runs: {runs} measured per engine per corpus, after {warmup} warmup run(s).",
        "",
        "Engines: " + ", ".join(labels) + ".",
    ]
    if missing:
        lines.append("")
        lines.append("Engines not available in this run (`--skip-missing`): " + ", ".join(f"`{ENGINE_LABELS[engine]}`" for engine in missing) + ".")
    lines += ["", "Corpora: " + ", ".join(corpus_names) + ".", ""]

    lines += ["## Median conversion time (ms)"] + matrix(lambda r: format_ms(r["median"])) + [""]
    lines += ["## p95 conversion time (ms)"] + matrix(lambda r: format_ms(r["p95"])) + [""]
    lines += ["## Output size"] + matrix(lambda r: format_chars(r["chars"])) + [""]
    lines += ["## Output tokens (tiktoken cl100k_base, approximating llm-cost gpt-4)"] + matrix(lambda r: str(r["tokens"])) + [""]

    lines += ["## Per-corpus detail", ""]
    for name, html in corpora:
        lines.append(f"### {name} ({format_chars(len(html))} HTML)")
        lines += ["", "| Engine | Median (ms) | p95 (ms) | Output | Tokens |", "| --- | --- | --- | --- | --- |"]
        for engine in available:
            r = results[(engine, name)]
            lines.append(
                f"| {ENGINE_LABELS[engine]} | {format_ms(r['median'])} | {format_ms(r['p95'])} | {format_chars(r['chars'])} | {r['tokens']} |"
            )
        lines.append("")

    lines += [
        "Token counts use tiktoken with the `cl100k_base` encoding (the encoding",
        "llm-cost's gpt-4 path resolves to), approximating the JS harness's",
        "llm-cost gpt-4 numbers so results stay comparable with existing bench",
        "reports. JS engine times are measured inside a warmed node worker around",
        "`htmlToMarkdown()` (node startup and JSON/pipe overhead excluded), the",
        "same warm-process treatment `bench/cli-compare.sh` gives non-JS runtimes.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=10, help="measured runs per engine per corpus (default 10)")
    parser.add_argument("--warmup", type=int, default=2, help="warmup runs excluded from timing (default 2)")
    parser.add_argument("--engines", default="python,js,html2text", help="comma-separated engines: python,js,html2text")
    parser.add_argument("--skip-missing", action="store_true", help="run with available engines instead of failing on a missing one")
    parser.add_argument("--output", type=Path, default=None, help="report path (default bench/python/results/python-compare-<timestamp>.md)")
    args = parser.parse_args()
    if args.runs < 1 or args.warmup < 0:
        parser.error("--runs must be >= 1 and --warmup must be >= 0")

    requested = [engine.strip() for engine in args.engines.split(",") if engine.strip()]
    unknown = [engine for engine in requested if engine not in ENGINE_ORDER]
    if unknown:
        parser.error(f"unknown engines: {unknown} (valid: {list(ENGINE_ORDER)})")

    try:
        count_tokens = make_token_counter()
        corpora = load_corpora()
    except EngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    engines: dict[str, object] = {}
    missing: list[str] = []
    factories = {"python": make_python_engine, "js": lambda: JsEngine(), "html2text": make_html2text_engine}
    js_engine: JsEngine | None = None
    for engine in requested:
        try:
            if engine == "js":
                js_engine = JsEngine()
                engines["js"] = js_engine
            else:
                engines[engine] = factories[engine]()
        except EngineError as exc:
            if args.skip_missing:
                print(f"note: skipping {ENGINE_LABELS[engine]} — {exc}", file=sys.stderr)
                missing.append(engine)
            else:
                if js_engine:
                    js_engine.close()
                print(f"error: {exc}", file=sys.stderr)
                return 1

    if not engines:
        print("error: no engines available", file=sys.stderr)
        return 1

    try:
        print(f"Benchmarking {len(engines)} engine(s) on {len(corpora)} corpora ({args.runs} runs, {args.warmup} warmup)...", flush=True)
        results = run_comparison(engines, corpora, args.runs, args.warmup, count_tokens)
        report = build_report(engines, missing, corpora, results, args.runs, args.warmup)
    finally:
        if js_engine:
            js_engine.close()

    print()
    print(report)

    output = args.output
    if output is None:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = RESULTS_DIR / f"python-compare-{stamp}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report + "\n", encoding="utf-8")
    print(f"Report saved to {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
