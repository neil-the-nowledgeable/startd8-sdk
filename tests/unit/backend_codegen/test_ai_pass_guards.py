"""FR-B2/B3 (2b-i): declarative per-pass guards — grammar, guards.py validate_output, emission.

- Grammar: `guards:` block parses into a Guards (default-on when absent); bad on_violation rejected.
- guards.py v2: validate_output strips control chars, caps field length, rejects a verbatim
  untrusted-input dump (echo/exfil), honoring on_violation drop|reject|flag.
- Emission: untrusted-input passes get the capped fence (B2) + a post-call validate_output
  guarded by GuardViolation (B3); the request cap is threaded from guards.max_untrusted_chars.

See `docs/design/prompt-injection-prevention/REQUIREMENTS.md` FR-B2/B3.
"""

import ast

import pytest

from startd8.backend_codegen.ai_layer import (
    Guards,
    parse_ai_passes,
    render_ai_guards,
    render_ai_layer,
)

_BASE = """passes:
  - name: p
    output_entities: [X]
    route_path: /p
    prompt: pr
"""


def _guards_ns():
    ns = {}
    exec(compile(render_ai_guards(), "guards.py", "exec"), ns)
    return ns


# ---- grammar --------------------------------------------------------------

def test_guards_default_on_when_absent():
    g = parse_ai_passes(_BASE + "    input_entities: [X]")[0].guards
    assert g == Guards()  # default-on
    assert g.validate_output is True and g.max_untrusted_chars == 200_000 and g.on_violation == "reject"


def test_guards_explicit_block_parsed():
    m = _BASE + (
        "    input_entities: [X]\n"
        "    guards:\n"
        "      max_untrusted_chars: 8000\n"
        "      on_violation: flag\n"
        "      field_max: {body: 4000}\n"
    )
    g = parse_ai_passes(m)[0].guards
    assert g.max_untrusted_chars == 8000 and g.on_violation == "flag"
    assert g.field_max == (("body", 4000),)


def test_guards_bad_on_violation_rejected():
    with pytest.raises(ValueError):
        parse_ai_passes(_BASE + "    input_entities: [X]\n    guards:\n      on_violation: nuke")


def test_guards_unknown_key_rejected():
    with pytest.raises(ValueError):
        parse_ai_passes(_BASE + "    input_entities: [X]\n    guards:\n      bogus: 1")


# ---- guards.py v2 validate_output -----------------------------------------

def test_guards_version_bumped_and_exports():
    ns = _guards_ns()
    assert ns["__guards_version__"] == "2"
    assert "validate_output" in ns and "GuardViolation" in ns


def test_validate_output_strips_control_and_caps():
    ns = _guards_ns()
    r = type("E", (), {})()
    r.body = "hi\x00there" + "x" * 10
    ns["validate_output"](r, [], field_max={"body": 5}, on_violation="drop", pass_name="p")
    assert "\x00" not in r.body and len(r.body) <= 5


def test_validate_output_rejects_verbatim_dump():
    ns = _guards_ns()
    secret = "S" * 300  # >= min_verbatim_dump (200)
    r = type("E", (), {})()
    r.body = "prefix " + secret + " suffix"
    with pytest.raises(ns["GuardViolation"]):
        ns["validate_output"](r, [secret], on_violation="reject", pass_name="p")


def test_validate_output_flag_keeps_but_reports():
    ns = _guards_ns()
    secret = "Z" * 300
    r = type("E", (), {})()
    r.body = secret
    violations = ns["validate_output"](r, [secret], on_violation="flag", pass_name="p")
    assert violations and r.body == secret  # kept, but reported


# ---- emission -------------------------------------------------------------

_SCHEMA = """
model Note { id String @id  text String  sourceId String?  source String?  confirmed Boolean @default(false) }
"""
_SRC_BOUND = """passes:
  - name: suggest_note
    output_entities: [Note]
    route_path: /ai/suggest-note
    prompt: prompts/suggest_note.md
    request_field: text
    source_binding: sourceId
"""


def test_source_bound_emits_cap_and_validate():
    files = dict(render_ai_layer(_SCHEMA, _SRC_BOUND, None))
    src = files["app/ai/suggest_note.py"]
    ast.parse(src)
    assert "validate_output, GuardViolation" in src
    assert "fence_untrusted(text, 'text', 200000)" in src            # B2 cap threaded
    assert "validate_output(result, [text]" in src                    # B3 validate
    assert "except GuardViolation" in src                             # reject → not persisted


def test_all_emitted_python_parses():
    for path, src in dict(render_ai_layer(_SCHEMA, _SRC_BOUND, None)).items():
        if path.endswith(".py"):
            ast.parse(src)
