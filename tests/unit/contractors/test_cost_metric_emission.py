"""REQ-CME: cost/usage metric emission from the Prime Contractor construction path.

Closes the gap documented in docs/design/OBSERVABILITY_COST_METRIC_EMISSION_GAP.md:
the contractor tracked cost into postmortem JSON but never drove the startd8.cost.*
OTel emitter, so cost/usage never reached Mimir.

FR-5 (runtime coverage): assert that a construction generation actually DRIVES the
emitter — not merely that the emitter module can emit — and that the emitted metric
stays in lockstep with the postmortem ``total_cost_usd`` accounting.
"""

from startd8.contractors.prime_contractor import (
    PrimeContractorWorkflow,
    _provider_from_model,
)
from startd8.contractors.protocols import GenerationResult


def _shell(tmp_path, cost_metrics):
    """A workflow shell without the heavy __init__ side effects."""
    wf = object.__new__(PrimeContractorWorkflow)
    wf.total_cost_usd = 0.0
    wf.total_input_tokens = 0
    wf.total_output_tokens = 0
    wf.project_root = tmp_path
    wf._cost_metrics = cost_metrics
    return wf


class _SpyMetrics:
    def __init__(self):
        self.records = []

    def record(self, rec):
        self.records.append(rec)


def test_accumulate_cost_drives_emitter_and_stays_in_lockstep(tmp_path):
    """FR-5 + FR-8: the chokepoint emits one startd8.cost.* record using the
    already-computed cost, and the postmortem totals advance identically."""
    spy = _SpyMetrics()
    wf = _shell(tmp_path, spy)

    result = GenerationResult(
        success=True,
        input_tokens=1500,
        output_tokens=500,
        cost_usd=0.042,
        model="anthropic:claude-sonnet-4-20250514",
    )
    wf._accumulate_cost(result)

    # Postmortem accounting advanced (FR-3: unchanged path).
    assert wf.total_cost_usd == 0.042
    assert wf.total_input_tokens == 1500
    assert wf.total_output_tokens == 500

    # The OTel emitter was actually driven (the gap this closes), exactly once.
    assert len(spy.records) == 1
    rec = spy.records[0]
    assert rec.total_cost == 0.042          # FR-8: no re-pricing
    assert rec.input_tokens == 1500
    assert rec.output_tokens == 500
    assert rec.model == "anthropic:claude-sonnet-4-20250514"
    assert rec.provider == "anthropic"       # FR-4: attribution
    assert rec.project == tmp_path.name


def test_accumulate_cost_noop_emitter_still_accounts(tmp_path):
    """When OTel is unconfigured (_cost_metrics is None), totals still advance
    and nothing raises (telemetry must never break a build)."""
    wf = _shell(tmp_path, None)
    result = GenerationResult(success=False, input_tokens=10, output_tokens=0, cost_usd=0.001)
    wf._accumulate_cost(result)  # must not raise
    assert wf.total_cost_usd == 0.001
    assert wf.total_input_tokens == 10


def test_emit_cost_metric_is_non_fatal(tmp_path):
    """A failure inside the emitter must not propagate (build-safety)."""
    class _Boom:
        def record(self, rec):
            raise RuntimeError("otel down")

    wf = _shell(tmp_path, _Boom())
    result = GenerationResult(success=True, cost_usd=0.01, input_tokens=5, output_tokens=5)
    wf._accumulate_cost(result)  # swallowed; totals still advance
    assert wf.total_cost_usd == 0.01


def test_provider_from_model():
    assert _provider_from_model("anthropic:claude-sonnet-4-20250514") == "anthropic"
    assert _provider_from_model("claude-sonnet-4-20250514") == "anthropic"
    assert _provider_from_model("gpt-4o") == "openai"
    assert _provider_from_model("gemini-3.1-pro") == "google"
    assert _provider_from_model("mock-model") == "mock"
    assert _provider_from_model("") == "unknown"
    assert _provider_from_model(None) == "unknown"
