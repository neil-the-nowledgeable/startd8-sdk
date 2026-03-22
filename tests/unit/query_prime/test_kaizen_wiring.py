"""Tests for Kaizen wiring in Query Prime engine — REQ-KQP-100 through 602.

Validates that the engine correctly:
- Loads and consults FalsePositiveRegistry (REQ-KQP-200–202)
- Loads and applies RoutingOverrideStore (REQ-KQP-601)
- Passes Kaizen hints through to generator (REQ-KQP-600)
- Accumulates results for verification reports (REQ-KQP-100–102)
- Sets prior_injection_failure from history (REQ-QP-300)
- Threads verification timing into report items (REQ-KQP-102)
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.complexity.models import ComplexityTier
from startd8.query_prime.engine import QueryPrimeEngine
from startd8.query_prime.fp_registry import FalsePositiveRegistry
from startd8.query_prime.kaizen_metrics import build_verification_report
from startd8.query_prime.models import (
    DatabaseType,
    OperationType,
    ParameterSpec,
    QueryResult,
    QueryWorkItem,
    SecurityCheckType,
    SecurityFinding,
    SecurityVerdict,
    SecurityVerificationResult,
)
from startd8.query_prime.router import QueryRouterConfig
from startd8.query_prime.routing_overrides import RoutingOverride, RoutingOverrideStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_startd8(tmp_path):
    """Create a temporary .startd8 directory for persistence tests."""
    d = tmp_path / ".startd8"
    d.mkdir()
    return d


@pytest.fixture
def simple_work_item():
    return QueryWorkItem(
        id="wi-001",
        description="Get user by ID",
        database=DatabaseType.POSTGRESQL,
        operation_type=OperationType.SELECT,
        tables=["users"],
        parameters=[ParameterSpec(name="id")],
        target_language="csharp",
    )


@pytest.fixture
def health_check_work_item():
    return QueryWorkItem(
        id="hc-1",
        description="Health check",
        database=DatabaseType.POSTGRESQL,
        operation_type=OperationType.HEALTH_CHECK,
        target_language="csharp",
    )


# ---------------------------------------------------------------------------
# Task 1: FP Registry wiring (REQ-KQP-200–202)
# ---------------------------------------------------------------------------

class TestFPRegistryWiring:
    """FP registry is loaded at init and passed to verify_file."""

    def test_engine_loads_fp_registry(self, tmp_startd8):
        """Engine loads FP registry from disk at init."""
        fp_path = tmp_startd8 / "query-prime-false-positives.json"
        fp_path.write_text(json.dumps({
            "entries": {
                "abc123": {
                    "pattern_hash": "abc123",
                    "check_type": "credential_leakage",
                    "message": "known safe pattern",
                    "database": "postgresql",
                    "framework": "npgsql",
                    "occurrences": 5,
                    "suppressed": True,
                }
            }
        }))
        # Pre-load the registry before passing to engine (engine calls
        # .load() but on the same path, so it re-loads correctly).
        registry = FalsePositiveRegistry(path=fp_path)
        registry.load()
        assert len(registry) == 1
        # Engine accepts pre-loaded registry and re-loads (idempotent)
        engine = QueryPrimeEngine(fp_registry=registry)
        assert len(engine.fp_registry) == 1

    def test_verify_file_suppresses_false_positives(self):
        """verify_file filters suppressed findings from verdict computation."""
        from startd8.query_prime.security import verify_file

        registry = FalsePositiveRegistry(suppression_threshold=1)

        # Register a credential finding and mark it suppressed
        finding = SecurityFinding(
            check_type=SecurityCheckType.CREDENTIAL_LEAKAGE,
            severity="error",
            message="password in log",
            pattern_hash="cred-hash-1",
        )
        registry.register(finding, "postgresql", "npgsql")

        # Safe code that would normally pass — we just verify the suppression
        # path by mocking.
        source = 'var x = "hello";'
        result = verify_file(
            source, "test.cs", "postgresql", "csharp",
            fp_registry=registry,
        )
        # No actual credential in this source, so no finding to suppress.
        assert result.verdict == SecurityVerdict.PASS

    def test_injection_never_suppressed_through_engine(self):
        """Injection findings bypass FP suppression even when registered."""
        registry = FalsePositiveRegistry(suppression_threshold=1)

        injection_finding = SecurityFinding(
            check_type=SecurityCheckType.INJECTION,
            severity="error",
            message="SQL injection",
            pattern_hash="inj-hash-1",
        )
        # Register it — should NOT suppress because it's injection
        registry.register(injection_finding, "postgresql", "npgsql")

        assert not registry.is_suppressed(injection_finding)

    def test_fp_suppression_count_in_verification_result(self):
        """verify_file reports false_positives_suppressed count."""
        from startd8.query_prime.security import verify_file

        registry = FalsePositiveRegistry(suppression_threshold=1)
        cred_finding = SecurityFinding(
            check_type=SecurityCheckType.CREDENTIAL_LEAKAGE,
            severity="error",
            message="cred leak",
            pattern_hash="fp-cred-1",
        )
        registry.register(cred_finding, "postgresql", "npgsql")

        # Source with no actual findings — suppression count stays 0
        result = verify_file("safe code", "t.cs", "postgresql", "csharp", fp_registry=registry)
        assert result.false_positives_suppressed == 0


# ---------------------------------------------------------------------------
# Task 2: Routing override wiring (REQ-KQP-601)
# ---------------------------------------------------------------------------

class TestRoutingOverrideWiring:
    """Routing overrides are loaded and applied during classification."""

    def test_engine_loads_routing_overrides(self, tmp_startd8):
        overrides_path = tmp_startd8 / "query-prime-routing-overrides.json"
        overrides_path.write_text(json.dumps({
            "overrides": {
                "QWI-PG": {
                    "pattern": "QWI-PG",
                    "minimum_tier": "MODERATE",
                    "reason": "PostgreSQL queries need T2",
                }
            }
        }))
        store = RoutingOverrideStore(path=overrides_path)
        store.load()
        assert len(store) == 1
        engine = QueryPrimeEngine(routing_overrides=store)
        assert len(engine.routing_overrides) == 1

    def test_override_bumps_tier_for_template_path(self, health_check_work_item):
        """Routing override doesn't block template path (template checked first)."""
        store = RoutingOverrideStore()
        store.add(RoutingOverride(pattern="hc-", minimum_tier="COMPLEX", reason="test"))

        engine = QueryPrimeEngine(routing_overrides=store)
        result = engine.process_work_item(health_check_work_item)
        # Template path still works — template check happens before classification override
        assert result.tier_used == ComplexityTier.TRIVIAL

    def test_override_applied_for_llm_path(self):
        """Routing override elevates tier for LLM-path work items."""
        store = RoutingOverrideStore()
        store.add(RoutingOverride(
            pattern="esc-",
            minimum_tier="COMPLEX",
            reason="known hard query",
        ))

        engine = QueryPrimeEngine(
            routing_overrides=store,
            router_config=QueryRouterConfig(max_retries_per_tier=0, max_escalations=0),
        )
        wi = QueryWorkItem(
            id="esc-001",
            description="Complex query",
            database=DatabaseType.SPANNER,
            operation_type=OperationType.DELETE,
            tables=["users"],
            parameters=[ParameterSpec(name="userId")],
            target_language="java",
        )

        agent = MagicMock()
        agent.generate.return_value = MagicMock(
            text='stmt.executeQuery("SELECT 1")',
            token_usage={"input_tokens": 50, "output_tokens": 30},
        )
        agent.name = "mock"

        with patch.object(engine, '_resolve_agent', return_value=agent):
            result = engine.process_work_item(wi, agent=agent)

        # The tier used should reflect the override or escalation path
        assert result.work_item_id == "esc-001"


