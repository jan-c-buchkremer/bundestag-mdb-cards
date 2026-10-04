"""Each kind of fact has exactly one rendering component, in facts.py (docs/plan.md section 11, D13)."""

import ast
import re
from pathlib import Path

from research import facts

SRC = Path(__file__).parent.parent / "src" / "research"
# the markup that only a fact component writes: a speech row, a decision, a Drucksache row, a vote's bar and
# per-fraction table, and the functions that used to draw them elsewhere
MARKERS = {
    "speech": re.compile(r'class="sp[ "]'),
    "decision": re.compile(r'class="dec[ "]'),
    "drucksache": re.compile(r'class="row drs"'),
    "vote": re.compile(r'class="v-\{|<table class="plenum"><thead><tr><th>Fraktion</th><th>(Ja|Sitze)'),
}
OLD = {"count_bar", "hands_bar", "fraction_table_rc", "fraction_table_hands", "drs_links", "speech_row", "vote_row",
       "speeches_block", "decision_row", "counts_line", "positions_line"}  # fmt: skip


def test_fact_markup_is_written_by_facts_py_only():
    for path in SRC.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for fact, rx in MARKERS.items():
            if path.name != "facts.py":
                assert not rx.search(text), f"{path.name} renders a {fact} of its own"


def test_the_old_helpers_are_gone():
    for path in SRC.glob("*.py"):
        defined = {
            n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef)
        }
        assert not defined & OLD, f"{path.name} defines {defined & OLD}"


def test_no_script_renders_facts():
    """card.js shows the fact tabs facts.py wrote; search.js and pages.js render no speech, vote or Drucksache."""
    for name in ("card.js", "pages.js", "search.js", "index.html"):
        text = (SRC / name).read_text(encoding="utf-8")
        assert not re.search(r"reden/\$\{|abstimmungen/\$\{|Drucksache \$\{|class=\"sp\b", text), name


def test_one_component_per_fact():
    for name in ("speech", "speech_list", "vote", "decision", "decision_list", "drucksache", "drucksache_list"):
        assert callable(getattr(facts, name))
    d = {"id": "21/1/h1", "page": "21-1-h1", "kind": "handzeichen", "title": "Antrag", "result": "angenommen",
         "fractions": {"SPD": "yes"}, "house": {"SPD": 3}, "vorgaenge": ["g1"], "href": "vorgaenge/g1.html#abst-21-1-h1"}  # fmt: skip # noqa: E501
    assert 'href="../vorgaenge/g1.html#abst-21-1-h1"' in facts.decision(d)
    assert 'id="abst-21-1-h1"' in facts.decision(d, point=True) and "vorgaenge/g1" not in facts.decision(d, point=True)
