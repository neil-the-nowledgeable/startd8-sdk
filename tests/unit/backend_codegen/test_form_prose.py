"""Tests for the form Words layer (``form_prose.yaml`` → per-field help/placeholder + per-form intro).

Covers the E4 acceptance criteria (SDK_FORM_HELP_INPUT_REQUIREMENTS.md §6):
1. help + placeholder + intro render into the form; help is wired as aria-describedby (FR-FH-1/2/7).
2. absent ⇒ byte-identical forms; present ⇒ only additive fragments (FR-FH-4).
3. editing a help string never changes the owned ``form.html`` (FR-FH-3, SOTTO).
4. an unknown ``Entity.field`` target is a loud, sourced error (FR-FH-5).
5. the capability is schema-driven — a second project's form_prose renders through the same code.
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen.drift import is_owned_generated_file, owned_file_in_sync
from startd8.backend_codegen.form_prose import (
    FormFieldProse,
    FormProse,
    parse_form_prose,
)
from startd8.backend_codegen.htmx_generator import render_ui

SCHEMA = """
model Bill {
  id Int @id @default(autoincrement())
  amountCents Int
  memo String
  paid Boolean @default(false)
}
model Chore {
  id Int @id @default(autoincrement())
  weekday Int
}
"""

FORM_PROSE = """
forms:
  Bill:
    intro: "Enter what the statement says."
    fields:
      amountCents: { help: "Amount in dollars, e.g. 42.00", placeholder: "42.00" }
      paid: { help: "Tick when settled." }
  Chore:
    fields:
      weekday: { help: "0 = Monday … 6 = Sunday." }
