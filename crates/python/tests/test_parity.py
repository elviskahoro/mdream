# Pytest suite for the mdream Python bindings.
#
# Build and install the extension first:
#     maturin develop
# Run:
#     pytest crates/python/tests/

import mdream

import pytest

from expected import CASES


CASE_IDS = [case[0] for case in CASES]


@pytest.mark.parametrize(
    "name,html,options,expected_md,expected_fm",
    CASES,
    ids=CASE_IDS,
)
def test_one_shot_matches_core(name, html, options, expected_md, expected_fm):
    result = mdream.convert(html, options)
    assert result.markdown == expected_md
    if expected_fm is None:
        assert result.frontmatter in (None, {})
    else:
        assert result.frontmatter == expected_fm
    assert result.truncated is False


def test_html_to_markdown_matches_convert():
    for _name, html, options, expected_md, _fm in CASES:
        assert mdream.html_to_markdown(html, options) == expected_md


def test_html_to_text_omits_markdown_syntax():
    html = "<h1>Title</h1><p>Some <strong>bold</strong> text.</p>"
    text = mdream.html_to_text(html)
    assert text == mdream.convert(html, {"format": "text"}).markdown
    assert "Title" in text
    assert "bold" in text
    assert "#" not in text
    assert "**" not in text


def test_version_is_exposed():
    assert isinstance(mdream.__version__, str)
    assert mdream.__version__