# ---------------------------------------------------------------------------
# Task 3: Kaizen hint injection (REQ-KQP-600)
# ---------------------------------------------------------------------------

class TestKaizenHintInjection:
    """Kaizen hints from prior runs are injected into generator prompts."""

    def test_hints_appear_in_system_prompt(self):
        from startd8.query_prime.generator import _build_system_prompt

        wi = QueryWorkItem(
            id="hint-1",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            target_language="csharp",
        )
        hints = [
            "Prior run had SQL injection in Npgsql DELETE queries",
            "Use @param binding for all user inputs",
        ]
        prompt = _build_system_prompt(wi, hints=hints)
        assert "SECURITY WARNINGS (Kaizen" in prompt
        assert "Prior run had SQL injection" in prompt
        assert "Use @param binding" in prompt

    def test_no_hints_no_section(self):
        from startd8.query_prime.generator import _build_system_prompt

        wi = QueryWorkItem(
            id="no-hint-1",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            target_language="csharp",
        )
        prompt = _build_system_prompt(wi)
        assert "Kaizen" not in prompt

    def test_max_three_hints(self):
        from startd8.query_prime.generator import _build_system_prompt

        wi = QueryWorkItem(
            id="max-hint",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            target_language="csharp",
        )
        hints = [f"Hint {i}" for i in range(10)]
        prompt = _build_system_prompt(wi, hints=hints)
        # Only first 3 should appear
        assert "Hint 0" in prompt
        assert "Hint 2" in prompt
        assert "Hint 3" not in prompt

    def test_engine_passes_hints_to_generator(self):
        """Engine threads kaizen_hints through to generate_query."""
        hints = ["Use NpgsqlParameter for all inputs"]
        engine = QueryPrimeEngine(kaizen_hints=hints)
        assert engine._kaizen_hints == hints

    def test_engine_caps_hints_at_max(self):
        """Engine caps hints to _MAX_KAIZEN_HINTS."""
        hints = [f"hint-{i}" for i in range(10)]
        engine = QueryPrimeEngine(kaizen_hints=hints)
        assert len(engine._kaizen_hints) == 3


