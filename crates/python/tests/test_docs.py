# Review F1 guard: the README's documented option value shapes must match
# the shapes the binding enforces (options.rs), so a future docs/binding
# divergence fails tests instead of review. The README lands via the docs
# convoy; skipped when it is not present in this tree (on the merged tree it
# always exists).

import re
from pathlib import Path

import pytest

README = Path(__file__).resolve().parents[1] / "README.md"

pytestmark = pytest.mark.skipif(
    not README.is_file(), reason="crates/python/README.md not in this tree yet"
)


def _plugins_row(key):
    text = README.read_text(encoding="utf-8")
    plugins = text.split("### `plugins`", 1)
    assert len(plugins) == 2, "README has no `plugins` options section"
    match = re.search(rf"^\|\s*`{key}`\s*\|\s*`([^`]+)`\s*\|(.+)\|\s*$", plugins[1], re.MULTILINE)
    assert match, f"README plugins table has no row for {key!r}"
    return match.group(1), match.group(2).strip()


def test_isolate_main_and_tailwind_documented_as_bool():
    for key in ("isolate_main", "tailwind"):
        type_cell, description = _plugins_row(key)
        assert type_cell == "bool", f"{key} documented as {type_cell!r}, expected 'bool'"
        assert "True" in description, f"{key} description should say to pass True"


def test_additional_fields_documented_as_dict_of_strings():
    _type_cell, description = _plugins_row("frontmatter")
    assert "dict of" in description, (
        "additional_fields should be documented as a dict of string pairs, "
        f"got: {description}"
    )
    assert "{name: value}" in description