"""


def _ui(form_prose_text=None):
    return dict(render_ui(SCHEMA, "prisma/schema.prisma", form_prose_text=form_prose_text))


# --------------------------------------------------------------------------- parser


def test_parse_absent_is_empty():
    assert parse_form_prose(None) == {}
    assert parse_form_prose("") == {}
    assert parse_form_prose("forms: {}") == {}


def test_parse_happy_path():
    out = parse_form_prose(FORM_PROSE)
    assert set(out) == {"Bill", "Chore"}
    assert out["Bill"].intro == "Enter what the statement says."
    assert out["Bill"].fields["amountCents"] == FormFieldProse(
        help="Amount in dollars, e.g. 42.00", placeholder="42.00"
    )
    assert out["Bill"].fields["paid"] == FormFieldProse(help="Tick when settled.")
    assert out["Chore"].intro is None


def test_parse_inert_entry_dropped():
    # An entry with neither intro nor any field copy emits nothing (byte-identical output).
    assert parse_form_prose("forms:\n  Bill:\n    fields: {}\n") == {}


@pytest.mark.parametrize(
    "bad, msg",
    [
        ("forms:\n  Bill:\n    bogus: x\n", "unknown keys"),
        ("forms:\n  Bill:\n    intro: 5\n", "`intro` must be a string"),
        ("forms:\n  Bill:\n    fields:\n      amountCents: {nope: y}\n", "unknown keys"),
        ("forms:\n  Bill:\n    fields:\n      amountCents: {help: 7}\n", "`help` must be a string"),
        ("nope:\n  x: 1\n", "unknown top-level keys"),
        ("- a\n- b\n", "must be a mapping"),
    ],
)
def test_parse_loud_fail(bad, msg):
    with pytest.raises(ValueError) as exc:
        parse_form_prose(bad, known_entities=frozenset({"Bill"}),
                         known_fields={"Bill": frozenset({"amountCents"})})
    assert msg in str(exc.value)


def test_parse_unknown_entity_and_field():
    with pytest.raises(ValueError, match="unknown entity"):
        parse_form_prose("forms:\n  Ghost:\n    intro: x\n",
                         known_entities=frozenset({"Bill"}))
    with pytest.raises(ValueError, match="unknown form field"):
        parse_form_prose(
            "forms:\n  Bill:\n    fields:\n      ghost: {help: x}\n",
            known_entities=frozenset({"Bill"}),
            known_fields={"Bill": frozenset({"amountCents"})},
        )


# --------------------------------------------------------------------------- render (FR-FH-4)


def test_absent_is_byte_identical():
    assert _ui(None) == _ui()  # default arg path
    base = _ui()
    assert "form-intro" not in base["app/templates/bill/form.html"]
    # No help/intro fragments emitted when absent.
    assert not any(k.startswith("app/templates/bill/_form_intro") for k in base)
    assert not any("_help_" in k for k in base)


def test_present_only_adds_fragments_and_includes():
    base, rich = _ui(), _ui(FORM_PROSE)
    # Every non-form artifact is untouched (the strangler invariant: others(absent) == others(present)).
    def others(d):
        return {k: v for k, v in d.items() if not k.endswith("/form.html") and "_help_" not in k
                and not k.endswith("_form_intro.html")}
    assert others(base) == others(rich)


# --------------------------------------------------------------------------- render (FR-FH-1/2/7)


def test_help_placeholder_intro_and_aria():
    rich = _ui(FORM_PROSE)
    form = rich["app/templates/bill/form.html"]
    assert '{% include "bill/_form_intro.html" %}' in form
    assert 'placeholder="42.00"' in form
    assert 'aria-describedby="help-amountCents"' in form
    assert '{% include "bill/_help_amountCents.html" %}' in form
    # checkbox carries aria-describedby but never a placeholder (meaningless there).
    paid_input = form.split('id="f-paid"')[1].split(">")[0]
    assert "aria-describedby=" in paid_input and "placeholder=" not in paid_input
    # the help fragment is the escaped words, headerless.
    frag = rich["app/templates/bill/_help_amountCents.html"]
    assert frag == '<small id="help-amountCents" class="field-help">Amount in dollars, e.g. 42.00</small>\n'
    assert "GENERATED" not in frag
    # the intro fragment markdown-renders.
    assert rich["app/templates/bill/_form_intro.html"] == (
        '<div class="form-intro"><p>Enter what the statement says.</p></div>\n'
    )


def test_placeholder_only_field_has_no_help_fragment():
    rich = _ui("forms:\n  Bill:\n    fields:\n      memo: {placeholder: 'note'}\n")
    form = rich["app/templates/bill/form.html"]
    assert 'placeholder="note"' in form
    assert "aria-describedby=" not in form  # no help → no aria, no fragment
    assert not any("_help_" in k for k in rich)


def test_help_text_is_html_escaped():
    rich = _ui("forms:\n  Bill:\n    fields:\n      memo: {help: '<b>bold</b> & more'}\n")
    assert rich["app/templates/bill/_help_memo.html"] == (
        '<small id="help-memo" class="field-help">&lt;b&gt;bold&lt;/b&gt; &amp; more</small>\n'
    )


def test_placeholder_is_attribute_escaped():
    rich = _ui('forms:\n  Bill:\n    fields:\n      memo: {placeholder: \'say "hi"\'}\n')
    assert 'placeholder="say &quot;hi&quot;"' in rich["app/templates/bill/form.html"]


# --------------------------------------------------------------------------- SOTTO (FR-FH-3)


def test_editing_help_words_does_not_change_form_html():
    rich = _ui(FORM_PROSE)
    edited = _ui(FORM_PROSE.replace("Amount in dollars, e.g. 42.00", "Totally rewritten guidance"))
    # The owned template is unchanged — only the untracked fragment moves (the hash-exempt Words layer).
    assert edited["app/templates/bill/form.html"] == rich["app/templates/bill/form.html"]
    assert (
        edited["app/templates/bill/_help_amountCents.html"]
        != rich["app/templates/bill/_help_amountCents.html"]
    )


def test_fragments_are_not_owned_files():
    rich = _ui(FORM_PROSE)
    assert not is_owned_generated_file(rich["app/templates/bill/_help_amountCents.html"])
    assert not is_owned_generated_file(rich["app/templates/bill/_form_intro.html"])
    assert is_owned_generated_file(rich["app/templates/bill/form.html"])


# --------------------------------------------------------------------------- drift round-trip


def test_owned_form_in_sync_with_form_prose():
    # The generated form.html re-renders byte-identically under --check when form_prose is threaded.
    rich = _ui(FORM_PROSE)
    form = rich["app/templates/bill/form.html"]
    assert owned_file_in_sync(SCHEMA, form, form_prose_text=FORM_PROSE)


def test_owned_form_drifts_when_structure_added_without_regen():
    # form.html generated with NO prose, but the project later adds help → structural drift (correct).
    base_form = _ui()["app/templates/bill/form.html"]
    assert owned_file_in_sync(SCHEMA, base_form, form_prose_text=None)
    assert not owned_file_in_sync(SCHEMA, base_form, form_prose_text=FORM_PROSE)


def test_owned_form_stays_in_sync_when_only_help_words_edited():
    # form.html generated with prose; editing only the help WORDS keeps the owned file in-sync (SOTTO).
    rich_form = _ui(FORM_PROSE)["app/templates/bill/form.html"]
    edited_prose = FORM_PROSE.replace("Tick when settled.", "Mark once the bill is paid.")
    assert owned_file_in_sync(SCHEMA, rich_form, form_prose_text=edited_prose)


# --------------------------------------------------------------------------- project-agnostic (FR-FH-10)


def test_second_project_schema_renders_through_same_code():
    schema = "model Widget {\n  id Int @id @default(autoincrement())\n  sku String\n}\n"
    rich = dict(render_ui(schema, "prisma/schema.prisma",
                          form_prose_text="forms:\n  Widget:\n    fields:\n      sku: {help: 'Stock code.'}\n"))
    assert 'aria-describedby="help-sku"' in rich["app/templates/widget/form.html"]
    assert rich["app/templates/widget/_help_sku.html"].startswith('<small id="help-sku"')
