"""Tests for per-element import scoping in the classifier.

Verifies that file-level external imports don't inflate classification
scores for elements that don't actually reference those imports.
"""

from __future__ import annotations

import sys
import types

import pytest

# Work around circular import through micro_prime.__init__ when engine.py
# has uncommitted changes that break the import chain.
if "startd8.micro_prime" not in sys.modules:
    _pkg = types.ModuleType("startd8.micro_prime")
    _pkg.__path__ = ["src/startd8/micro_prime"]
    _pkg.__package__ = "startd8.micro_prime"
    sys.modules["startd8.micro_prime"] = _pkg

from startd8.micro_prime.classifier import (
    _build_import_index,
    _element_relevant_import_count,
    _extract_type_tokens,
    classify_element,
)
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
)
from startd8.micro_prime.models import MicroPrimeConfig, TierClassification
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ── Shared fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def heavy_import_file_spec() -> ForwardFileSpec:
    """File spec with 7 external packages (mirrors email_server.py)."""
    return ForwardFileSpec(
        file="src/emailservice/email_server.py",
        imports=[
            ForwardImportSpec(kind="import", module="grpc"),
            ForwardImportSpec(
                kind="from", module="grpc_health.v1",
                names=["health_pb2", "health_pb2_grpc"],
            ),
            ForwardImportSpec(
                kind="from", module="opentelemetry", names=["trace"],
            ),
            ForwardImportSpec(
                kind="from", module="opentelemetry.sdk.trace",
                names=["TracerProvider"],
            ),
            ForwardImportSpec(kind="import", module="google.cloud.profiler"),
            ForwardImportSpec(
                kind="from", module="google.auth.credentials",
                names=["Credentials"],
            ),
            ForwardImportSpec(
                kind="from", module="jinja2",
                names=["Environment", "FileSystemLoader"],
            ),
            ForwardImportSpec(kind="import", module="os"),
            ForwardImportSpec(kind="import", module="logging"),
        ],
        elements=[
            # 5 elements to avoid small-file bias
            ForwardElementSpec(
                kind=ElementKind.FUNCTION, name=f"fn_{i}",
                signature=Signature(params=[], return_annotation="None"),
            )
            for i in range(5)
        ],
    )


# ── _extract_type_tokens ─────────────────────────────────────────────────


class TestExtractTypeTokens:
    def test_simple_type(self):
        assert _extract_type_tokens("str") == {"str"}

    def test_dotted_type(self):
        tokens = _extract_type_tokens("grpc.Server")
        assert "grpc" in tokens
        assert "grpc.Server" in tokens

    def test_generic(self):
        tokens = _extract_type_tokens("Optional[grpc.Server]")
        assert "Optional" in tokens
        assert "grpc" in tokens
        assert "grpc.Server" in tokens

    def test_deeply_nested(self):
        tokens = _extract_type_tokens("google.cloud.logging.Client")
        assert "google" in tokens
        assert "google.cloud" in tokens
        assert "google.cloud.logging" in tokens


# ── _element_relevant_import_count ────────────────────────────────────────


class TestElementRelevantImportCount:
    def test_grpc_param_annotation(self, heavy_import_file_spec):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="send_email",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="context", annotation="grpc.ServicerContext"),
                ],
                return_annotation="None",
            ),
            parent_class="EmailService",
        )
        external_pkgs = {"grpc", "opentelemetry", "google.cloud", "google.auth", "jinja2"}
        import_index = _build_import_index(heavy_import_file_spec, external_pkgs)
        count, has_refs = _element_relevant_import_count(elem, import_index)
        assert count == 1  # only grpc
        assert has_refs is True

    def test_no_annotations_returns_no_refs(self, heavy_import_file_spec):
        """Element with no annotations/bases/decorators → has_refs=False."""
        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="Config",
        )
        external_pkgs = {"grpc", "jinja2"}
        import_index = _build_import_index(heavy_import_file_spec, external_pkgs)
        count, has_refs = _element_relevant_import_count(elem, import_index)
        assert count == 0
        assert has_refs is False

    def test_bases_match_import_names(self, heavy_import_file_spec):
        """Element bases referencing imported names → counted."""
        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="HealthCheck",
            bases=["health_pb2_grpc.HealthServicer"],
        )
        external_pkgs = {"grpc", "grpc_health", "jinja2"}
        import_index = _build_import_index(heavy_import_file_spec, external_pkgs)
        count, has_refs = _element_relevant_import_count(elem, import_index)
        # health_pb2_grpc is an imported name from grpc_health.v1
        assert count >= 1
        assert has_refs is True

    def test_unresolved_bases_return_zero(self, heavy_import_file_spec):
        """Bases referencing non-imported names → count=0, has_refs=True."""
        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="DummyService",
            bases=["demo_pb2_grpc.EmailServiceServicer"],
        )
        external_pkgs = {"grpc", "jinja2", "opentelemetry"}
        import_index = _build_import_index(heavy_import_file_spec, external_pkgs)
        count, has_refs = _element_relevant_import_count(elem, import_index)
        assert count == 0
        assert has_refs is True

    def test_jinja2_decorator(self, heavy_import_file_spec):
        """Decorator referencing an imported name → counted."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="render",
            signature=Signature(params=[], return_annotation="str"),
            decorators=["Environment"],
        )
        external_pkgs = {"grpc", "jinja2"}
        import_index = _build_import_index(heavy_import_file_spec, external_pkgs)
        count, has_refs = _element_relevant_import_count(elem, import_index)
        # Environment is imported from jinja2
        assert count == 1
        assert has_refs is True


# ── End-to-end classification ─────────────────────────────────────────────


class TestElementAwareClassification:
    """Verify that elements in import-heavy files aren't uniformly escalated."""

    def test_simple_getter_stays_simple(self, heavy_import_file_spec):
        """A simple getter in a file with 7 external imports → SIMPLE."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="get_port",
            signature=Signature(
                params=[Param(name="self")],
                return_annotation="int",
            ),
            parent_class="Config",
        )
        tier, reason = classify_element(elem, heavy_import_file_spec, [])
        assert tier == TierClassification.SIMPLE

    def test_class_no_external_bases_not_complex(self, heavy_import_file_spec):
        """A class with non-external bases in import-heavy file → not COMPLEX."""
        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="DummyEmailService",
            bases=["demo_pb2_grpc.EmailServiceServicer"],
            docstring_hint="Dummy email service for testing.",
        )
        tier, reason = classify_element(elem, heavy_import_file_spec, [])
        assert tier != TierClassification.COMPLEX

    def test_method_with_grpc_param_not_complex(self, heavy_import_file_spec):
        """A method using grpc in params → at most MODERATE, not COMPLEX."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="send_email",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="request", annotation="demo_pb2.Request"),
                    Param(name="context", annotation="grpc.ServicerContext"),
                ],
                return_annotation="demo_pb2.Empty",
            ),
            parent_class="EmailService",
        )
        tier, reason = classify_element(elem, heavy_import_file_spec, [])
        assert tier != TierClassification.COMPLEX

    def test_class_with_grpc_docstring_is_moderate(self, heavy_import_file_spec):
        """A class whose docstring mentions grpc → MODERATE (docstring gate)."""
        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="EmailService",
            bases=["demo_pb2_grpc.EmailServiceServicer"],
            docstring_hint="Email service using gRPC.",
        )
        tier, reason = classify_element(elem, heavy_import_file_spec, [])
        assert tier == TierClassification.MODERATE
        assert "grpc" in reason
