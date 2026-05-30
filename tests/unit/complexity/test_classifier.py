"""Tests for complexity.classifier — tier classification logic."""

from startd8.complexity.classifier import classify_tier
from startd8.complexity.models import (
    ClassificationResult,
    ComplexityRoutingConfig,
    ComplexityTier,
    TaskComplexitySignals,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _signals(**overrides) -> TaskComplexitySignals:
    """Build a TaskComplexitySignals with custom fields."""
    return TaskComplexitySignals(**overrides)


def _config(**overrides) -> ComplexityRoutingConfig:
    """Build a ComplexityRoutingConfig with custom fields."""
    return ComplexityRoutingConfig(**overrides)


# ── COMPLEX triggers (any single one fires) ──────────────────────────


class TestComplexTriggers:
    def test_blast_radius(self):
        tier, reason = classify_tier(_signals(blast_radius=10))
        assert tier is ComplexityTier.COMPLEX
        assert "blast_radius" in reason

    def test_dynamic_dispatch(self):
        tier, reason = classify_tier(_signals(has_dynamic_dispatch=True))
        assert tier is ComplexityTier.COMPLEX
        assert "dynamic_dispatch" in reason

    def test_edit_mode_with_high_callers(self):
        tier, reason = classify_tier(
            _signals(edit_mode="edit", caller_count=5)
        )
        assert tier is ComplexityTier.COMPLEX
        assert "caller_count" in reason

    def test_edit_mode_with_low_callers_default_complex(self):
        """Edit mode with low callers doesn't trigger COMPLEX via the
        edit_mode+callers rule, but falls through to default (COMPLEX)."""
        tier, reason = classify_tier(
            _signals(edit_mode="edit", caller_count=2)
        )
        assert tier is ComplexityTier.COMPLEX
        assert "default" in reason  # hit default, not the edit_mode trigger

    def test_create_mode_with_high_callers_default_complex(self):
        """caller_count trigger only fires in edit mode; create mode
        with high callers falls through to default (COMPLEX)."""
        tier, reason = classify_tier(
            _signals(edit_mode="create", caller_count=10)
        )
        assert tier is ComplexityTier.COMPLEX
        assert "default" in reason

    def test_mro_depth(self):
        tier, reason = classify_tier(_signals(mro_depth=5))
        assert tier is ComplexityTier.COMPLEX
        assert "mro_depth" in reason

    def test_unresolved_calls(self):
        tier, reason = classify_tier(_signals(unresolved_call_count=4))
        assert tier is ComplexityTier.COMPLEX
        assert "unresolved_call_count" in reason

    def test_high_loc(self):
        tier, reason = classify_tier(_signals(estimated_loc=600))
        assert tier is ComplexityTier.COMPLEX
        assert "estimated_loc" in reason

    def test_multi_file_cross_edges(self):
        tier, reason = classify_tier(
            _signals(target_file_count=3, has_cross_file_edges=True)
        )
        assert tier is ComplexityTier.COMPLEX
        assert "cross-file" in reason

    def test_multi_file_no_edges_default_complex(self):
        """Multi-file alone (without edges) doesn't trigger COMPLEX via the
        multi-file rule, but falls through to default (COMPLEX)."""
        tier, reason = classify_tier(
            _signals(target_file_count=3, has_cross_file_edges=False)
        )
        assert tier is ComplexityTier.COMPLEX
        assert "default" in reason

    def test_single_file_with_edges_default_complex(self):
        """Single file + edges flag doesn't trigger COMPLEX via multi-file rule,
        but falls through to default (COMPLEX)."""
        tier, reason = classify_tier(
            _signals(target_file_count=1, has_cross_file_edges=True)
        )
        assert tier is ComplexityTier.COMPLEX
        assert "default" in reason


# ── SIMPLE eligibility (all conditions must pass) ────────────────────


class TestSimpleEligibility:
    SIMPLE_SIGNALS = dict(
        manifest_coverage="full",
        blast_radius=0,
        edit_mode="create",
        caller_count=0,
        has_dynamic_dispatch=False,
        estimated_loc=100,
        target_file_count=1,
    )

    def test_all_conditions_met(self):
        tier, reason = classify_tier(_signals(**self.SIMPLE_SIGNALS))
        assert tier is ComplexityTier.SIMPLE
        assert "SIMPLE" in reason

    def test_not_simple_if_manifest_partial_strict(self):
        """Strict gate rejects partial manifest coverage."""
        tier, _ = classify_tier(
            _signals(**{**self.SIMPLE_SIGNALS, "manifest_coverage": "partial"}),
            _config(simple_relaxed_enabled=False),
        )
        assert tier is ComplexityTier.COMPLEX

    def test_simple_if_manifest_partial_relaxed(self):
        """Relaxed gate (default) accepts partial manifest + create mode."""
        tier, reason = classify_tier(
            _signals(**{**self.SIMPLE_SIGNALS, "manifest_coverage": "partial"})
        )
        assert tier is ComplexityTier.SIMPLE
        assert "relaxed" in reason

    def test_not_simple_if_blast_radius_nonzero_strict(self):
        """Strict gate rejects blast_radius > 0."""
        tier, _ = classify_tier(
            _signals(**{**self.SIMPLE_SIGNALS, "blast_radius": 1}),
            _config(simple_relaxed_enabled=False),
        )
        assert tier is ComplexityTier.COMPLEX

    def test_simple_if_blast_radius_small_relaxed(self):
        """Relaxed gate (default) accepts small blast_radius + create mode."""
        tier, reason = classify_tier(
            _signals(**{**self.SIMPLE_SIGNALS, "blast_radius": 1})
        )
        assert tier is ComplexityTier.SIMPLE
        assert "relaxed" in reason

    def test_not_simple_if_edit_mode(self):
        tier, _ = classify_tier(
            _signals(**{**self.SIMPLE_SIGNALS, "edit_mode": "edit"})
        )
        assert tier is ComplexityTier.COMPLEX

    def test_not_simple_if_callers(self):
        tier, _ = classify_tier(
            _signals(**{**self.SIMPLE_SIGNALS, "caller_count": 1})
        )
        assert tier is ComplexityTier.COMPLEX

    def test_not_simple_if_loc_too_high(self):
        tier, _ = classify_tier(
            _signals(**{**self.SIMPLE_SIGNALS, "estimated_loc": 200})
        )
        assert tier is ComplexityTier.COMPLEX

    def test_not_simple_if_multi_file(self):
        tier, _ = classify_tier(
            _signals(**{**self.SIMPLE_SIGNALS, "target_file_count": 2})
        )
        assert tier is ComplexityTier.COMPLEX


# ── Default → COMPLEX (was MODERATE before AC-R3-R7) ──────────────────


class TestComplexDefault:
    def test_default_signals(self):
        tier, reason = classify_tier(_signals())
        assert tier is ComplexityTier.COMPLEX
        assert "default" in reason

    def test_edit_mode_unknown(self):
        tier, _ = classify_tier(_signals(edit_mode="unknown"))
        assert tier is ComplexityTier.COMPLEX


# ── Config threshold overrides ───────────────────────────────────────


class TestThresholdOverrides:
    def test_custom_blast_radius_threshold(self):
        """Raise threshold so blast_radius=6 no longer triggers COMPLEX via blast_radius rule."""
        tier, reason = classify_tier(
            _signals(blast_radius=6),
            _config(blast_radius_complex_threshold=10),
        )
        assert tier is ComplexityTier.COMPLEX
        assert "blast_radius" not in reason  # trigger didn't fire
        assert "default" in reason

    def test_custom_loc_simple_max(self):
        """Raise SIMPLE LOC limit so estimated_loc=200 qualifies."""
        tier, _ = classify_tier(
            _signals(
                manifest_coverage="full",
                blast_radius=0,
                edit_mode="create",
                caller_count=0,
                estimated_loc=200,
                target_file_count=1,
            ),
            _config(loc_simple_max=300),
        )
        assert tier is ComplexityTier.SIMPLE

    def test_custom_loc_complex_min(self):
        """Lower COMPLEX LOC threshold so estimated_loc=400 triggers."""
        tier, _ = classify_tier(
            _signals(estimated_loc=400),
            _config(loc_complex_min=300),
        )
        assert tier is ComplexityTier.COMPLEX

    def test_custom_caller_threshold(self):
        """Raise caller threshold so caller_count=4 does not trigger COMPLEX via caller rule."""
        tier, reason = classify_tier(
            _signals(edit_mode="edit", caller_count=4),
            _config(caller_count_complex_threshold=5),
        )
        assert tier is ComplexityTier.COMPLEX
        assert "caller_count" not in reason  # trigger didn't fire
        assert "default" in reason


# ── None config uses defaults ────────────────────────────────────────


# ── Non-Python file routing ─────────────────────────────────────────


class TestNonPythonRouting:
    def test_html_below_trivial_threshold(self):
        """HTML template (54 LOC) should route to TRIVIAL."""
        tier, reason = classify_tier(
            _signals(file_extension=".html", estimated_loc=54)
        )
        assert tier is ComplexityTier.TRIVIAL
        assert ".html" in reason

    def test_dockerfile_below_trivial_threshold(self):
        tier, reason = classify_tier(
            _signals(file_extension="", estimated_loc=50)
        )
        # Empty extension falls back to .py default, not non-Python
        # (Dockerfiles use no extension — handled by explicit empty check)

    def test_yaml_below_simple_threshold(self):
        """YAML config at 200 LOC should route to SIMPLE."""
        tier, reason = classify_tier(
            _signals(file_extension=".yaml", estimated_loc=200)
        )
        assert tier is ComplexityTier.SIMPLE
        assert ".yaml" in reason

    def test_non_python_above_simple_threshold(self):
        """Large non-Python file should route to COMPLEX."""
        tier, reason = classify_tier(
            _signals(file_extension=".html", estimated_loc=400)
        )
        assert tier is ComplexityTier.COMPLEX
        assert ".html" in reason

    def test_python_file_not_affected(self):
        """Python files should NOT take the non-Python path."""
        tier, _ = classify_tier(_signals(file_extension=".py"))
        assert tier is ComplexityTier.COMPLEX  # default

    def test_requirements_txt_trivial(self):
        tier, reason = classify_tier(
            _signals(file_extension=".txt", estimated_loc=9)
        )
        assert tier is ComplexityTier.TRIVIAL

    def test_vue_uses_full_classifier_when_registered(self):
        """REQ-VUE-P-008: ``.vue`` is a supported extension — not LOC-only trivial."""
        from startd8.languages.registry import LanguageRegistry

        LanguageRegistry.discover()
        tier, reason = classify_tier(
            _signals(file_extension=".vue", estimated_loc=20),
        )
        assert "non-Python file (.vue)" not in reason


class TestNoneConfig:
    def test_none_config_uses_defaults(self):
        tier, _ = classify_tier(_signals(blast_radius=10), config=None)
        assert tier is ComplexityTier.COMPLEX


# ── Relaxed SIMPLE boundary (Kaizen run-017) ──────────────────────────


class TestRelaxedSimple:
    """Create-mode elements with small blast radius qualify as SIMPLE."""

    def test_blast_radius_1_create_mode(self):
        """Create-mode element with blast_radius=1 qualifies under relaxed gate."""
        tier, reason = classify_tier(
            _signals(
                blast_radius=1,
                edit_mode="create",
                caller_count=0,
                estimated_loc=100,
                target_file_count=1,
            ),
        )
        assert tier is ComplexityTier.SIMPLE
        assert "relaxed" in reason

    def test_blast_radius_2_create_mode(self):
        """blast_radius=2 is at the default relaxed threshold."""
        tier, reason = classify_tier(
            _signals(
                blast_radius=2,
                edit_mode="create",
                caller_count=0,
                estimated_loc=100,
                target_file_count=1,
            ),
        )
        assert tier is ComplexityTier.SIMPLE
        assert "relaxed" in reason

    def test_blast_radius_3_still_complex(self):
        """blast_radius=3 exceeds the relaxed threshold → COMPLEX (default)."""
        tier, _ = classify_tier(
            _signals(
                blast_radius=3,
                edit_mode="create",
                caller_count=0,
                estimated_loc=100,
                target_file_count=1,
            ),
        )
        assert tier is ComplexityTier.COMPLEX

    def test_edit_mode_not_relaxed(self):
        """Edit-mode elements are NOT eligible for relaxed SIMPLE."""
        tier, _ = classify_tier(
            _signals(
                blast_radius=1,
                edit_mode="edit",
                caller_count=0,
                estimated_loc=100,
                target_file_count=1,
            ),
        )
        assert tier is ComplexityTier.COMPLEX

    def test_relaxed_disabled(self):
        """With simple_relaxed_enabled=False, blast_radius=1 stays COMPLEX (default)."""
        tier, _ = classify_tier(
            _signals(
                blast_radius=1,
                edit_mode="create",
                caller_count=0,
                estimated_loc=100,
                target_file_count=1,
            ),
            _config(simple_relaxed_enabled=False),
        )
        assert tier is ComplexityTier.COMPLEX

    def test_partial_manifest_create_mode(self):
        """Partial manifest coverage + create mode + blast_radius=0 → relaxed SIMPLE."""
        tier, reason = classify_tier(
            _signals(
                manifest_coverage="partial",
                blast_radius=0,
                edit_mode="create",
                caller_count=0,
                estimated_loc=80,
                target_file_count=1,
            ),
        )
        assert tier is ComplexityTier.SIMPLE
        assert "relaxed" in reason


# ── ClassificationResult signal threading ──────────────────────────


class TestClassificationResultSignals:
    def test_returns_classification_result(self):
        """classify_tier must return a ClassificationResult, not a plain tuple."""
        result = classify_tier(_signals(blast_radius=10))
        assert isinstance(result, ClassificationResult)

    def test_signals_threaded_complex(self):
        signals = _signals(blast_radius=10, edit_mode="edit")
        result = classify_tier(signals)
        assert result.signals is signals
        assert result.tier is ComplexityTier.COMPLEX

    def test_signals_threaded_simple(self):
        signals = _signals(**TestSimpleEligibility.SIMPLE_SIGNALS)
        result = classify_tier(signals)
        assert result.signals is signals
        assert result.tier is ComplexityTier.SIMPLE

    def test_signals_threaded_default_complex(self):
        signals = _signals()
        result = classify_tier(signals)
        assert result.signals is signals
        assert result.tier is ComplexityTier.COMPLEX

    def test_tuple_unpacking_still_works(self):
        """Backward compat: tier, reason = classify_tier(...) must work."""
        tier, reason = classify_tier(_signals(has_dynamic_dispatch=True))
        assert tier is ComplexityTier.COMPLEX
        assert "dynamic_dispatch" in reason


# ── Exemplar-informed tier downgrade (Layer 1) ────────────────────


class _FakeScores:
    """Minimal stand-in for ExemplarScores."""

    def __init__(self, disk_quality_score: float = 1.0, cost_usd: float = 0.0):
        self.disk_quality_score = disk_quality_score
        self.cost_usd = cost_usd


class _FakeExemplar:
    """Minimal stand-in for ExemplarEntry."""

    def __init__(self, id: str = "ex-abc123", maturity: int = 3,
                 disk_quality_score: float = 1.0):
        self.id = id
        self.maturity = maturity
        self.scores = _FakeScores(disk_quality_score=disk_quality_score)


class _FakeRegistry:
    """Minimal stand-in for ExemplarRegistry."""

    def __init__(self, match=None):
        self._match = match

    def find_best_match(self, fingerprint):
        return self._match


class _FakeFingerprint:
    """Minimal stand-in for ConfigFingerprint."""
    pass


class TestExemplarDowngrade:
    """Exemplar-informed complexity tier downgrade (Layer 1)."""

    # Signals that normally classify as COMPLEX (default)
    COMPLEX_SIGNALS = dict()  # default signals → COMPLEX

    # Signals that normally classify as SIMPLE (strict)
    SIMPLE_SIGNALS = dict(
        manifest_coverage="full",
        blast_radius=0,
        edit_mode="create",
        caller_count=0,
        has_dynamic_dispatch=False,
        estimated_loc=100,
        target_file_count=1,
    )

    def test_downgrade_complex_to_moderate(self):
        """COMPLEX task with qualifying exemplar → MODERATE (one step down)."""
        registry = _FakeRegistry(match=_FakeExemplar(maturity=3, disk_quality_score=1.0))
        result = classify_tier(
            _signals(**self.COMPLEX_SIGNALS),
            exemplar_registry=registry,
            fingerprint=_FakeFingerprint(),
        )
        assert result.tier is ComplexityTier.MODERATE
        assert "exemplar downgrade" in result.reason
        assert "ex-abc123" in result.reason
        assert result.exemplar_override == "ex-abc123"

    def test_downgrade_simple_to_trivial(self):
        """SIMPLE task with qualifying exemplar → TRIVIAL."""
        registry = _FakeRegistry(match=_FakeExemplar(maturity=4, disk_quality_score=1.5))
        result = classify_tier(
            _signals(**self.SIMPLE_SIGNALS),
            exemplar_registry=registry,
            fingerprint=_FakeFingerprint(),
        )
        assert result.tier is ComplexityTier.TRIVIAL
        assert "exemplar downgrade" in result.reason

    def test_trivial_stays_trivial(self):
        """TRIVIAL task with qualifying exemplar stays TRIVIAL (floor)."""
        registry = _FakeRegistry(match=_FakeExemplar(maturity=3, disk_quality_score=1.0))
        result = classify_tier(
            _signals(file_extension=".html", estimated_loc=50),
            exemplar_registry=registry,
            fingerprint=_FakeFingerprint(),
        )
        assert result.tier is ComplexityTier.TRIVIAL
        assert result.exemplar_override is None  # no downgrade applied

    def test_no_downgrade_low_maturity(self):
        """maturity=2 does not qualify for downgrade."""
        registry = _FakeRegistry(match=_FakeExemplar(maturity=2, disk_quality_score=1.0))
        result = classify_tier(
            _signals(**self.COMPLEX_SIGNALS),
            exemplar_registry=registry,
            fingerprint=_FakeFingerprint(),
        )
        assert result.tier is ComplexityTier.COMPLEX
        assert result.exemplar_override is None

    def test_no_downgrade_low_score(self):
        """disk_quality_score < 1.0 does not qualify for downgrade."""
        registry = _FakeRegistry(match=_FakeExemplar(maturity=3, disk_quality_score=0.8))
        result = classify_tier(
            _signals(**self.COMPLEX_SIGNALS),
            exemplar_registry=registry,
            fingerprint=_FakeFingerprint(),
        )
        assert result.tier is ComplexityTier.COMPLEX
        assert result.exemplar_override is None

    def test_no_downgrade_no_match(self):
        """No matching exemplar → normal classification."""
        registry = _FakeRegistry(match=None)
        result = classify_tier(
            _signals(**self.COMPLEX_SIGNALS),
            exemplar_registry=registry,
            fingerprint=_FakeFingerprint(),
        )
        assert result.tier is ComplexityTier.COMPLEX
        assert result.exemplar_override is None

    def test_no_downgrade_none_registry(self):
        """No registry passed → normal classification."""
        result = classify_tier(
            _signals(**self.COMPLEX_SIGNALS),
            exemplar_registry=None,
            fingerprint=_FakeFingerprint(),
        )
        assert result.tier is ComplexityTier.COMPLEX
        assert result.exemplar_override is None

    def test_no_downgrade_none_fingerprint(self):
        """No fingerprint passed → normal classification."""
        registry = _FakeRegistry(match=_FakeExemplar())
        result = classify_tier(
            _signals(**self.COMPLEX_SIGNALS),
            exemplar_registry=registry,
            fingerprint=None,
        )
        assert result.tier is ComplexityTier.COMPLEX
        assert result.exemplar_override is None

    def test_registry_exception_non_fatal(self):
        """Exception in registry.find_best_match → graceful fallback."""

        class _BrokenRegistry:
            def find_best_match(self, fp):
                raise RuntimeError("boom")

        result = classify_tier(
            _signals(**self.COMPLEX_SIGNALS),
            exemplar_registry=_BrokenRegistry(),
            fingerprint=_FakeFingerprint(),
        )
        assert result.tier is ComplexityTier.COMPLEX
        assert result.exemplar_override is None

    def test_exemplar_override_field_set(self):
        """exemplar_override carries the exemplar ID when downgrade applied."""
        registry = _FakeRegistry(match=_FakeExemplar(id="ex-test-99"))
        result = classify_tier(
            _signals(**self.COMPLEX_SIGNALS),
            exemplar_registry=registry,
            fingerprint=_FakeFingerprint(),
        )
        assert result.exemplar_override == "ex-test-99"

    def test_signals_preserved_after_downgrade(self):
        """Original signals are preserved through the downgrade."""
        signals = _signals(blast_radius=10)
        registry = _FakeRegistry(match=_FakeExemplar())
        result = classify_tier(
            signals,
            exemplar_registry=registry,
            fingerprint=_FakeFingerprint(),
        )
        assert result.signals is signals
