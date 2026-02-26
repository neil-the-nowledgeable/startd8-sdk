"""
Unit tests for the Forward-Looking Code Manifest (FLCM) Phase 3 — Extractor.

Covers: signature parsing, DeterministicExtractor, HumanYamlExtractor,
ProtoExtractor, ManifestMerger precedence rules, and end-to-end orchestration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pytest

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardElementSpec,
    ForwardManifest,
    InterfaceContract,
    compute_binding_text,
)
from startd8.forward_manifest_extractor import (
    DeterministicExtractor,
    HumanYamlExtractor,
    ManifestMerger,
    ProtoExtractor,
    _extract_function_name,
    _make_contract,
    _parse_python_signature,
    extract_forward_contracts,
)
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature
from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature


# ═══════════════════════════════════════════════════════════════════════════
# Test helper
# ═══════════════════════════════════════════════════════════════════════════


def _make_feature(**overrides) -> ParsedFeature:
    """Create a ``ParsedFeature`` with sensible defaults."""
    defaults = {
        "feature_id": "F-001",
        "name": "Test Feature",
        "description": "A test feature",
        "target_files": ["src/app/main.py"],
        "dependencies": [],
        "estimated_loc": 50,
        "api_signatures": [],
        "protocol": "",
        "runtime_dependencies": [],
    }
    defaults.update(overrides)
    return ParsedFeature(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
# Group 1: Signature Parsing
# ═══════════════════════════════════════════════════════════════════════════


class TestSignatureParsing:
    """Tests for _parse_python_signature."""

    def test_basic(self):
        """Parse 'def foo(bar: int) -> str' → Param + return annotation."""
        sig = _parse_python_signature("def foo(bar: int) -> str")
        assert sig is not None
        assert sig.return_annotation == "str"
        assert len(sig.params) == 1
        assert sig.params[0].name == "bar"
        assert sig.params[0].annotation == "int"

    def test_no_return(self):
        """Parse 'process(data: bytes, count: int)' — no return, 2 params."""
        sig = _parse_python_signature("process(data: bytes, count: int)")
        assert sig is not None
        assert sig.return_annotation is None
        assert len(sig.params) == 2
        assert sig.params[0].name == "data"
        assert sig.params[1].name == "count"

    def test_malformed(self):
        """Malformed signature returns None."""
        sig = _parse_python_signature("not a function at all !!!")
        assert sig is None


# ═══════════════════════════════════════════════════════════════════════════
# Group 2: DeterministicExtractor
# ═══════════════════════════════════════════════════════════════════════════


class TestDeterministicExtractor:
    """Tests for DeterministicExtractor."""

    def test_api_signatures(self):
        """api_signatures produce FUNCTION_NAME contracts + ForwardElementSpec."""
        feature = _make_feature(
            api_signatures=["def serve(port: int) -> None"],
            target_files=["src/server.py"],
        )
        ext = DeterministicExtractor()
        contracts, file_elements = ext.extract([feature])

        fn_contracts = [
            c for c in contracts if c.category == ContractCategory.FUNCTION_NAME
        ]
        assert len(fn_contracts) == 1
        assert fn_contracts[0].function_name == "serve"
        assert fn_contracts[0].confidence == ContractConfidence.INFERRED
        assert fn_contracts[0].source_reference == "deterministic"
        assert "F-001" in fn_contracts[0].applicable_task_ids

        # ForwardElementSpec routed to target file
        assert "src/server.py" in file_elements
        specs = file_elements["src/server.py"]
        assert len(specs) == 1
        assert specs[0].kind == ElementKind.FUNCTION
        assert specs[0].name == "serve"
        assert specs[0].signature is not None

    def test_runtime_dependencies(self):
        """runtime_dependencies produce IMPORT_PATH contracts."""
        feature = _make_feature(runtime_dependencies=["flask", "redis"])
        ext = DeterministicExtractor()
        contracts, _ = ext.extract([feature])

        imp_contracts = [
            c for c in contracts if c.category == ContractCategory.IMPORT_PATH
        ]
        paths = {c.import_path for c in imp_contracts}
        assert "flask" in paths
        assert "redis" in paths

    def test_protocol(self):
        """Non-empty protocol produces INFRASTRUCTURE contract."""
        feature = _make_feature(protocol="grpc")
        ext = DeterministicExtractor()
        contracts, _ = ext.extract([feature])

        infra = [
            c for c in contracts if c.category == ContractCategory.INFRASTRUCTURE
        ]
        assert len(infra) == 1
        assert infra[0].dependency == "grpc"
        assert "gRPC transport" in infra[0].description

    def test_shared_files(self):
        """Files in 2+ features produce project-wide IMPORT_PATH contracts."""
        f1 = _make_feature(
            feature_id="F-001",
            target_files=["src/shared/utils.py", "src/app/main.py"],
        )
        f2 = _make_feature(
            feature_id="F-002",
            target_files=["src/shared/utils.py", "src/app/other.py"],
        )
        ext = DeterministicExtractor()
        contracts, _ = ext.extract([f1, f2])

        shared = [
            c
            for c in contracts
            if c.category == ContractCategory.IMPORT_PATH
            and "shared" in (c.description or "").lower()
        ]
        assert len(shared) >= 1
        # Project-wide → empty applicable_task_ids
        assert shared[0].applicable_task_ids == []


# ═══════════════════════════════════════════════════════════════════════════
# Group 3: HumanYamlExtractor
# ═══════════════════════════════════════════════════════════════════════════


class TestHumanYamlExtractor:
    """Tests for HumanYamlExtractor."""

    def test_valid_block(self):
        """Two valid entries produce two EXPLICIT contracts."""
        yaml_text = """\
