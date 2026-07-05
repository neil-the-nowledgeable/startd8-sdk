"""Tests for the Red Carpet Prescriptive Advisor (FR-RCA + CRP R1)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from startd8.kickoff_experience.red_carpet import (
    RedCarpetStage,
    RedCarpetState,
    build_red_carpet_state,
    reflection_text,
)
from startd8.kickoff_experience.red_carpet_advisor import (
    ADVISOR_COMMANDS,
    ADVISORY_KINDS,
    CMD_GENERATE_CONTRACT_PROMOTE,
    CMD_RED_CARPET_AGENT,
    CMD_SCREENS_SUGGEST,
    KIND_CASCADE_BLOCKER,
    KIND_INPUT_GAP,
    KIND_INPUT_INVALID,
    KIND_PROVENANCE_REVIEW,
    KIND_SCHEMA_SHAPE,
    KIND_STAKEHOLDER,
    Advisory,
    build_playbook,
    derive_advisories,
)


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────

def _state(*, schema=False, app=False, pages=False, views=False) -> RedCarpetState:
    """A minimal RedCarpetState with the given cascade gates satisfied."""
    gates = {"schema": schema, "app": app, "pages": pages, "views": views}
    unmet = tuple(k for k in ("schema", "app", "pages", "views") if not gates[k])
    stages = (
        RedCarpetStage("data_model", "done" if schema else "pending", ""),
        RedCarpetStage("manifests", "done" if (app and pages and views) else "pending", ""),
        RedCarpetStage("value_inputs", "pending", ""),
        RedCarpetStage("content", "pending", ""),
        RedCarpetStage("run", "done" if not unmet else "pending", ""),
    )
    return RedCarpetState(
        stages=stages, next_stage=None if not unmet else "data_model",
        cascade_offerable=not unmet, unmet_gates=unmet, readiness_score=None,
    )


def _assess(*, domains=None, cascade=None) -> dict:
    return {
        "kickoff_inputs": {"domains": domains or {}},
        "cascade": cascade if cascade is not None else {"status": "ok", "blockers": []},
    }


def _kinds(advs):
    return {a.kind for a in advs}


# ── FR-RCA-5: schema-shape ──────────────────────────────────────────────────────────────────────

def _write_schema(root: Path, text: str) -> None:
    (root / "prisma").mkdir(parents=True, exist_ok=True)
    (root / "prisma" / "schema.prisma").write_text(text, encoding="utf-8")


ONE_MODEL = "model A {\n id String @id\n name String\n}\n"
TWO_ISLANDS = ONE_MODEL + "model B {\n id String @id\n title String\n}\n"
TWO_LINKED = (
    "model A {\n id String @id\n name String\n bs B[]\n}\n"
    "model B {\n id String @id\n a A @relation(fields: [aId], references: [id])\n aId String\n}\n"
)


def test_single_entity_no_island_warn():
    from startd8.kickoff_experience.red_carpet_advisor import _schema_advisories
    advs = _schema_advisories(_state(schema=True), ONE_MODEL)
    assert not any("unlinked" in a.title for a in advs), "a relationless single-entity schema must not flag islands"


def test_many_islands_warn_names_count():
    from startd8.kickoff_experience.red_carpet_advisor import _schema_advisories
    advs = _schema_advisories(_state(schema=True), TWO_ISLANDS)
    islands = [a for a in advs if "unlinked" in a.title]
    assert len(islands) == 1
    assert islands[0].severity == "warn"
    assert "2 of 2" in islands[0].title
    assert islands[0].command == CMD_GENERATE_CONTRACT_PROMOTE


def test_linked_models_no_island_warn():
    from startd8.kickoff_experience.red_carpet_advisor import _schema_advisories
    advs = _schema_advisories(_state(schema=True), TWO_LINKED)
    assert not any("unlinked" in a.title for a in advs)


def test_unparseable_schema_never_raises_never_errors():
    # The lenient parser rarely raises; garbage typically yields 0 models (a `warn`, not a gate). Either
    # way: schema-shape kind, never `error` severity, no exception.
    from startd8.kickoff_experience.red_carpet_advisor import _schema_advisories
    advs = _schema_advisories(_state(schema=True), "this is not { valid prisma ][")
    assert advs and all(a.kind == KIND_SCHEMA_SHAPE for a in advs)
    assert all(a.severity != "error" for a in advs)  # never an error/gate


def test_parse_exception_degrades_to_info(monkeypatch):
    # Force parse_prisma_schema to raise → the except path yields a single bounded `info`, never raises.
    import startd8.kickoff_experience.red_carpet_advisor as adv

    def boom(_text):
        raise ValueError("kaboom")

    monkeypatch.setattr("startd8.languages.prisma_parser.parse_prisma_schema", boom)
    advs = adv._schema_advisories(_state(schema=True), ONE_MODEL)
    assert len(advs) == 1 and advs[0].kind == KIND_SCHEMA_SHAPE and advs[0].severity == "info"


def test_no_schema_when_gate_pending():
    from startd8.kickoff_experience.red_carpet_advisor import _schema_advisories
    advs = _schema_advisories(_state(schema=False), None)
    assert len(advs) == 1 and advs[0].title == "No data model yet"
    assert advs[0].command == CMD_RED_CARPET_AGENT


def test_zero_byte_schema_agrees_with_gate(tmp_path):
    # CRP R1-F5: a zero-byte schema.prisma → data_model stage pending AND "no schema yet" (not unparseable).
    _write_schema(tmp_path, "")
    st = build_red_carpet_state(tmp_path)
    dm = next(s for s in st.stages if s.key == "data_model")
    assert dm.status == "pending"
    schema_advs = [a for a in st.advisories if a.kind == KIND_SCHEMA_SHAPE]
    assert schema_advs and schema_advs[0].title == "No data model yet"


# ── FR-RCA-6: per-input diagnosis ─────────────────────────────────────────────────────────────────

def test_absent_input_is_gap_warn():
    advs = derive_advisories(".", _state(schema=True), _assess(domains={"conventions": {"status": "absent"}}), ONE_MODEL)
    gap = [a for a in advs if a.kind == KIND_INPUT_GAP]
    assert gap and gap[0].severity == "warn" and gap[0].command == CMD_RED_CARPET_AGENT


def test_invalid_input_is_error():
    advs = derive_advisories(
        ".", _state(schema=True),
        _assess(domains={"observability": {"status": "invalid", "error": "bad: yaml: here"}}), ONE_MODEL)
    inv = [a for a in advs if a.kind == KIND_INPUT_INVALID]
    assert inv and inv[0].severity == "error"
    assert "bad" in inv[0].detail


def test_defaulted_value_is_provenance_review():
    advs = derive_advisories(
        ".", _state(schema=True),
        _assess(domains={"business-targets": {"status": "present", "provenance_default": "estimate"}}), ONE_MODEL)
    rev = [a for a in advs if a.kind == KIND_PROVENANCE_REVIEW]
    assert rev and rev[0].severity == "info"


def test_present_confirmed_value_no_advisory():
    advs = derive_advisories(
        ".", _state(schema=True),
        _assess(domains={"conventions": {"status": "present", "provenance_default": "human"}}), ONE_MODEL)
    assert not any(a.kind in (KIND_INPUT_GAP, KIND_PROVENANCE_REVIEW) for a in advs)


# ── CRP R1-F1: stakeholders carve-out (never input-invalid) ───────────────────────────────────────

@pytest.mark.parametrize("roster,expect_kind", [
    ({"status": "invalid", "error": "roster broke"}, KIND_STAKEHOLDER),
    ({"status": "unavailable", "error": "panel pkg missing"}, KIND_STAKEHOLDER),
    ({"status": "present", "authored": True, "consumable": False, "note": "ships later"}, KIND_STAKEHOLDER),
])
def test_stakeholders_never_input_invalid(roster, expect_kind):
    advs = derive_advisories(".", _state(schema=True), _assess(domains={"stakeholders": roster}), ONE_MODEL)
    stake = [a for a in advs if a.kind == KIND_STAKEHOLDER]
    assert stake, f"expected a stakeholder advisory for {roster}"
    assert not any(a.kind == KIND_INPUT_INVALID for a in advs), "stakeholders must never be input-invalid"


def test_stakeholders_absent_no_advisory():
    advs = derive_advisories(".", _state(schema=True), _assess(domains={"stakeholders": {"status": "absent"}}), ONE_MODEL)
    assert not any(a.kind == KIND_STAKEHOLDER for a in advs)


def test_stakeholders_authored_consumable_no_advisory():
    advs = derive_advisories(
        ".", _state(schema=True),
        _assess(domains={"stakeholders": {"status": "present", "authored": True, "consumable": True}}), ONE_MODEL)
    assert not any(a.kind == KIND_STAKEHOLDER for a in advs)


# ── FR-RCA-7 + CRP R1-S2: cascade translation + inputs_error ──────────────────────────────────────

def test_cascade_blocker_translation():
    # FR-MS-8: the screens gap (pages/views) points at the Manifest Suggester, not the generic interview.
    cascade = {"status": "ok", "blockers": [
        {"section": "Pages & Nav", "status": "not_defined", "consequence": "no pages"}]}
    advs = derive_advisories(".", _state(schema=True), _assess(cascade=cascade), ONE_MODEL)
    cb = [a for a in advs if a.kind == KIND_CASCADE_BLOCKER]
    assert cb and cb[0].title == "Cascade blocker: Pages & Nav"
    assert cb[0].command == CMD_SCREENS_SUGGEST


def test_cascade_blocker_non_screens_stays_interview():
    # A non-screens manifest gap (app) is NOT a screens gap — stays the red-carpet interview (FR-MS-8 split).
    cascade = {"status": "ok", "blockers": [
        {"section": "App manifest", "status": "not_defined", "consequence": "no app.yaml"}]}
    advs = derive_advisories(".", _state(schema=True), _assess(cascade=cascade), ONE_MODEL)
    cb = [a for a in advs if a.kind == KIND_CASCADE_BLOCKER]
    assert cb and cb[0].command == CMD_RED_CARPET_AGENT


def test_inputs_error_one_bounded_advisory_no_keyerror():
    # CRP R1-S2: inputs_error has NO `blockers` key — must not KeyError, must emit exactly one advisory.
    cascade = {"status": "inputs_error", "error": "x" * 5000}
    advs = derive_advisories(".", _state(schema=True), _assess(cascade=cascade), ONE_MODEL)
    cb = [a for a in advs if a.kind == KIND_CASCADE_BLOCKER]
    assert len(cb) == 1 and cb[0].severity == "error"
    assert len(cb[0].detail) <= 201  # bounded


def test_cascade_blockers_same_consequence_collapse():
    # The "no contract → …" family fans out across sections; collapse to one (noise, not signal).
    cascade = {"status": "ok", "blockers": [
        {"section": "Entities & CRUD", "status": "x", "consequence": "no contract → no entities"},
        {"section": "Forms", "status": "x", "consequence": "no contract → no entities"},
        {"section": "Services", "status": "x", "consequence": "no contract → no entities"},
        {"section": "Pages & Nav", "status": "x", "consequence": "no pages"},
    ]}
    advs = derive_advisories(".", _state(schema=True), _assess(cascade=cascade), ONE_MODEL)
    cb = [a for a in advs if a.kind == KIND_CASCADE_BLOCKER]
    details = [a.detail for a in cb]
    assert details.count("no contract → no entities") == 1
    assert "no pages" in details


def test_dedupe_cascade_beats_input_gap_on_same_subject():
    # A cascade blocker and an input-gap on the same subject → cascade-blocker wins.
    cascade = {"status": "ok", "blockers": [{"section": "conventions", "status": "x", "consequence": "y"}]}
    advs = derive_advisories(
        ".", _state(schema=True),
        _assess(domains={"conventions": {"status": "absent"}}, cascade=cascade), ONE_MODEL)
    subjects = [a for a in advs if a.title.lower().endswith("conventions")]
    assert all(a.kind == KIND_CASCADE_BLOCKER for a in subjects)


# ── ordering / caps / coverage ────────────────────────────────────────────────────────────────────

def test_advisory_sort_is_byte_stable():
    a = _assess(domains={"conventions": {"status": "absent"}, "observability": {"status": "absent"}},
                cascade={"status": "ok", "blockers": [{"section": "Pages", "status": "s", "consequence": "c"}]})
    r1 = derive_advisories(".", _state(schema=True), a, TWO_ISLANDS)
    r2 = derive_advisories(".", _state(schema=True), a, TWO_ISLANDS)
    assert r1 == r2
    # severity-first: errors before warns before infos.
    ranks = [{"error": 0, "warn": 1, "info": 2}[a.severity] for a in r1]
    assert ranks == sorted(ranks)


def test_every_kind_is_producible():
    seen = set()
    scenarios = [
        (_state(schema=False), None, _assess()),                                            # schema-shape (no schema)
        (_state(schema=True), ONE_MODEL, _assess(domains={"conventions": {"status": "absent"}})),      # input-gap
        (_state(schema=True), ONE_MODEL, _assess(domains={"conventions": {"status": "invalid", "error": "e"}})),  # input-invalid
        (_state(schema=True), ONE_MODEL, _assess(cascade={"status": "ok", "blockers": [{"section": "P", "status": "s", "consequence": "c"}]})),  # cascade-blocker
        (_state(schema=True), ONE_MODEL, _assess(domains={"business-targets": {"status": "present", "provenance_default": "estimate"}})),  # provenance
        (_state(schema=True), ONE_MODEL, _assess(domains={"stakeholders": {"status": "invalid", "error": "e"}})),  # stakeholder
    ]
    for st, schema, a in scenarios:
        seen |= _kinds(derive_advisories(".", st, a, schema))
    assert seen == set(ADVISORY_KINDS)


def test_advisor_commands_are_startd8():
    assert all(c.startswith("startd8 ") for c in ADVISOR_COMMANDS)


# ── FR-RCA-8: playbook ────────────────────────────────────────────────────────────────────────────

def test_playbook_ranked_and_ordered():
    st = _state(schema=False)  # greenfield: all gates unmet
    steps = build_playbook(".", st, ())
    assert [s.rank for s in steps] == list(range(1, len(steps) + 1))
    assert steps[0].stage == "data_model" and steps[0].command == CMD_RED_CARPET_AGENT
    # cascade gates follow, in app → pages → views order
    manifest_steps = [s for s in steps if s.stage == "manifests"]
    assert [s.title for s in manifest_steps] == [
        "Add app manifest", "Add at least one page", "Add at least one view"]
    # FR-MS-8: the page/view (screens) gates point at the Manifest Suggester; the app manifest does not.
    by_title = {s.title: s.command for s in manifest_steps}
    assert by_title["Add app manifest"] == CMD_RED_CARPET_AGENT
    assert by_title["Add at least one page"] == CMD_SCREENS_SUGGEST
    assert by_title["Add at least one view"] == CMD_SCREENS_SUGGEST


def test_playbook_offerable_ends_with_wireframe_then_backend():
    st = _state(schema=True, app=True, pages=True, views=True)  # offerable
    steps = build_playbook(".", st, ())
    run = [s for s in steps if s.stage == "run"]
    assert [s.command for s in run][-2:] == ["startd8 wireframe", "startd8 generate backend"]


def test_playbook_cap():
    st = _state(schema=False)
    many = tuple(Advisory(KIND_INPUT_GAP, "warn", f"Value input missing: d{i}", "x", "y", CMD_RED_CARPET_AGENT)
                 for i in range(20))
    steps = build_playbook(".", st, many, cap=7)
    assert len(steps) == 7


# ── FR-RCA-4 / CRP R1-S1: single build_assess fetch + caps + to_dict ──────────────────────────────

def test_build_assess_called_exactly_once(tmp_path):
    import startd8.concierge.core as core
    real = core.build_assess
    calls = {"n": 0}

    def counting(root):
        calls["n"] += 1
        return real(root)

    with mock.patch.object(core, "build_assess", counting):
        build_red_carpet_state(tmp_path)
    assert calls["n"] == 1, "build_assess must be fetched exactly once per state build (greenfield)"


def test_build_assess_called_once_when_offerable(tmp_path):
    # Offerable path also fetches exactly once (preview reuses the single assess).
    import startd8.concierge.core as core
    real = core.build_assess
    calls = {"n": 0}

    def counting(root):
        calls["n"] += 1
        return real(root)

    with mock.patch.object(core, "build_assess", counting):
        build_red_carpet_state(tmp_path)  # non-offerable is fine; the count is what matters
    assert calls["n"] == 1


def test_to_dict_additive_keys_and_caps(tmp_path):
    d = build_red_carpet_state(tmp_path).to_dict()
    for k in ("advisories", "next_steps", "perf"):
        assert k in d
    assert len(d["advisories"]) <= 7 and len(d["next_steps"]) <= 7
    assert set(d["perf"]) == {"phase", "elapsed_ms", "budget_ms", "over_budget"}


def test_cascade_offerable_unchanged_by_advisor(tmp_path):
    # NR-2: the advisor never changes the offer predicate.
    st = build_red_carpet_state(tmp_path)
    assert st.cascade_offerable is False  # greenfield
    # The offer predicate is purely the gate set, independent of advisories/next_steps.
    assert st.unmet_gates == ("schema", "app", "pages", "views")


def test_perf_and_no_absolute_paths(tmp_path):
    # Bounded/leak-free (P4): no absolute host path leaks into advisory/next-step text.
    d = build_red_carpet_state(tmp_path).to_dict()
    blob = str(d["advisories"]) + str(d["next_steps"])
    assert str(tmp_path) not in blob


# ── FR-RCA-13: prescriptive reflection ────────────────────────────────────────────────────────────

def test_reflection_includes_insight_and_steps(tmp_path):
    st = build_red_carpet_state(tmp_path)
    text = reflection_text(st)
    assert "top insight" in text
    assert "next steps:" in text
    assert "startd8 " in text  # a command is cited


# ── FR-RCA-14: expanded schema diagnostics ────────────────────────────────────────────────────────

from startd8.kickoff_experience.red_carpet_advisor import _schema_advisories  # noqa: E402

WELL_FORMED = (
    "model User {\n id String @id\n name String\n posts Post[]\n}\n"
    "model Post {\n id String @id\n author User @relation(fields: [authorId], references: [id])\n"
    " authorId String\n}\n"
    "enum Role {\n ADMIN\n USER\n}\n"
)


def _codes(advs):
    return {a.code for a in advs}


def test_no_pk_warn():
    advs = _schema_advisories(_state(schema=True), "model A {\n name String\n}\n")
    assert any(a.code == "schema-shape:no-pk:a" and a.severity == "warn" for a in advs)


def test_likely_fk_warn_and_suppressed_when_relation_exists():
    # userId with no relation → warn
    a1 = _schema_advisories(_state(schema=True),
                            "model Order {\n id String @id\n userId String\n}\n"
                            "model User {\n id String @id\n}\n")
    assert any(a.code.startswith("schema-shape:likely-fk") for a in a1)
    # userId WITH a User relation → suppressed
    a2 = _schema_advisories(_state(schema=True),
                            "model Order {\n id String @id\n userId String\n"
                            " user User @relation(fields: [userId], references: [id])\n}\n"
                            "model User {\n id String @id\n}\n")
    assert not any(a.code.startswith("schema-shape:likely-fk") for a in a2)


def test_empty_enum_warn():
    advs = _schema_advisories(_state(schema=True), "model A {\n id String @id\n}\nenum E {\n}\n")
    assert any(a.code == "schema-shape:empty-enum:e" and a.severity == "warn" for a in advs)


def test_wellformed_schema_no_new_warns():
    advs = _schema_advisories(_state(schema=True), WELL_FORMED)
    bad = {c for c in _codes(advs) if c.startswith(("schema-shape:no-pk", "schema-shape:likely-fk", "schema-shape:empty-enum", "schema-shape:islands"))}
    assert not bad, f"a well-formed schema must raise none of these: {bad}"


# ── FR-RCA-17: versioning + stable code ───────────────────────────────────────────────────────────

def test_to_dict_has_schema_version(tmp_path):
    d = build_red_carpet_state(tmp_path).to_dict()
    assert d["schema_version"] == 1


def test_every_advisory_has_stable_nonempty_code(tmp_path):
    d1 = build_red_carpet_state(tmp_path).to_dict()
    d2 = build_red_carpet_state(tmp_path).to_dict()
    assert all(a["code"] for a in d1["advisories"])
    assert [a["code"] for a in d1["advisories"]] == [a["code"] for a in d2["advisories"]]  # byte-stable


def test_auto_derived_code():
    a = Advisory(KIND_INPUT_GAP, "warn", "Value input missing: conventions", "x", "y")
    assert a.code == "input-gap:conventions"


# ── FR-RCA-16: advisory telemetry (numeric-only) ──────────────────────────────────────────────────

def test_advice_telemetry_numeric_only(tmp_path):
    from startd8.kickoff_experience.red_carpet import record_red_carpet_progress
    from startd8.kickoff_experience.telemetry import (
        EV_RED_CARPET_ADVICE,
        WM2_EVENT_ATTR_ALLOWLIST,
        record_events,
    )
    st = build_red_carpet_state(tmp_path)
    with record_events() as evs:
        record_red_carpet_progress(None, st)
    advice = [e for e in evs if e.name == EV_RED_CARPET_ADVICE]
    assert len(advice) == 1
    attrs = advice[0].attributes
    assert set(attrs) <= WM2_EVENT_ATTR_ALLOWLIST         # allow-listed keys only
    assert all(isinstance(v, int) for v in attrs.values())  # numeric only — no text/paths
    assert attrs["n_advisories"] == len(st.advisories)


# ── FR-RCA-15: --check exit codes ─────────────────────────────────────────────────────────────────

def test_check_exit_zero_when_no_error(tmp_path):
    from typer.testing import CliRunner
    from startd8.cli_kickoff import kickoff_app
    res = CliRunner().invoke(kickoff_app, ["red-carpet", str(tmp_path), "--check"])
    assert res.exit_code == 0  # greenfield has only warn/info


def test_check_exit_one_on_error_advisory(tmp_path):
    from typer.testing import CliRunner
    from startd8.cli_kickoff import kickoff_app
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "conventions.yaml").write_text("this: : : not valid yaml", encoding="utf-8")
    res = CliRunner().invoke(kickoff_app, ["red-carpet", str(tmp_path), "--check"])
    assert res.exit_code == 1  # invalid input YAML → input-invalid error advisory


# ══ Batch 2 (FR-RCA-18..23) ═══════════════════════════════════════════════════════════════════════

# ── FR-RCA-18: specific value-input remediation ───────────────────────────────────────────────────

def test_absent_input_names_specific_fields():
    advs = derive_advisories(".", _state(schema=True),
                             _assess(domains={"conventions": {"status": "absent"}}), ONE_MODEL)
    gap = [a for a in advs if a.kind == KIND_INPUT_GAP][0]
    assert "fill:" in gap.action.lower()  # names specific fields, not just "author it"


def test_absent_input_degrades_without_config(monkeypatch):
    import startd8.kickoff_experience.red_carpet_advisor as adv
    adv._domain_fields.cache_clear()
    monkeypatch.setattr("startd8.kickoff_experience.manifest.default_config",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    advs = derive_advisories(".", _state(schema=True),
                             _assess(domains={"observability": {"status": "absent"}}), ONE_MODEL)
    gap = [a for a in advs if a.kind == KIND_INPUT_GAP]
    assert gap and "not authored yet" in gap[0].detail  # degrades, no raise
    adv._domain_fields.cache_clear()


# ── FR-RCA-19: reserve the headline schema slot ───────────────────────────────────────────────────

def test_cap_reserves_schema_slot():
    from startd8.kickoff_experience.red_carpet_advisor import cap_advisories
    warns = [Advisory(KIND_CASCADE_BLOCKER, "warn", f"Cascade blocker: S{i}", "d", "a") for i in range(10)]
    schema = Advisory(KIND_SCHEMA_SHAPE, "info", "No data model yet", "d", "a")
    capped = cap_advisories(tuple(warns + [schema]), 7)
    assert len(capped) == 7
    assert any(a.kind == KIND_SCHEMA_SHAPE for a in capped)  # headline never dropped


def test_greenfield_keeps_schema_shape_in_capped_set(tmp_path):
    advs = build_red_carpet_state(tmp_path).to_dict()["advisories"]
    assert any(a["kind"] == "schema-shape" for a in advs)


# ── FR-RCA-20: preview woven into run step ────────────────────────────────────────────────────────

def test_run_step_includes_preview():
    st = _state(schema=True, app=True, pages=True, views=True)  # offerable
    steps = build_playbook(".", st, (), preview={"shape": "modular-monolith", "counts": {"ready": 5}})
    run = [s for s in steps if s.title == "Run the $0 cascade"][0]
    assert "modular-monolith" in run.detail


# ── FR-RCA-21: proactive banner ───────────────────────────────────────────────────────────────────

def test_prescriptive_banner_has_insight_and_step(tmp_path):
    from startd8.kickoff_experience.red_carpet import prescriptive_banner
    st = build_red_carpet_state(tmp_path)
    banner = prescriptive_banner("WELCOME", st)
    assert "WELCOME" in banner
    assert "Top insight" in banner
    assert "Start here" in banner


# ── FR-RCA-22: --json summary header ──────────────────────────────────────────────────────────────

def test_summary_matches_severities(tmp_path):
    d = build_red_carpet_state(tmp_path).to_dict()
    advs = d["advisories"]
    assert d["summary"]["errors"] == sum(1 for a in advs if a["severity"] == "error")
    assert d["summary"]["warns"] == sum(1 for a in advs if a["severity"] == "warn")
    assert d["summary"]["infos"] == sum(1 for a in advs if a["severity"] == "info")
    assert d["summary"]["next_steps"] == len(d["next_steps"])


# ── FR-RCA-23: cross-surface parity ───────────────────────────────────────────────────────────────

def _without_perf(d):
    # `perf.elapsed_ms` is a live per-call measurement (legitimately volatile); parity is about the
    # derived logical content, so compare with the timing sample removed.
    return {k: v for k, v in d.items() if k != "perf"}


def test_cross_surface_parity(tmp_path):
    import pytest
    from startd8.kickoff_experience.chat import handle_kickoff_read

    canonical = _without_perf(build_red_carpet_state(tmp_path).to_dict())
    # chat read tool (handle_kickoff_read → build_red_carpet_state().to_dict())
    assert _without_perf(handle_kickoff_read("red_carpet_state", tmp_path)) == canonical
    # web /red-carpet.json route
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from startd8.kickoff_experience.web import build_kickoff_app
    client = TestClient(build_kickoff_app(tmp_path, chat_factory=None), headers={"host": "127.0.0.1:8000"})
    assert _without_perf(client.get("/red-carpet.json").json()) == canonical


# ── Command-resolution guard (regression for the stale `kickoff red-carpet --agent` bug) ─────────
# Every command the guided advisor emits MUST resolve in the post-M0 CLI registry. This is the guard
# that was missing when CMD_RED_CARPET_AGENT still pointed at the demoted `startd8 kickoff red-carpet`
# (moved to `kickoff-legacy`) with a bare `--agent` (which needs a `provider:model` arg).

def _resolve_in_registry(command: str) -> bool:
    """True if `command` (a `startd8 …` string) resolves to a registered Typer command."""
    from startd8.cli import app

    tokens = command.split()
    assert tokens[0] == "startd8"
    path = [t for t in tokens[1:] if not t.startswith("-")]  # subcommand path only, drop flags

    def _walk(typer_app, remaining):
        if not remaining:
            return True
        head, *tail = remaining
        for grp in typer_app.registered_groups:
            if grp.name == head:
                return _walk(grp.typer_instance, tail)
        for cmd in typer_app.registered_commands:
            if cmd.name == head and not tail:
                return True
        return False

    return _walk(app, path)


@pytest.mark.parametrize("command", ADVISOR_COMMANDS)
def test_every_advisor_command_resolves(command):
    assert _resolve_in_registry(command), f"{command!r} does not resolve in the CLI registry"


def test_red_carpet_command_is_the_resolvable_legacy_path():
    # Regression: the app/schema-gate command must be the resolvable `kickoff-legacy red-carpet`,
    # NOT the demoted `kickoff red-carpet` and NOT a bare `--agent` (which requires an argument).
    assert _resolve_in_registry(CMD_RED_CARPET_AGENT)
    assert "kickoff-legacy" in CMD_RED_CARPET_AGENT
    assert not CMD_RED_CARPET_AGENT.rstrip().endswith("--agent")
    assert not _resolve_in_registry("startd8 kickoff red-carpet")  # proves the trap is real