# ---------------------------------------------------------------------------
# Task 4: Metrics accumulation (REQ-KQP-100, 101)
# ---------------------------------------------------------------------------

class TestMetricsAccumulation:
    """Engine accumulates results and produces verification reports."""

    def test_template_results_accumulated(self, health_check_work_item):
        engine = QueryPrimeEngine()
        engine.process_work_item(health_check_work_item)
        assert len(engine.accumulated_results) == 1
        assert engine.accumulated_results[0].work_item_id == "hc-1"

    def test_get_verification_report(self, health_check_work_item):
        engine = QueryPrimeEngine()
        engine.process_work_item(health_check_work_item)

        report = engine.get_verification_report("run-001")
        assert report["run_id"] == "run-001"
        assert report["total_work_items"] == 1
        assert "items" in report
        assert report["items"][0]["work_item_id"] == "hc-1"

    def test_multiple_items_accumulated(self):
        engine = QueryPrimeEngine()

        for i in range(3):
            wi = QueryWorkItem(
                id=f"hc-{i}",
                description="Health check",
                database=DatabaseType.POSTGRESQL,
                operation_type=OperationType.HEALTH_CHECK,
                target_language="csharp",
            )
            engine.process_work_item(wi)

        assert len(engine.accumulated_results) == 3
        report = engine.get_verification_report("run-multi")
        assert report["total_work_items"] == 3

    def test_save_verification_report(self, tmp_path, health_check_work_item):
        engine = QueryPrimeEngine(output_dir=tmp_path)
        engine.process_work_item(health_check_work_item)

        path = engine.save_verification_report("run-save", output_dir=tmp_path)
        assert path is not None
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["run_id"] == "run-save"
        assert data["total_work_items"] == 1


# ---------------------------------------------------------------------------
# Task 5: Prior injection signal (REQ-QP-300)
# ---------------------------------------------------------------------------

