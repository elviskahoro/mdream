# Validation errors: unknown keys and invalid values raise ValueError, wrong
# types raise TypeError, Rust panics never cross the boundary.

import pytest

import mdream


def test_unknown_key_at_each_level():
    cases = [
        ({"nope": 1}, "Unknown option key 'nope'; valid keys are: clean, format, max_node_bytes, origin, plugins, wrap_width"),
        ({"clean": {"nope": True}}, "valid keys are: empty_images, empty_link_text, empty_links, fragments, redundant_links, self_link_headings, urls"),
        ({"plugins": {"nope": 1}}, "valid keys are: extraction, filter, frontmatter, isolate_main, tag_overrides, tailwind"),
        ({"plugins": {"filter": {"nope": 1}}}, "valid keys are: exclude, include, process_children"),
        ({"plugins": {"frontmatter": {"nope": 1}}}, "valid keys are: additional_fields, meta_fields"),
        ({"plugins": {"extraction": {"nope": 1}}}, "valid keys are: selectors"),
        ({"plugins": {"tag_overrides": {"x": {"nope": 1}}}}, "valid keys are: alias, collapses_inner_white_space, enter, exit, is_inline, is_self_closing, spacing"),
    ]
    for options, message_part in cases:
        with pytest.raises(ValueError, match="Unknown option key 'nope'"):
            mdream.convert("<p>x</p>", options)
        with pytest.raises(ValueError) as excinfo:
            mdream.convert("<p>x</p>", options)
        assert message_part in str(excinfo.value)


def test_bad_format_is_value_error():
    with pytest.raises(ValueError, match="Invalid format 'pdf'"):
        mdream.convert("<p>x</p>", {"format": "pdf"})


def test_negative_numbers_are_value_errors():
    with pytest.raises(ValueError, match="non-negative"):
        mdream.convert("<p>x</p>", {"wrap_width": -5})
    with pytest.raises(ValueError, match="non-negative"):
        mdream.convert("<p>x</p>", {"max_node_bytes": -1})


def test_wrong_input_types_are_type_errors():
    with pytest.raises(TypeError):
        mdream.html_to_markdown(123)
    with pytest.raises(TypeError):
        mdream.html_to_markdown("<p>x</p>", "not a dict")
    with pytest.raises(TypeError):
        mdream.convert("<p>x</p>", {"origin": 5})
    with pytest.raises(TypeError):
        mdream.convert("<p>x</p>", {"wrap_width": "80"})
    with pytest.raises(TypeError):
        mdream.convert("<p>x</p>", {"clean": "all"})
    with pytest.raises(TypeError):
        mdream.convert("<p>x</p>", {1: "x"})
    with pytest.raises(TypeError):
        mdream.MarkdownStream().process_chunk(123)


def test_tag_override_alias_unknown_name_is_value_error():
    options = {"plugins": {"tag_overrides": {"x": {"alias": "not-a-tag"}}}}
    with pytest.raises(ValueError, match="Unknown tag name 'not-a-tag'"):
        mdream.convert("<p>x</p>", options)


def test_camel_case_keys_are_rejected():
    with pytest.raises(ValueError, match="Unknown option key 'wrapWidth'"):
        mdream.convert("<p>x</p>", {"wrapWidth": 80})


@pytest.mark.parametrize("spacing", [[1], [1, 2, 3]])
def test_spacing_must_be_exactly_two_entries(spacing):
    options = {"plugins": {"tag_overrides": {"x": {"spacing": spacing}}}}
    with pytest.raises(ValueError, match="exactly two entries"):
        mdream.convert("<p>x</p>", options)
