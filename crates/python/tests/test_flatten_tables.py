import mdream

LAYOUT = (
    "<table role='presentation'><tr><td><h1>Title</h1>"
    "<ul><li>one</li><li>two</li></ul>"
    "<table><tr><td>inner</td></tr></table></td></tr></table>"
)


def test_default_leaks_raw_html_from_nested_layout_tables():
    assert "<table" in mdream.html_to_markdown(LAYOUT)


def test_flatten_tables_yields_clean_markdown():
    out = mdream.html_to_markdown(LAYOUT, mdream.flatten_tables_options())
    assert "<" not in out
    assert "# Title" in out
    assert "- one" in out and "- two" in out
    assert "inner" in out


def test_flatten_tables_keeps_other_options():
    opts = mdream.flatten_tables_options({"origin": "https://example.com"})
    out = mdream.html_to_markdown("<table><tr><td><a href='/x'>l</a></td></tr></table>", opts)
    assert "https://example.com/x" in out


def test_flatten_tables_streaming_matches_one_shot():
    opts = mdream.flatten_tables_options()
    stream = mdream.MarkdownStream(opts)
    joined = "".join(stream.process_chunk(LAYOUT[i : i + 5]) for i in range(0, len(LAYOUT), 5))
    joined += stream.finish()
    assert joined == mdream.html_to_markdown(LAYOUT, opts)