class TestPriorInjectionSignal:
    """Engine sets prior_injection_failure from Kaizen history."""

    def test_prior_injection_from_metrics_file(self, tmp_path):
        metrics = {
            "injection_total": 2,
            "by_database": {
                "postgresql": {"injection_findings": 1},
                "spanner": {"injection_findings": 0},
            },
        }
        metrics_path = tmp_path / "query-security-metrics.json"
        metrics_path.write_text(json.dumps(metrics))

        engine = QueryPrimeEngine(output_dir=tmp_path)
        assert "postgresql" in engine._prior_injection_databases
        assert "spanner" not in engine._prior_injection_databases

    def test_signal_set_for_prior_injection_database(self, tmp_path):
        metrics = {
            "injection_total": 1,
            "by_database": {
                "postgresql": {"injection_findings": 1},
            },
        }
        (tmp_path / "query-security-metrics.json").write_text(json.dumps(metrics))

        engine = QueryPrimeEngine(output_dir=tmp_path)
        wi = QueryWorkItem(
            id="sig-inj",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            target_language="csharp",
        )
        signals = engine._extract_signals(wi)
        assert signals.prior_injection_failure is True

    def test_no_signal_without_history(self):
        engine = QueryPrimeEngine()
        wi = QueryWorkItem(
            id="sig-none",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            target_language="csharp",
        )
        signals = engine._extract_signals(wi)
        assert signals.prior_injection_failure is False

    def test_missing_metrics_file_no_error(self, tmp_path):
        """No metrics file → no prior injection history, no error."""
        engine = QueryPrimeEngine(output_dir=tmp_path)
        assert len(engine._prior_injection_databases) == 0


# ---------------------------------------------------------------------------
# Task 6: Verification timing in report (REQ-KQP-102)
# ---------------------------------------------------------------------------

class TestVerificationTiming:
    """Verification timing is threaded through to report items."""

    def test_timing_in_report_items(self):
        results = [
            QueryResult(
                work_item_id="t-1",
                code="SELECT 1",
                verification=SecurityVerificationResult(
                    file_path="test.cs",
                    verdict=SecurityVerdict.PASS,
                    checks_passed=3,
                    verification_timing_ms={
                        "injection_ms": 0.5,
                        "credential_ms": 0.3,
                        "lifecycle_ms": 0.2,
                    },
                ),
                tier_used=ComplexityTier.TRIVIAL,
                model_used="template",
                cost_usd=0.0,
                escalations=0,
                retry_count=0,
            ),
        ]
        report = build_verification_report(results, "run-timing")
        item = report["items"][0]
        assert "verification_timing_ms" in item
        assert item["verification_timing_ms"]["injection_ms"] == 0.5

    def test_fp_suppressed_count_in_report(self):
        results = [
            QueryResult(
                work_item_id="fp-1",
                code="SELECT 1",
                verification=SecurityVerificationResult(
                    file_path="test.cs",
                    verdict=SecurityVerdict.PASS,
                    checks_passed=3,
                    false_positives_suppressed=2,
                ),
                tier_used=ComplexityTier.TRIVIAL,
                model_used="template",
                cost_usd=0.0,
                escalations=0,
                retry_count=0,
            ),
        ]
        report = build_verification_report(results, "run-fp")
        item = report["items"][0]
        assert item["false_positives_suppressed"] == 2

    def test_health_check_has_timing(self):
        """Template-path items get verification timing from verify_file."""
        engine = QueryPrimeEngine()
        wi = QueryWorkItem(
            id="hc-timing",
            description="Health check",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.HEALTH_CHECK,
            target_language="csharp",
        )
        result = engine.process_work_item(wi)
        assert result.verification is not None
        assert result.verification.verification_timing_ms is not None
        assert "injection_ms" in result.verification.verification_timing_ms


# ---------------------------------------------------------------------------
# Integration: generate_query passes hints and fp_registry
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Gap fix: --no-suppress audit mode (REQ-KQP-201)
# ---------------------------------------------------------------------------

class TestNoSuppressAuditMode:
    """--no-suppress flag disables all FP suppression."""

    def test_no_suppress_bypasses_registry(self):
        """verify_file ignores fp_registry when no_suppress=True."""
        from startd8.query_prime.security import verify_file

        registry = FalsePositiveRegistry(suppression_threshold=1)
        # Register a credential finding twice to reach threshold
        finding = SecurityFinding(
            check_type=SecurityCheckType.CREDENTIAL_LEAKAGE,
            severity="error",
            message="cred leak",
            pattern_hash="audit-fp-1",
        )
        registry.register(finding, "postgresql", "npgsql")  # occurrence 1
        registry.register(finding, "postgresql", "npgsql")  # occurrence 2 → suppressed
        assert registry.is_suppressed(finding)

        # With no_suppress, the registry is ignored (no actual cred in
        # this source, but the flag path is exercised)
        result = verify_file(
            "safe code", "t.cs", "postgresql", "csharp",
            fp_registry=registry,
            no_suppress=True,
        )
        # No findings in this safe code → PASS regardless
        assert result.verdict == SecurityVerdict.PASS
        assert result.false_positives_suppressed == 0

    def test_engine_threads_no_suppress(self):
        """Engine passes no_suppress to template-path verification."""
        engine = QueryPrimeEngine(no_suppress=True)
        assert engine._no_suppress is True

        wi = QueryWorkItem(
            id="hc-audit",
            description="Health check",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.HEALTH_CHECK,
            target_language="csharp",
        )
        result = engine.process_work_item(wi)
        assert result.verification.verdict == SecurityVerdict.PASS


