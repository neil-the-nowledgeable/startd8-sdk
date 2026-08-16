"""Route TODO entries through the SARIF sink (rung 1, producer #5, a partial) + the todo catalog.

Modules: src/startd8/validators/todo_rule_catalog.py, todo_sarif.py
"""

from __future__ import annotations

import pytest

from startd8.validators import todo_rule_catalog as cat
from startd8.validators.todo_scanner import TodoEntry
from startd8.validators.todo_sarif import render_todo_sarif


def _entry(security=False, line=7, raw="# TODO: x", cat_="B"):
    return TodoEntry(file_path="a.py", line=line, language="python", raw_text=raw,
                     category=cat_, context_lines="", containing_function="",
                     security_sensitive=security)


def _run0(doc):
    return doc["runs"][0]


# --- catalog ---
def test_catalog_validates_and_round_trips():
    assert cat.PRODUCER == "todo"
    assert set(cat.RULE_CATALOG) == {"todo_unresolved", "todo_security"}
    assert cat.qualified_id("todo_security") == "todo.todo_security"
    with pytest.raises(KeyError):
        cat.rule_severity("nope")


# --- adapter ---
def test_security_sensitive_todo_gets_the_security_rule():
    res = _run0(render_todo_sarif([_entry(security=True, raw="# TODO: fix auth")]))["results"][0]
    assert res["ruleId"] == "todo_security"
    assert res["level"] == "warning"                 # from the catalog (TodoEntry has no severity)
    assert res["message"]["text"] == "# TODO: fix auth"   # raw_text (TodoEntry has no message)
    assert res["locations"][0]["physicalLocation"]["region"]["startLine"] == 7


def test_plain_todo_gets_the_unresolved_rule_at_note_level():
    res = _run0(render_todo_sarif([_entry(security=False)]))["results"][0]
    assert res["ruleId"] == "todo_unresolved"
    assert res["level"] == "note"                    # info → note


def test_category_ABC_is_not_used_as_the_rule_id():
    rules = {r["id"] for r in _run0(render_todo_sarif([_entry(cat_="A"), _entry(cat_="C")]))["tool"]["driver"]["rules"]}
    assert rules == {"todo_unresolved"}              # not {"A", "C"}


def test_entry_without_file_is_skipped_and_counted():
    keep = _entry()
    nofile = TodoEntry(file_path="", line=1, language="python", raw_text="x", category="A",
                       context_lines="", containing_function="")
    run = _run0(render_todo_sarif([keep, nofile]))
    assert len(run["results"]) == 1
    assert run["invocations"][0]["properties"]["skipped"] == 1
