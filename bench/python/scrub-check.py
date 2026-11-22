#!/usr/bin/env python3
"""PII scrub verification for the bench/python/fixtures/emails corpus.

Automates the detectable scrub-checklist classes from bench/python/NOTES.md:
tracking pixels, email addresses, mailto links, data URIs, token-like query
parameters, and long random-looking identifier strings. It is a safety net,
not a substitute for the human read-through in the checklist — run it before
committing any email fixture; it must report PASS.

Usage: python bench/python/scrub-check.py [fixture ...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

EMAILS_DIR = Path(__file__).resolve().parent / "fixtures" / "emails"

# 1x1 (or sub-2px) images in any spelling: width/height attributes, CSS.
TRACKING_PIXEL_RES = (
    re.compile(r"<img\b[^>]*?\bwidth=[\"']?1[\"']?\b", re.IGNORECASE),
    re.compile(r"<img\b[^>]*?\bheight=[\"']?1[\"']?\b", re.IGNORECASE),
    re.compile(r"<img\b[^>]*?1px", re.IGNORECASE),
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAILTO_RE = re.compile(r"mailto:", re.IGNORECASE)
DATA_URI_RE = re.compile(r"data:[^\"'\s]{64,}", re.IGNORECASE)
# Token-like query parameters (tracking, sessions, signed identifiers).
TOKEN_PARAM_RE = re.compile(
    r"[?&](utm_[a-z_]+|token|sig|signature|session|sid|auth|key|apikey|api_key|"
    r"verification|code|unsubscribe[_-]?token|t)=",
    re.IGNORECASE,
)
# Long random-looking strings (hex/base64/base32 identifiers, >= 24 chars).
LONG_RANDOM_RE = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")
# message-id style values (they embed addresses/domains).
MESSAGE_ID_RE = re.compile(r"message-?id", re.IGNORECASE)


def check_fixture(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    for pattern in TRACKING_PIXEL_RES:
        if pattern.search(text):
            problems.append(f"possible tracking pixel ({pattern.pattern})")
    if EMAIL_RE.search(text):
        problems.append(f"email-address-like string ({EMAIL_RE.search(text).group(0)})")
    if MAILTO_RE.search(text):
        problems.append("mailto: link")
    if DATA_URI_RE.search(text):
        problems.append("long data: URI")
    if TOKEN_PARAM_RE.search(text):
        problems.append(f"token-like query parameter ({TOKEN_PARAM_RE.search(text).group(0)})")
    for match in LONG_RANDOM_RE.finditer(text):
        value = match.group(0)
        # Allow plain words that happen to be long (needs a digit to look random).
        if any(character.isdigit() for character in value) and not value.isdigit():
            problems.append(f"long identifier-like string ({value[:40]})")
            break
    if MESSAGE_ID_RE.search(text):
        problems.append("message-id header fragment")
    return problems


def main() -> int:
    paths = [Path(argument) for argument in sys.argv[1:]] or sorted(EMAILS_DIR.glob("*.html"))
    if not paths:
        print(f"scrub-check: no fixtures found under {EMAILS_DIR}", file=sys.stderr)
        return 1

    failed = False
    for path in paths:
        problems = check_fixture(path)
        if problems:
            failed = True
            print(f"FAIL {path}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"PASS {path}")

    if failed:
        print("scrub-check: FAIL — fix every flagged fixture before committing", file=sys.stderr)
        return 1
    print("scrub-check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