shared_contracts:
  - contract_id: "HC-001"
    category: "function_name"
    description: "Main entry point"
    function_name: "main"
  - contract_id: "HC-002"
    category: "class_name"
    description: "Config class"
    class_name: "AppConfig"
"""
        ext = HumanYamlExtractor()
        contracts = ext.extract(yaml_text)
        assert len(contracts) == 2
        assert all(c.confidence == ContractConfidence.EXPLICIT for c in contracts)
        assert all(c.source_reference == "human-yaml" for c in contracts)
        ids = {c.contract_id for c in contracts}
        assert ids == {"HC-001", "HC-002"}

    def test_malformed_entry(self, caplog):
        """One valid + one bad entry → 1 contract, warning logged."""
        yaml_text = """\
shared_contracts:
  - contract_id: "HC-001"
    category: "function_name"
    description: "Valid entry"
    function_name: "foo"
  - category: "function_name"
    description: "Missing contract_id"
"""
        ext = HumanYamlExtractor()
        with caplog.at_level(logging.WARNING):
            contracts = ext.extract(yaml_text)
        assert len(contracts) == 1
        assert contracts[0].contract_id == "HC-001"
        assert any("malformed" in r.message.lower() or "missing" in r.message.lower()
                    for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════
# Group 4: ProtoExtractor
# ═══════════════════════════════════════════════════════════════════════════


class TestProtoExtractor:
    """Tests for ProtoExtractor."""

    def test_service_extraction(self, tmp_path):
        """Parse .proto file → CLASS_NAME (service + message) + API_ENDPOINT (rpc)."""
        proto_file = tmp_path / "api.proto"
        proto_file.write_text(
            """\
syntax = "proto3";

service UserService {
  rpc GetUser (GetUserRequest) returns (GetUserResponse);
  rpc CreateUser (CreateUserRequest) returns (CreateUserResponse);
}

message GetUserRequest {
  string user_id = 1;
}

