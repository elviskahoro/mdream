# mdream (Python)

Python bindings for [mdream](../core/README.md) — a [PyO3](https://github.com/PyO3/pyo3) wrapper
around the Rust `mdream` core engine. Converts HTML to GitHub Flavored Markdown
with frontmatter, lists, tables, and code blocks, through one-shot and streaming
APIs. The GIL is released for the whole conversion, so Python code keeps running
while large documents convert.

- Requires CPython 3.10+ (a single `abi3` wheel per platform covers every supported CPython)
- No runtime Python dependencies
- MIT licensed, matching the workspace

## Install

From PyPI, once the first wheels are published (distribution name `mdream`,
import name `mdream`):

```sh
pip install mdream
```

From source with [maturin](https://www.maturin.rs/):

```sh
pip install maturin
maturin develop        # build and install into the active virtualenv
# or build a wheel:
maturin build --release
```

## Quickstart

```python
import mdream

md = mdream.html_to_markdown("<h1>Hello</h1><p>World</p>")
# "# Hello\n\nWorld"

# Rich result: markdown plus frontmatter, extracted elements, and the
# truncation flag. Pass options as a plain dict (snake_case keys).
result = mdream.convert(
    html,
    {
        "origin": "https://example.com",
        "plugins": {"frontmatter": {}},
    },
)
result.markdown      # str — the Markdown output
result.frontmatter   # dict[str, str] | None — extracted <head> metadata
result.extracted     # list[ExtractedElement] | None — extraction plugin matches
result.truncated     # bool — True if max_node_bytes dropped content

# Plain text output
text = mdream.html_to_text(html)
```

`mdream.__version__` reports the package version (kept in lockstep with the
workspace crate version).

## Streaming

`MarkdownStream` converts HTML incrementally: feed chunks as they arrive and
collect the Markdown as it is produced. Joining the chunk outputs always equals
the one-shot conversion of the same input, even when a chunk boundary splits
HTML mid-tag.

```python
from mdream import MarkdownStream

stream = MarkdownStream()

for chunk in chunks:                # e.g. a network response body
    md_part = stream.process_chunk(chunk)
    write(md_part)                  # Markdown as it becomes ready

tail = stream.finish()              # flush remaining output
write(tail)

stream.truncated                    # bool — True if max_node_bytes fired
data = stream.take_data()           # {"extracted": [...], "frontmatter": {...}}
```

`take_data()` returns the elements collected by the extraction plugin and the
frontmatter extracted so far; `extracted` drains on call and is complete after
`finish()`. The GIL is released around each chunk's conversion work.

## Options

Options are plain dicts with `snake_case` keys (a deliberate divergence from the
JS engines' `camelCase`). Every key is validated: an unknown key at any level
raises `ValueError` naming the key, a bad `format` or negative `wrap_width`
raises `ValueError`, and wrong value types raise `TypeError`.

Top-level keys (all optional):

| Key             | Type  | Default     | Description |
| --------------- | ----- | ----------- | ----------- |
| `origin`        | `str` | — | Base URL used to resolve relative links and image sources. |
| `clean`         | `dict` | — | Post-processing cleanup rules (see below). |
| `plugins`       | `dict` | — | Plugin configuration (see below). |
| `wrap_width`    | `int` | `0` | Hard-wrap prose at this many characters, breaking on word boundaries. `0` disables wrapping. Code, tables, and headings are never wrapped. |
| `format`        | `str` | `"markdown"` | Output format: `"markdown"`, `"text"`, or `"html"`. |
| `max_node_bytes`| `int` | `0` | Safety cap in bytes on what one construct may buffer — a text node, a tag, an open code block or inline code span, a table row's columns, or extraction script text. `0` (the default) is unlimited; content past the cap is **dropped**, bounding memory on adversarial input. Useful when streaming untrusted email. `truncated` in the result (or `MarkdownStream.truncated`) reports whether it fired. |

### `clean`

All flags are `bool`, `false` by default:

| Key                  | Description |
| -------------------- | ----------- |
| `urls`               | Strip tracking query parameters from URLs (`utm_*`, `fbclid`, `gclid`, …). |
| `fragments`          | Strip fragment-only links that don't match any heading slug. |
| `empty_links`        | Strip links with meaningless or executable hrefs to plain text. |
| `redundant_links`    | Strip links where the text equals the URL: `[https://x.com](https://x.com)` → `https://x.com`. |
| `self_link_headings` | Strip self-referencing heading anchors: `## [Title](#title)` → `## Title`. |
| `empty_images`       | Strip images with no alt text: `![](url)` → nothing. |
| `empty_link_text`    | Drop links that produce no visible text: `[](url)` → nothing. |

### `plugins`

| Key             | Type | Description |
| --------------- | ---- | ----------- |
| `filter`        | `dict` | Filter content by CSS selector: `include` (list of selectors to keep, dropping everything else), `exclude` (list of selectors to remove), `process_children` (`bool` — when `true`, children of an excluded element are still processed). |
| `isolate_main`  | `dict` | Restrict output to the page's `<main>` element. Pass `{}` to enable. |
| `frontmatter`   | `dict` | Extract `<head>` metadata into YAML frontmatter: `additional_fields` (list of `[key, value]` pairs appended to the frontmatter; reserved keys such as `title` are ignored), `meta_fields` (list of extra `<meta name="...">` keys to extract beyond the defaults). |
| `tailwind`      | `dict` | Convert Tailwind utility classes to semantic Markdown. Pass `{}` to enable. |
| `extraction`    | `dict` | `selectors` (list of CSS selectors); matched elements are collected into the result's `extracted` / `take_data()["extracted"]`. |
| `tag_overrides` | `dict` | Per-tag rendering overrides keyed by lowercase tag name (see below). |

#### `tag_overrides`

Each value is a `dict` with any of:

| Key                          | Type | Description |
| ---------------------------- | ---- | ----------- |
| `enter`                      | `str` | String emitted when entering the tag, replacing its default opening Markdown. |
| `exit`                       | `str` | String emitted when exiting the tag, replacing its default closing Markdown. |
| `spacing`                    | `[int, int]` | Blank lines `[before, after]` around the tag's output. `[0, 0]` keeps it inline. |
| `is_inline`                  | `bool` | Treat the tag as inline (`true`) or block (`false`). |
| `is_self_closing`            | `bool` | Treat the tag as void/self-closing (like `<br>`). |
| `collapses_inner_white_space`| `bool` | Collapse runs of whitespace inside the tag to a single space. |
| `alias`                      | `str` | Name of a built-in tag to render exactly like (e.g. `"em"`). Unknown tag names raise `ValueError`. |

```python
mdream.html_to_markdown(
    html,
    {"plugins": {"tag_overrides": {"sup": {"enter": "^", "exit": "^", "is_inline": True}}}},
)
```

## Platform support

Prebuilt `abi3` wheels (CPython 3.10+) are published for:

- macOS (arm64)
- Linux (x86_64)

Everything else builds from the sdist with a Rust toolchain and maturin.

## Known limitations

- **Free-threaded CPython**: `abi3` wheels are incompatible with free-threaded
  CPython 3.13t/3.14t. If you need free-threaded Python, a separate `cp3xxt`
  wheel would be required; build from the sdist in the meantime.
- **Panic safety**: Rust panics are caught and re-raised as Python
  `RuntimeError` (`mdream internal error: ...`) rather than crashing the
  interpreter. That path is implemented but not deterministically triggerable
  from pure Python, so it is an accepted, documented gap — no test asserts it
  end-to-end.
- **No `html2text` compatibility layer**: the package ships a clean native API
  (one-shot + streaming). `html2text` remains a benchmark baseline only.

## API surface

| Symbol | Kind | Description |
| ------ | ---- | ----------- |
| `mdream.html_to_markdown(html, options=None)` | function | One-shot conversion → Markdown `str`. |
| `mdream.convert(html, options=None)` | function | One-shot conversion → `MdreamResult`. |
| `mdream.html_to_text(html, options=None)` | function | One-shot conversion → plain-text `str`. |
| `mdream.MarkdownStream(options=None)` | class | Streaming converter: `process_chunk(chunk)`, `finish()`, `truncated`, `take_data()`. |
| `mdream.MdreamResult` | type | `markdown`, `extracted`, `frontmatter`, `truncated`. |
| `mdream.ExtractedElement` | type | `selector`, `tag_name`, `text_content`, `attributes`. |
| `mdream.__version__` | `str` | Package version, in lockstep with the workspace crate. |

The native extension lives in `mdream._mdream`; the `mdream` package re-exports
the public API above, ships inline `.pyi` stubs, and is marked typed
(`py.typed`).
