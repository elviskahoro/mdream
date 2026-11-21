"""Committed expected outputs for the pytest parity suite.

Generated once by running the mdream core crate directly (through the
generator in crates/python/src/tests.rs); regenerate alongside core
output changes, like the cross-engine parity fixtures.

Provenance:
- mdream core commit: 59245077
- generator: crates/python/src/tests.rs `generate_expected` (ignored test)

Regenerate with:
    cargo test -p mdream-python --lib generate_expected -- --ignored --nocapture

Each case: (name, html, options, expected_markdown, expected_frontmatter).
"""

CASES = [
    ('headings', '<h1>Title</h1><h2>Section</h2><h3>Sub</h3><h4>Deep</h4><h5>Deeper</h5><h6>Deepest</h6>', None, '# Title\n\n## Section\n\n### Sub\n\n#### Deep\n\n##### Deeper\n\n###### Deepest', None),
    ('emphasis', '<p>Some <strong>bold</strong>, <em>italic</em>, <del>struck</del>, and <code>inline code</code> text.</p>', None, 'Some **bold**, *italic*, ~~struck~~, and `inline code` text.', None),
    ('links_images', '<p>See <a href="https://example.com/page">the guide</a> and <a href="/relative">a relative link</a>.</p><p><img src="/images/logo.png" alt="Logo" /></p>', {'origin': 'https://example.com/docs/'}, 'See [the guide](https://example.com/page) and [a relative link](https://example.com/relative).\n\n![Logo](https://example.com/images/logo.png)', None),
    ('nested_lists', '<ul><li>alpha</li><li>beta<ol><li>one</li><li>two<ul><li>deep</li></ul></li></ol></li><li>gamma</li></ul>', None, '- alpha\n- beta\n  1. one\n  2. two\n     - deep\n- gamma', None),
    ('table_alignment', '<table><tr><th align="left">L</th><th align="center">C</th><th align="right">R</th></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>', None, '| L | C | R |\n| :--- | :---: | ---: |\n| 1 | 2 | 3 |', None),
    ('table_colspan', '<table><tr><td colspan="2">wide</td></tr><tr><td>a</td><td>b</td></tr></table>', None, '| wide | |\n| --- | --- |\n| a | b |', None),
    ('code_blocks', '<pre><code class="language-rust">fn main() {\n    println!("hi");\n}</code></pre><p>after</p>', None, '```rust\nfn main() {\n    println!("hi");\n}\n```\n\nafter', None),
    ('frontmatter', '<html><head><title>Page Title</title><meta name="description" content="A test page"></head><body><h1>Body</h1><p>Text.</p></body></html>', {'plugins': {'frontmatter': {}}}, '---\ntitle: "Page Title"\nmeta:\n  description: "A test page"\n---\n\n# Body\n\nText.', {'title': 'Page Title', 'description': 'A test page'}),
]