message GetUserResponse {
  string name = 1;
}
""",
            encoding="utf-8",
        )
        ext = ProtoExtractor()
        contracts = ext.extract(tmp_path)

        # 1 service + 2 rpcs + 2 messages = 5
        assert len(contracts) == 5

        categories = {c.category for c in contracts}
        assert ContractCategory.CLASS_NAME in categories
        assert ContractCategory.API_ENDPOINT in categories

        assert all(c.confidence == ContractConfidence.EXPLICIT for c in contracts)
        assert all(c.source_reference == "proto" for c in contracts)

        rpc_names = {
            c.endpoint for c in contracts if c.category == ContractCategory.API_ENDPOINT
        }
        assert rpc_names == {"GetUser", "CreateUser"}

    def test_missing_directory(self):
        """Non-existent directory returns empty list."""
        ext = ProtoExtractor()
        contracts = ext.extract(Path("/nonexistent/path/to/protos"))
        assert contracts == []


# ═══════════════════════════════════════════════════════════════════════════
# Group 5: ManifestMerger
# ═══════════════════════════════════════════════════════════════════════════


class TestManifestMerger:
    """Tests for ManifestMerger precedence-based deduplication."""

    def _contract_with_source(
        self, contract_id: str, source: str
    ) -> InterfaceContract:
        """Helper: create a contract with a specific source_reference."""
        return _make_contract(
            contract_id=contract_id,
            category=ContractCategory.FUNCTION_NAME,
            confidence=ContractConfidence.INFERRED,
            description=f"From {source}",
            function_name="foo",
            source_reference=source,
        )

    def test_higher_precedence_overwrites(self):
        """human-yaml (3) overwrites deterministic (1) for same contract_id."""
        det = self._contract_with_source("C-001", "deterministic")
        human = self._contract_with_source("C-001", "human-yaml")

        merger = ManifestMerger()
        manifest = merger.merge([[det, human]], {})

        assert len(manifest.contracts) == 1
        assert manifest.contracts[0].source_reference == "human-yaml"

    def test_equal_precedence_retains_first(self, caplog):
        """Equal precedence retains first, logs warning."""
        c1 = self._contract_with_source("C-001", "deterministic")
        c2 = _make_contract(
            contract_id="C-001",
            category=ContractCategory.FUNCTION_NAME,
            confidence=ContractConfidence.INFERRED,
            description="Second deterministic",
            function_name="bar",
            source_reference="deterministic",
        )

        merger = ManifestMerger()
        with caplog.at_level(logging.WARNING):
            manifest = merger.merge([[c1, c2]], {})

        assert len(manifest.contracts) == 1
        assert manifest.contracts[0].description == "From deterministic"
        assert any("duplicate" in r.message.lower() for r in caplog.records)

    def test_lower_precedence_discarded(self):
        """Lower precedence (deterministic=1) discarded when human-yaml (3) already present."""
        human = self._contract_with_source("C-001", "human-yaml")
        det = self._contract_with_source("C-001", "deterministic")

        merger = ManifestMerger()
        # human-yaml first, deterministic second → det is lower, discarded
        manifest = merger.merge([[human, det]], {})

        assert len(manifest.contracts) == 1
        assert manifest.contracts[0].source_reference == "human-yaml"


# ═══════════════════════════════════════════════════════════════════════════
# Group 6: End-to-End
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEnd:
    """End-to-end tests for extract_forward_contracts orchestrator."""

    def test_mixed_sources(self, tmp_path):
        """Features + YAML + proto → correct count, 'EXTRACT' in stages."""
        features = [
            _make_feature(
                feature_id="F-001",
                api_signatures=["def handle(request: dict) -> dict"],
                runtime_dependencies=["flask"],
                protocol="http",
                target_files=["src/handler.py"],
            ),
        ]

        yaml_text = """\
shared_contracts:
  - contract_id: "HC-001"
    category: "config_key"
    description: "Database URL"
    env_var: "DATABASE_URL"
"""

        proto_dir = tmp_path / "proto"
        proto_dir.mkdir()
        (proto_dir / "svc.proto").write_text(
            "service Greeter {\n  rpc SayHello (Req) returns (Resp);\n}\n"
            "message Req {}\nmessage Resp {}\n",
            encoding="utf-8",
        )

        manifest = extract_forward_contracts(
            features, yaml_text=yaml_text, proto_dir=proto_dir
        )

        assert "EXTRACT" in manifest.stages_completed
        # Deterministic: 1 fn + 1 import + 1 infra = 3
        # Human YAML: 1
        # Proto: 1 service + 1 rpc + 2 messages = 4
        # Total: 8
        assert len(manifest.contracts) == 8

        # File specs populated for target file
        assert "src/handler.py" in manifest.file_specs

    def test_empty_input(self):
        """No features, no YAML, no proto → empty manifest, no crash."""
        manifest = extract_forward_contracts([])

        assert manifest.contracts == []
        assert manifest.file_specs == {}
        assert "EXTRACT" in manifest.stages_completed
