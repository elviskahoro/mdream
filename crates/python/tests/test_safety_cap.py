# max_node_bytes: the safety cap bounds output for adversarial input and is
# inert by default.

import mdream


OVERSIZED = "<p>" + ("x" * 100_000) + "</p>"


def test_one_shot_cap_reports_truncation_and_bounds_output():
    result = mdream.convert(OVERSIZED, {"max_node_bytes": 64})
    assert result.truncated is True
    assert len(result.markdown) <= 64


def test_one_shot_default_is_unlimited():
    result = mdream.convert(OVERSIZED)
    assert result.truncated is False
    assert len(result.markdown) >= 100_000


def test_stream_cap_reports_truncation_and_bounds_output():
    s = mdream.MarkdownStream({"max_node_bytes": 64})
    out = []
    for i in range(0, len(OVERSIZED), 1024):
        out.append(s.process_chunk(OVERSIZED[i : i + 1024]))
    out.append(s.finish())
    assert s.truncated is True
    assert len("".join(out)) <= 64


def test_stream_default_is_unlimited():
    html = "<p>" + ("y" * 50_000) + "</p>"
    s = mdream.MarkdownStream()
    out = s.process_chunk(html) + s.finish()
    assert s.truncated is False
    assert len(out) >= 50_000
