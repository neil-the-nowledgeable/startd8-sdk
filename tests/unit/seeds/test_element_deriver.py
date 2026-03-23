"""Tests for element deriver — REQ-DFA-108, REQ-DFA-100.

Validates progressive element derivation from feature metadata
for non-Python languages (C#, Go, Java, Node.js).
"""

import pytest

from startd8.seeds.element_deriver import (
    derive_elements_for_file,
    enrich_forward_manifest,
)


# ---------------------------------------------------------------------------
# T0: Filename → primary type
# ---------------------------------------------------------------------------

class TestFilenameDerivation:

    def test_csharp_class_from_filename(self):
        elements, _ = derive_elements_for_file(
            "src/cartservice/src/CartStore.cs",
        )
        assert len(elements) >= 1
        assert elements[0]["name"] == "CartStore"
        assert elements[0]["kind"] == "class"

    def test_csharp_interface_from_i_prefix(self):
        elements, _ = derive_elements_for_file(
            "src/cartservice/src/ICartStore.cs",
        )
        assert len(elements) >= 1
        assert elements[0]["name"] == "ICartStore"
        assert "interface" in elements[0].get("decorators", [])

    def test_go_type_from_filename(self):
        elements, _ = derive_elements_for_file(
            "src/shippingservice/shipping.go",
        )
        assert len(elements) >= 1
        assert elements[0]["name"] == "shipping"
        assert elements[0]["kind"] == "class"

    def test_java_class_from_filename(self):
        elements, _ = derive_elements_for_file(
            "src/main/java/com/example/CartService.java",
        )
        assert len(elements) >= 1
        assert elements[0]["name"] == "CartService"

    def test_nodejs_class_from_filename(self):
        elements, _ = derive_elements_for_file(
            "src/currencyservice/server.js",
        )
        assert len(elements) >= 1
        assert elements[0]["name"] == "server"

    def test_typescript_file(self):
        elements, _ = derive_elements_for_file(
            "src/frontend/utils/helper.ts",
        )
        assert len(elements) >= 1

    def test_non_source_file_returns_empty(self):
        elements, imports = derive_elements_for_file("Dockerfile")
        assert elements == []
        assert imports == []

    def test_python_file_returns_empty(self):
        """Python files should not be processed (handled by AST extractor)."""
        elements, imports = derive_elements_for_file("src/main.py")
        assert elements == []


# ---------------------------------------------------------------------------
# T1: Description → base classes
# ---------------------------------------------------------------------------

class TestDescriptionExtraction:

    def test_implements_keyword(self):
        elements, _ = derive_elements_for_file(
            "src/cartstore/SpannerCartStore.cs",
            feature_description="Implements ICartStore with Spanner backend",
        )
        assert elements[0]["bases"] == ["ICartStore"]

    def test_extends_keyword(self):
        elements, _ = derive_elements_for_file(
            "src/BaseService.java",
            feature_description="Extends AbstractService for common logic",
        )
        assert "AbstractService" in elements[0]["bases"]

    def test_interface_from_description_keyword(self):
        elements, _ = derive_elements_for_file(
            "src/CartStore.go",
            feature_description="Interface for cart store operations",
        )
        assert "interface" in elements[0].get("decorators", [])

    def test_no_bases_without_keywords(self):
        elements, _ = derive_elements_for_file(
            "src/Startup.cs",
            feature_description="ASP.NET Core startup configuration",
        )
        assert elements[0]["bases"] == []


# ---------------------------------------------------------------------------
# T2: Contracts → method signatures
# ---------------------------------------------------------------------------

class TestContractDerivation:

    def test_method_from_contract(self):
        contracts = [{
            "name": "AddItemAsync",
            "category": "FUNCTION_NAME",
            "applicable_task_ids": [],
            "parameters": [
                {"name": "userId", "type": "string"},
                {"name": "productId", "type": "string"},
            ],
            "return_type": "Task",
        }]
        elements, _ = derive_elements_for_file(
            "src/CartStore.cs",
            feature_description="CartStore with AddItemAsync",
            contracts=contracts,
        )
        # Should have class element + method element
        method_elements = [e for e in elements if e.get("parent_class")]
        assert len(method_elements) >= 1
        assert method_elements[0]["name"] == "AddItemAsync"
        assert method_elements[0]["kind"] == "async_method"

    def test_contract_not_matching_skipped(self):
        contracts = [{
            "name": "UnrelatedMethod",
            "category": "FUNCTION_NAME",
            "applicable_task_ids": [],
        }]
        elements, _ = derive_elements_for_file(
            "src/CartStore.cs",
            contracts=contracts,
        )
        method_elements = [e for e in elements if e.get("parent_class")]
        assert len(method_elements) == 0


# ---------------------------------------------------------------------------
# T3: Framework imports → DI constructor
# ---------------------------------------------------------------------------

class TestFrameworkDerivation:

    def test_csharp_logger_injection(self):
        elements, imports = derive_elements_for_file(
            "src/CartService.cs",
            language_id="csharp",
            framework_imports={
                "grpc": {
                    "detect_keywords": ["grpc", "proto"],
                    "imports": ["Grpc.Core"],
                },
            },
            feature_description="gRPC cart service",
        )
        # Should have ILogger constructor param
        constructors = [e for e in elements if e.get("parent_class") and e["name"] == "CartService"]
        assert len(constructors) >= 1
        params = constructors[0]["signature"]["params"]
        assert any(p["name"] == "logger" for p in params)

        # Should have framework import
        assert any(i["module"] == "Grpc.Core" for i in imports)

    def test_no_framework_without_keywords(self):
        _, imports = derive_elements_for_file(
            "src/Utils.cs",
            language_id="csharp",
            framework_imports={
                "grpc": {
                    "detect_keywords": ["grpc"],
                    "imports": ["Grpc.Core"],
                },
            },
            feature_description="Utility class for string operations",
        )
        # No gRPC keywords in description → no gRPC imports
        assert not any(i.get("module") == "Grpc.Core" for i in imports)


# ---------------------------------------------------------------------------
# enrich_forward_manifest integration
# ---------------------------------------------------------------------------

class TestEnrichForwardManifest:

    def test_enriches_empty_file_specs(self):
        manifest = {
            "file_specs": {
                "src/CartStore.cs": {"elements": [], "imports": []},
                "src/main.py": {"elements": [{"kind": "class", "name": "Main"}], "imports": []},
            },
            "contracts": [],
        }
        tasks = [{
            "task_id": "PI-001",
            "config": {
                "task_description": "CartStore service",
                "context": {"target_files": ["src/CartStore.cs"]},
            },
        }]
        count = enrich_forward_manifest(manifest, tasks)
        assert count == 1  # Only CartStore.cs enriched (Python already has elements)
        assert len(manifest["file_specs"]["src/CartStore.cs"]["elements"]) >= 1

    def test_idempotent_does_not_overwrite(self):
        """Elements from AST extraction should not be overwritten."""
        existing = [{"kind": "class", "name": "CartStore", "bases": ["ICartStore"]}]
        manifest = {
            "file_specs": {
                "src/CartStore.cs": {"elements": existing, "imports": []},
            },
            "contracts": [],
        }
        count = enrich_forward_manifest(manifest, [])
        assert count == 0
        assert manifest["file_specs"]["src/CartStore.cs"]["elements"] is existing

    def test_skips_non_source_files(self):
        manifest = {
            "file_specs": {
                "Dockerfile": {"elements": [], "imports": []},
                "go.mod": {"elements": [], "imports": []},
            },
            "contracts": [],
        }
        count = enrich_forward_manifest(manifest, [])
        assert count == 0
