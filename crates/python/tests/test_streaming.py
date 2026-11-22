# Streaming parity: joining streamed chunks must equal the one-shot output.

import mdream

import pytest

from expected import CASES


CHUNK_SIZES = [1, 3, 7, 64, 4096]


def stream(html, options, size):
    s = mdream.MarkdownStream(options)
    out = []
    for i in range(0, len(html), size):
        out.append(s.process_chunk(html[i : i + size]))
    out.append(s.finish())
    return "".join(out)


@pytest.mark.parametrize(
    "name,html,options,expected_md,_fm",
    CASES,
    ids=[case[0] for case in CASES],
)
def test_stream_join_equals_one_shot(name, html, options, expected_md, _fm):
    one_shot = mdream.convert(html, options).markdown
    assert one_shot == expected_md
    for size in CHUNK_SIZES:
        assert stream(html, options, size) == one_shot, f"chunk size {size}"


def test_stream_split_deliberately_mid_tag():
    html = "<h2>Streamed heading</h2><p>Some <strong>bold</strong> words.</p>"
    one_shot = mdream.convert(html).markdown
    split = html.index("<h2>") + 1  # between '<' and 'h' of the opening tag
    assert "<" == html[split - 1] and "h" == html[split]
    s = mdream.MarkdownStream()
    out = s.process_chunk(html[:split]) + s.process_chunk(html[split:]) + s.finish()
    assert out == one_shot


def test_stream_split_inside_a_multibyte_entity():
    # '&eacute;' is the HTML entity for the two-byte character é; split
    # between '&' and 'eacute;' so the entity spans two chunks.
    html = "<p>caf&eacute; time</p>"
    one_shot = mdream.convert(html).markdown
    split = html.index("&eacute;") + 1
    s = mdream.MarkdownStream()
    out = s.process_chunk(html[:split]) + s.process_chunk(html[split:]) + s.finish()
    assert out == one_shot
    assert "café" in out


def test_stream_single_huge_chunk():
    html = "<p>" + ("word " * 50_000) + "</p>"
    one_shot = mdream.convert(html).markdown
    s = mdream.MarkdownStream()
    assert s.process_chunk(html) + s.finish() == one_shot


def test_stream_empty_and_unicode_only_chunks():
    for chunks in ([], [""], ["   "], ["\u00e9\u00fc\u4e2d\u6587"]):
        s = mdream.MarkdownStream()
        out = "".join(s.process_chunk(c) for c in chunks) + s.finish()
        assert isinstance(out, str)


def test_stream_take_data_frontmatter_and_extraction():
    html = (
        "<html><head><title>T</title></head><body>"
        "<h1>Heading</h1><p>Body text.</p></body></html>"
    )
    options = {
        "plugins": {"frontmatter": {}, "extraction": {"selectors": ["h1"]}}
    }
    s = mdream.MarkdownStream(options)
    s.process_chunk(html)
    s.finish()

    data = s.take_data()
    assert data["frontmatter"] == {"title": "T"}
    extracted = data["extracted"]
    assert extracted is not None and len(extracted) == 1
    assert extracted[0].tag_name == "h1"
    assert extracted[0].text_content == "Heading"

    # Extracted elements drain on call.
    assert s.take_data()["extracted"] is None


def test_stream_take_data_before_finish_is_partial():
    s = mdream.MarkdownStream({"plugins": {"frontmatter": {}}})
    s.process_chunk("<html><head><title>Half")
    data = s.take_data()
    assert data["extracted"] is None
    s.process_chunk("</title></head><body><p>x</p></body></html>")
    s.finish()
    assert s.take_data()["frontmatter"] == {"title": "Half"}


def test_stream_double_finish_and_chunk_after_finish_are_safe():
    html = "<p>a</p><p>b</p>"
    s = mdream.MarkdownStream()
    first = s.process_chunk(html) + s.finish()
    second = s.finish()
    assert second == ""
    after = s.process_chunk("<p>c</p>") + s.finish()
    assert first + after == mdream.convert(html + "<p>c</p>").markdown
