"""Python bindings for mdream: HTML to Markdown conversion.

Re-exports the native extension surface from ``mdream._mdream``. No runtime
dependencies beyond the compiled extension.
"""

from mdream._mdream import (
    MarkdownStream,
    MdreamResult,
    ExtractedElement,
    convert,
    html_to_markdown,
    html_to_text,
)

_TABLE_TAGS = ("table", "thead", "tbody", "tfoot", "tr", "td", "th")


def flatten_tables_options(options=None):
    """Return ``options`` with HTML tables flattened into plain block content.

    Marketing and receipt emails are built from nested layout tables. Left as
    is, the converter renders the outer table as a Markdown table and dumps the
    inner HTML into one cell. This aliases every table tag to ``div`` so each
    cell becomes its own paragraph, headings and lists stay intact. Genuine
    data tables lose their grid, so use this for email, not for general pages.

    Works with ``html_to_markdown``, ``convert`` and ``MarkdownStream``::

        mdream.html_to_markdown(html, mdream.flatten_tables_options())
    """
    merged = dict(options or {})
    plugins = dict(merged.get("plugins") or {})
    overrides = dict(plugins.get("tag_overrides") or {})
    for tag in _TABLE_TAGS:
        overrides.setdefault(tag, {"alias": "div"})
    plugins["tag_overrides"] = overrides
    merged["plugins"] = plugins
    return merged


try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:  # pragma: no cover - Python < 3.8 not supported anyway
    version = None  # type: ignore[assignment]

if version is not None:
    try:
        __version__ = version("mdream")
    except PackageNotFoundError:  # pragma: no cover - not installed as a package
        __version__ = "0.0.0"
else:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = [
    "MarkdownStream",
    "MdreamResult",
    "ExtractedElement",
    "convert",
    "html_to_markdown",
    "html_to_text",
    "flatten_tables_options",
]
