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
]
