from typing import Any, Optional

__all__ = [
    "convert",
    "html_to_markdown",
    "html_to_text",
    "MarkdownStream",
    "MdreamResult",
    "ExtractedElement",
]


def html_to_markdown(html: str, options: Optional[dict[str, Any]] = ...) -> str: ...
def html_to_text(html: str, options: Optional[dict[str, Any]] = ...) -> str: ...
def convert(html: str, options: Optional[dict[str, Any]] = ...) -> MdreamResult: ...


class ExtractedElement:
    selector: str
    tag_name: str
    text_content: str
    attributes: dict[str, str]


class MdreamResult:
    markdown: str
    extracted: Optional[list[ExtractedElement]]
    frontmatter: Optional[dict[str, str]]
    truncated: bool


class MarkdownStream:
    def __init__(self, options: Optional[dict[str, Any]] = ...) -> None: ...
    def process_chunk(self, chunk: str) -> str: ...
    def finish(self) -> str: ...
    @property
    def truncated(self) -> bool: ...
    def take_data(self) -> dict[str, Any]: ...