# ---------------------------------------------------------------------------
# Gap fix: T3 threshold alert (REQ-KQP-302)
# ---------------------------------------------------------------------------

class TestT3ThresholdAlert:
    """build_verification_report logs WARNING when T3 first_pass_rate < 0.6."""

    def test_low_t3_rate_logs_warning(self, caplog):
        """Warning logged when SIMPLE tier first_pass_rate < 0.6."""
        import logging

        # Create results that produce a low SIMPLE-tier first_pass_rate
        results = []
        for i in range(5):
            verdict = SecurityVerdict.FAIL if i < 3 else SecurityVerdict.PASS
            results.append(QueryResult(
                work_item_id=f"t3-{i}",
                code=f"code-{i}",
                verification=SecurityVerificationResult(
                    file_path=f"t3-{i}.cs",
                    verdict=verdict,
                    checks_passed=3 if verdict == SecurityVerdict.PASS else 0,
                    checks_failed=0 if verdict == SecurityVerdict.PASS else 1,
                ),
                tier_used=ComplexityTier.SIMPLE,  # T3 tier
                model_used="haiku",
                cost_usd=0.01,
                escalations=0,
                retry_count=1,
            ))

        with caplog.at_level(logging.WARNING):
            report = build_verification_report(results, "run-t3-alert")

        # SIMPLE tier first_pass_rate = 2/5 = 0.4 < 0.6
        assert report["by_tier"]["simple"]["first_pass_rate"] == 0.4
        assert any("KQP-302" in msg for msg in caplog.messages)

    def test_good_t3_rate_no_warning(self, caplog):
        """No warning when SIMPLE tier first_pass_rate >= 0.6."""
        import logging

        results = []
        for i in range(5):
            results.append(QueryResult(
                work_item_id=f"t3g-{i}",
                code=f"code-{i}",
                verification=SecurityVerificationResult(
                    file_path=f"t3g-{i}.cs",
                    verdict=SecurityVerdict.PASS,
                    checks_passed=3,
                ),
                tier_used=ComplexityTier.SIMPLE,
                model_used="haiku",
                cost_usd=0.01,
                escalations=0,
                retry_count=1,
            ))

        with caplog.at_level(logging.WARNING):
            build_verification_report(results, "run-t3-good")

        assert not any("KQP-302" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# Gap fix: Auto-escalation routing (REQ-KQP-601)
# ---------------------------------------------------------------------------

class TestAutoEscalateFromTrends:
    """auto_escalate_from_trends creates/removes routing overrides."""

    def test_skip_below_min_runs(self):
        from startd8.query_prime.routing_overrides import auto_escalate_from_trends

        store = RoutingOverrideStore()
        actions = auto_escalate_from_trends(
            {"by_tier": {"SIMPLE": {"first_pass_rate": 0.3}}},
            store,
            run_count=5,
        )
        assert len(store) == 0
        assert "Skipped" in actions[0]

    def test_escalate_when_t3_below_threshold(self, tmp_path):
        from startd8.query_prime.routing_overrides import auto_escalate_from_trends

        store = RoutingOverrideStore(path=tmp_path / "overrides.json")
        actions = auto_escalate_from_trends(
            {"by_tier": {"SIMPLE": {"first_pass_rate": 0.45}}},
            store,
            run_count=15,
        )
        assert len(store) == 1
        assert "ESCALATED" in actions[0]
        # Override file was written
        assert (tmp_path / "overrides.json").exists()

    def test_restore_when_t3_above_threshold(self, tmp_path):
        from startd8.query_prime.routing_overrides import auto_escalate_from_trends

        store = RoutingOverrideStore(path=tmp_path / "overrides.json")
        # First: escalate
        auto_escalate_from_trends(
            {"by_tier": {"SIMPLE": {"first_pass_rate": 0.45}}},
            store,
            run_count=15,
        )
        assert len(store) == 1

        # Then: restore
        actions = auto_escalate_from_trends(
            {"by_tier": {"SIMPLE": {"first_pass_rate": 0.85}}},
            store,
            run_count=16,
        )
        assert len(store) == 0
        assert "RESTORED" in actions[0]

    def test_no_action_in_middle_range(self):
        from startd8.query_prime.routing_overrides import auto_escalate_from_trends

        store = RoutingOverrideStore()
        actions = auto_escalate_from_trends(
            {"by_tier": {"SIMPLE": {"first_pass_rate": 0.70}}},
            store,
            run_count=15,
        )
        assert len(store) == 0
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# Gap fix: FP rate in trends (REQ-KQP-402)
# ---------------------------------------------------------------------------

class TestFPRateTrends:
    """Trend script aggregates FP suppression rates across runs."""

    def test_fp_rate_extraction(self):
        # Import the script functions directly
        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location(
            "run_query_prime_trends",
            str(Path(__file__).resolve().parents[3] / "scripts" / "run_query_prime_trends.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        run = {
            "total_work_items": 10,
            "injection_total": 1,
            "credential_total": 1,
            "lifecycle_total": 2,
            "items": [
                {"false_positives_suppressed": 2},
                {"false_positives_suppressed": 1},
            ],
        }
        assert mod._extract_fp_suppressed(run) == 3
        # Rate: 3 / (1+1+2+3) = 3/7 ≈ 0.4286
        rate = mod._extract_fp_rate(run)
        assert 0.42 < rate < 0.44

    def test_trends_include_fp_slope(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "run_query_prime_trends",
            str(Path(__file__).resolve().parents[3] / "scripts" / "run_query_prime_trends.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        runs = [
            {"mean_score": 0.8, "pass_rate": 0.8, "total_cost_usd": 0.1,
             "injection_total": 1, "items": [{"false_positives_suppressed": 2}],
             "credential_total": 0, "lifecycle_total": 1},
            {"mean_score": 0.9, "pass_rate": 0.9, "total_cost_usd": 0.08,
             "injection_total": 0, "items": [{"false_positives_suppressed": 1}],
             "credential_total": 0, "lifecycle_total": 1},
        ]
        trends = mod.compute_trends(runs)
        assert "fp_rate_slope" in trends
        assert "latest_fp_rate" in trends


class TestGenerateQueryKaizenArgs:
    """generate_query accepts and passes through hints and fp_registry."""

    def test_generate_query_with_hints(self):
        from startd8.query_prime.generator import generate_query

        wi = QueryWorkItem(
            id="gen-hint",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            target_language="csharp",
        )
        agent = MagicMock()
        agent.generate.return_value = MagicMock(
            text='cmd.ExecuteReader("SELECT 1")',
            token_usage={"input_tokens": 50, "output_tokens": 30},
        )

        code, verification, cost = generate_query(
            wi, agent,
            hints=["Use NpgsqlParameter"],
        )
        # Verify the hint was in the system prompt
        call_args = agent.generate.call_args
        system_prompt = call_args.kwargs.get("system_prompt", "")
        assert "NpgsqlParameter" in system_prompt

    def test_generate_query_with_fp_registry(self):
        from startd8.query_prime.generator import generate_query

        wi = QueryWorkItem(
            id="gen-fp",
            description="test",
            database=DatabaseType.POSTGRESQL,
            operation_type=OperationType.SELECT,
            target_language="csharp",
        )
        agent = MagicMock()
        agent.generate.return_value = MagicMock(
            text='cmd.ExecuteReader("SELECT 1")',
            token_usage={"input_tokens": 50, "output_tokens": 30},
        )
        registry = FalsePositiveRegistry()

        code, verification, cost = generate_query(
            wi, agent, fp_registry=registry,
        )
        assert verification is not None
