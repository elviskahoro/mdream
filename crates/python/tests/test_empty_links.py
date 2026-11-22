import mdream

import pytest


@pytest.mark.parametrize(
    "html",
    [
        '<a href="u"></a>',
        '<a href="u"> </a>',
        '<a href="u"><span></span></a>',
        '<a href="u"><b></b></a>',
    ],
)
def test_empty_links_are_dropped_by_default(html):
    assert "[](u)" not in mdream.convert(f"<p>a {html} b</p>").markdown


def test_links_with_content_are_kept():
    assert mdream.convert('<a href="u">x</a>').markdown == "[x](u)"
    assert mdream.convert('<a href="u"><img src="i.png" alt="x"></a>').markdown == "[![x](i.png)](u)"


def test_empty_link_text_can_be_opted_out():
    opts = {"clean": {"empty_link_text": False}}
    assert "[](u)" in mdream.convert('<a href="u"></a>', opts).markdown
    assert "[](u)" in mdream.convert('<a href="u"></a>', {"clean": None}).markdown


def test_other_clean_rules_keep_the_default():
    opts = {"clean": {"urls": True}}
    assert "[](u)" not in mdream.convert('<p>a <a href="u"></a></p>', opts).markdown
