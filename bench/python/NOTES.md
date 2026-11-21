# Python comparison harness notes

Support files for `bench/python-compare.py` (run from the repo root:

`python bench/python-compare.py`). See the script header for the engine

configuration and methodology; this file records the fair-comparison notes

specific to this harness and the PII-scrub checklist for the email corpus.

## Fair comparison configuration

- **mdream (Python)** — one-shot `mdream.convert(html)` with default options.

  Requires the binding built and installed (`cd crates/python && maturin develop`).

- **mdream (JS)** — `@mdream/js` `htmlToMarkdown()` via `js-worker.mjs`, a

  warmed node subprocess. The worker is started once, warmed up, and timed

  internally with `performance.now()` around the conversion call, so node

  startup and JSON/pipe overhead are excluded from the reported times.

- **html2text** — upstream pip package, `HTML2Text` with `body_width = 0`:

  html2text hard-wraps output at 78 columns by default, which is not a

  comparable feature configuration for unwrapped GFM markdown, so wrapping is

  disabled. This is the closest equivalent configuration per the

  fair-comparison rules in `bench/README.md`.

- **Tokens** — tiktoken `cl100k_base`, the encoding llm-cost's gpt-4 path

  resolves to, so numbers approximate the JS harness's `llm-cost` gpt-4

  counts (`bench/token-usage.ts`) and stay comparable with existing bench

  reports. Approximation, not a byte-identical port of the JS tokenizer.

Harness-only pip dependencies (`tiktoken`, `html2text`) are never

dependencies of the mdream Python package: `pip install tiktoken html2text`.

## Email corpus — PII scrub checklist

The email corpus exists because the motivating case (linear-inbox) is large

HTML email. Fixtures live in `bench/python/fixtures/emails/*.html` and MUST

be real HTML email bodies committed **only after PII scrubbing**. Raw

unscrubbed email HTML is never committed anywhere in this repository.

Before committing any email fixture, apply this checklist and then run

`python bench/python/scrub-check.py` (it must report PASS):

1. **Tracking pixels** — remove every 1x1 (or otherwise sized) tracking

   image and any `<img>` whose sole purpose is open tracking; remove

   tracking query parameters from remaining URLs.

2. **Names** — replace personal names (sender, recipient, references in

   prose) with generic placeholders such as `Example User`.

3. **Email addresses** — remove or genericize every address, `mailto:`

   link, and message-ID-like value.

4. **Physical addresses** — remove or genericize postal addresses.

5. **Tokens and identifiers** — remove auth tokens, verification codes,

   account numbers, order/reference numbers tied to a real account, session

   identifiers, and unsubscribe tokens.

6. **Account URLs** — replace user-specific URLs (profile, settings,

   order, thread links tied to a real account) with generic example URLs.

7. **Anything else identifying** — phone numbers, payment info (keep only

   generic amounts), organization-internal hostnames, avatars tied to a

   real account, and any other identifier not covered above.

8. **Re-verify** — run `python bench/python/scrub-check.py`, read the full

   fixture top to bottom once more, and only then commit.

### Current fixture provenance

The fixtures currently committed under `fixtures/emails/` are clearly-labeled

**synthetic stand-ins** built from the shapes that dominate the

linear-inbox case (newsletter, transactional receipt, notification). They

exercise the email corpus leg of the harness end to end. The real raw emails

are human-held and were not available to the implementing agent; replacing

the stand-ins with real PII-scrubbed bodies (following the checklist above)

is the documented follow-up work item.
