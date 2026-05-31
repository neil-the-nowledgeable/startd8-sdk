"""RUN-007 Steps 2 + 4: empty-spec skeleton-suppression gate + escalation/refusal."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from startd8.micro_prime.prime_adapter import (
    MicroPrimeCodeGenerator,
    _FileProcessingState,
)


def _spec(file_path, elements):
    return SimpleNamespace(
        file=file_path, elements=elements, language=None,
        imports=[], metadata={}, bases=[],
    )


def _manifest(specs):
    return SimpleNamespace(file_specs=specs)


# ---------------------------------------------------------------------------
# Step 2 — the skeleton-emission gate in _generate_skeletons (FR-1/FR-7/FR-10)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEmptySpecGate:
    def test_empty_fillable_source_spec_is_suppressed_and_recorded(self):
        gen = MicroPrimeCodeGenerator()
        # CLASS-only spec → empty-fillable (the run-007 shape)
        m = _manifest({"lib/value-model.ts": _spec("lib/value-model.ts",
                                                   [{"kind": "class", "name": "value-model"}])})
        ctx = {}
        skeletons = gen._generate_skeletons(m, ["lib/value-model.ts"], ctx)
        assert "lib/value-model.ts" not in skeletons          # no stub emitted
        assert "lib/value-model.ts" in ctx.get("_empty_spec_files", set())

    def test_gate_clears_stale_skeleton_fill_context(self):
        gen = MicroPrimeCodeGenerator()
        m = _manifest({"lib/env.ts": _spec("lib/env.ts",
                                            [{"kind": "class", "name": "env"}])})
        ctx = {
            "skeleton_sources": {"lib/env.ts": "stale skeleton"},
            "element_tiers": {"lib/env.ts": {"tier": "SIMPLE", "source": "dfa_skeleton"}},
        }
        gen._generate_skeletons(m, ["lib/env.ts"], ctx)
        assert "lib/env.ts" not in ctx["skeleton_sources"]    # FR-10 cleanup
        assert "lib/env.ts" not in ctx["element_tiers"]

    def test_fillable_spec_is_not_suppressed(self):
        gen = MicroPrimeCodeGenerator()
        m = _manifest({"lib/db.ts": _spec("lib/db.ts",
                                           [{"kind": "function", "name": "getClient"}])})
        ctx = {}
        gen._generate_skeletons(m, ["lib/db.ts"], ctx)
        assert "lib/db.ts" not in ctx.get("_empty_spec_files", set())

    def test_registry_config_is_exempt(self):
        # next.config.mjs matches FRAMEWORK_CONFIG_DEFAULTS → never escalate (FR-7 tie-break)
        gen = MicroPrimeCodeGenerator()
        m = _manifest({"next.config.mjs": _spec("next.config.mjs", [])})
        ctx = {}
        gen._generate_skeletons(m, ["next.config.mjs"], ctx)
        assert "next.config.mjs" not in ctx.get("_empty_spec_files", set())

    def test_non_source_file_is_not_gated(self):
        # a .json/.yaml empty spec uses passthrough, not a stem-type stub
        gen = MicroPrimeCodeGenerator()
        m = _manifest({"data.json": _spec("data.json", [])})
        ctx = {}
        gen._generate_skeletons(m, ["data.json"], ctx)
        assert "data.json" not in ctx.get("_empty_spec_files", set())


# ---------------------------------------------------------------------------
# Step 4 — escalation outcome / refusal (FR-2.2/FR-9)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEmptySpecRefusal:
    def _gen(self):
        return MicroPrimeCodeGenerator()

    def test_unwritten_empty_spec_target_is_refused(self):
        gen = self._gen()
        st = _FileProcessingState()
        ctx = {"_empty_spec_files": {"lib/value-model.ts"}}
        # not in generated_files → fallback never produced it
        refused = gen._collect_empty_spec_refusals(st, ctx)
        assert refused == ["lib/value-model.ts"]

    def test_stub_output_is_refused(self, tmp_path):
        gen = self._gen()
        p = tmp_path / "value-model.ts"
        p.write_text("\nexport class value-model {\n\n}\n")  # escalation still produced a stub
        st = _FileProcessingState()
        st.generated_files = [p]
        ctx = {"_empty_spec_files": {"lib/value-model.ts"}}
        # match by endswith — generated path ends with the relative target
        assert gen._collect_empty_spec_refusals(st, {"_empty_spec_files": {"value-model.ts"}}) == ["value-model.ts"]

    def test_real_content_is_not_refused(self, tmp_path):
        gen = self._gen()
        p = tmp_path / "value-model.ts"
        p.write_text("import { z } from 'zod'\nexport const ValueModel = z.object({ name: z.string() })\n")
        st = _FileProcessingState()
        st.generated_files = [p]
        refused = gen._collect_empty_spec_refusals(st, {"_empty_spec_files": {"value-model.ts"}})
        assert refused == []

    def test_no_empty_spec_files_is_noop(self):
        gen = self._gen()
        st = _FileProcessingState()
        assert gen._collect_empty_spec_refusals(st, {}) == []

    def test_refusal_error_stamps_metadata_and_message(self):
        gen = self._gen()
        st = _FileProcessingState()
        st.empty_spec_refused = ["lib/value-model.ts"]
        meta = {}
        err = gen._empty_spec_refusal_error(st, meta)
        assert err is not None and "value-model.ts" in err and "MissingTemplateError" in err
        assert meta["refusal_root_cause"] == "empty_spec_refusal"
        assert meta["refusal_pipeline_stage"] == "micro_prime_escalation"
        assert meta["refused_targets"] == ["lib/value-model.ts"]

    def test_refusal_error_none_when_no_refusal(self):
        gen = self._gen()
        st = _FileProcessingState()
        meta = {}
        assert gen._empty_spec_refusal_error(st, meta) is None
        assert "refusal_root_cause" not in meta


# ---------------------------------------------------------------------------
# FR-4 — cost-budget guard (refuse-before-escalate when budget exhausted)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBudgetGuard:
    def _gen(self):
        return MicroPrimeCodeGenerator()

    def test_budget_remaining_parsing(self):
        gen = self._gen()
        assert gen._cost_budget_remaining(None) is None
        assert gen._cost_budget_remaining({}) is None
        assert gen._cost_budget_remaining({"_cost_budget_remaining_usd": None}) is None
        assert gen._cost_budget_remaining({"_cost_budget_remaining_usd": 1.5}) == 1.5
        assert gen._cost_budget_remaining({"_cost_budget_remaining_usd": "bad"}) is None

    def test_exhausted_budget_refuses_empty_spec_before_escalation(self):
        gen = self._gen()
        st = _FileProcessingState()
        st.bypass_files = ["lib/value-model.ts", "go.mod"]  # one empty-spec, one legit bypass
        ctx = {"_empty_spec_files": {"lib/value-model.ts"}, "_cost_budget_remaining_usd": 0.0}
        held = gen._apply_budget_refusal(st, ctx)
        assert held == ["lib/value-model.ts"]              # pulled from escalation
        assert st.bypass_files == ["go.mod"]               # legit bypass untouched

    def test_budget_available_does_not_refuse(self):
        gen = self._gen()
        st = _FileProcessingState()
        st.bypass_files = ["lib/value-model.ts"]
        ctx = {"_empty_spec_files": {"lib/value-model.ts"}, "_cost_budget_remaining_usd": 5.0}
        assert gen._apply_budget_refusal(st, ctx) == []
        assert st.bypass_files == ["lib/value-model.ts"]   # still escalates

    def test_no_budget_ceiling_does_not_refuse(self):
        gen = self._gen()
        st = _FileProcessingState()
        st.bypass_files = ["lib/value-model.ts"]
        ctx = {"_empty_spec_files": {"lib/value-model.ts"}}  # no _cost_budget_remaining_usd
        assert gen._apply_budget_refusal(st, ctx) == []
        assert st.bypass_files == ["lib/value-model.ts"]
