"""Tests for multi-language plan ingestion support (REQ-PLI-100–701).

Covers Java and Node.js metadata inference, QP-1 field threading,
ParsedFeature construction with language fields, and lang_detect mappings.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List

from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature


# ---------------------------------------------------------------------------
# Helpers — lightweight feature stubs for _infer_service_metadata()
# ---------------------------------------------------------------------------

@dataclass
class _FakeFeature:
    """Minimal feature stub with all fields used by infer_service_metadata."""
    target_files: List[str] = field(default_factory=list)
    protocol: str = ""
    runtime_dependencies: List[str] = field(default_factory=list)
    api_signatures: List[str] = field(default_factory=list)
    negative_scope: List[str] = field(default_factory=list)
    module_path: str = ""
    service_name: str = ""
    java_package: str = ""
    build_system: str = ""
    java_version: str = ""
    spring_boot: bool = False
    module_system: str = ""
    node_version: str = ""


# ---------------------------------------------------------------------------
# _infer_service_metadata() — Java features
# ---------------------------------------------------------------------------

class TestInferServiceMetadataJava:
    """REQ-PLI-300: Java metadata inference."""

    def _infer(self, features, onboarding=None):
        from startd8.seeds.derivation import infer_service_metadata
        return infer_service_metadata(features, onboarding)

    def test_java_package_from_feature(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/example/svc/App.java"],
            java_package="com.example.svc",
        )
        meta = self._infer([feat])
        assert meta["java_package"] == "com.example.svc"

    def test_java_package_inferred_from_path(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/example/order/OrderService.java"],
        )
        meta = self._infer([feat])
        assert meta["java_package"] == "com.example.order"

    def test_build_system_gradle_explicit(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
            build_system="gradle",
        )
        meta = self._infer([feat])
        assert meta["build_system"] == "gradle"

    def test_build_system_maven_from_files(self):
        feat = _FakeFeature(
            target_files=["pom.xml", "src/main/java/com/ex/App.java"],
        )
        meta = self._infer([feat])
        assert meta["build_system"] == "maven"

    def test_build_system_gradle_from_files(self):
        feat = _FakeFeature(
            target_files=["build.gradle", "src/main/java/com/ex/App.java"],
        )
        meta = self._infer([feat])
        assert meta["build_system"] == "gradle"

    def test_build_system_default_gradle(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
        )
        meta = self._infer([feat])
        assert meta["build_system"] == "gradle"

    def test_java_version_default(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
        )
        meta = self._infer([feat])
        assert meta["java_version"] == "21"

    def test_java_version_from_feature(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
            java_version="17",
        )
        meta = self._infer([feat])
        assert meta["java_version"] == "17"

    def test_java_version_from_onboarding(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
        )
        meta = self._infer([feat], onboarding={"java_version": "11"})
        assert meta["java_version"] == "11"

    def test_spring_boot_from_feature(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
            spring_boot=True,
        )
        meta = self._infer([feat])
        assert meta["spring_boot"] is True

    def test_spring_boot_from_deps(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
            runtime_dependencies=["org.springframework.boot:spring-boot-starter:3.2.0"],
        )
        meta = self._infer([feat])
        assert meta.get("spring_boot") is True

    def test_no_spring_boot_by_default(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
        )
        meta = self._infer([feat])
        assert "spring_boot" not in meta

    def test_primary_language_java(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
        )
        meta = self._infer([feat])
        assert meta["primary_language"] == "java"


class TestInferServiceMetadataMixed:
    """Mixed Go+Java features — Java block only runs for Java-primary."""

    def _infer(self, features, onboarding=None):
        from startd8.seeds.derivation import infer_service_metadata
        return infer_service_metadata(features, onboarding)

    def test_go_primary_no_java_metadata(self):
        feat = _FakeFeature(
            target_files=["src/svc/main.go"],
            module_path="github.com/org/repo",
        )
        meta = self._infer([feat])
        assert "java_package" not in meta
        assert meta.get("primary_language") == "go"

    def test_java_primary_no_go_metadata(self):
        feat = _FakeFeature(
            target_files=["src/main/java/com/ex/App.java"],
            java_package="com.ex",
        )
        meta = self._infer([feat])
        assert "module_path" not in meta
        assert meta["java_package"] == "com.ex"


# ---------------------------------------------------------------------------
# QP-1: _CONTEXT_THREADABLE_FIELDS auto-threading
# ---------------------------------------------------------------------------

class TestQP1JavaFieldThreading:
    """REQ-PLI-301: Java fields in _CONTEXT_THREADABLE_FIELDS."""

    def test_java_fields_in_threadable(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            _CONTEXT_THREADABLE_FIELDS,
        )
        assert "java_package" in _CONTEXT_THREADABLE_FIELDS
        assert "build_system" in _CONTEXT_THREADABLE_FIELDS
        assert "java_version" in _CONTEXT_THREADABLE_FIELDS


# ---------------------------------------------------------------------------
# ParsedFeature Java fields
# ---------------------------------------------------------------------------

class TestParsedFeatureJavaFields:
    """REQ-PLI-700: Java fields on ParsedFeature."""

    def test_defaults(self):
        f = ParsedFeature(feature_id="F-001", name="test")
        assert f.java_package == ""
        assert f.build_system == ""
        assert f.java_version == ""
        assert f.spring_boot is False

    def test_explicit_values(self):
        f = ParsedFeature(
            feature_id="F-001",
            name="test",
            java_package="com.example.svc",
            build_system="gradle",
            java_version="21",
            spring_boot=True,
        )
        assert f.java_package == "com.example.svc"
        assert f.build_system == "gradle"
        assert f.java_version == "21"
        assert f.spring_boot is True


# ---------------------------------------------------------------------------
# SeedTask Java fields
# ---------------------------------------------------------------------------

class TestSeedTaskJavaFields:
    """REQ-PLI-701: Java fields on SeedTask."""

    def test_defaults(self):
        from startd8.seeds.models import SeedTask
        entry = {
            "task_id": "PI-001",
            "title": "Test task",
            "config": {"context": {}},
        }
        task = SeedTask.from_seed_entry(entry)
        assert task.java_package == ""
        assert task.build_system == ""
        assert task.java_version == ""

    def test_from_context(self):
        from startd8.seeds.models import SeedTask
        entry = {
            "task_id": "PI-001",
            "title": "Test task",
            "config": {
                "context": {
                    "java_package": "com.example.svc",
                    "build_system": "maven",
                    "java_version": "17",
                },
            },
        }
        task = SeedTask.from_seed_entry(entry)
        assert task.java_package == "com.example.svc"
        assert task.build_system == "maven"
        assert task.java_version == "17"


# ---------------------------------------------------------------------------
# lang_detect mappings
# ---------------------------------------------------------------------------

class TestLangDetectMultiLanguage:
    """REQ-PLI-100/101: Node.js and Java filename detection."""

    def test_nodejs_extensions(self):
        from startd8.micro_prime.lang_detect import detect_language
        assert detect_language("app.js") == "nodejs"
        assert detect_language("app.mjs") == "nodejs"
        assert detect_language("app.cjs") == "nodejs"
        assert detect_language("app.ts") == "nodejs"
        assert detect_language("app.tsx") == "nodejs"
        assert detect_language("app.jsx") == "nodejs"

    def test_java_filename(self):
        from startd8.micro_prime.lang_detect import detect_language
        assert detect_language("App.java") == "java"

    def test_build_gradle_filename(self):
        from startd8.micro_prime.lang_detect import detect_language
        assert detect_language("build.gradle") == "java"
        assert detect_language("build.gradle.kts") == "java"
        assert detect_language("settings.gradle") == "java"
        assert detect_language("pom.xml") == "java"

    def test_package_json_filename(self):
        from startd8.micro_prime.lang_detect import detect_language
        assert detect_language("package.json") == "nodejs"

    def test_go_unchanged(self):
        from startd8.micro_prime.lang_detect import detect_language
        assert detect_language("main.go") == "go"

    def test_python_unchanged(self):
        from startd8.micro_prime.lang_detect import detect_language
        assert detect_language("app.py") == "python"


# ---------------------------------------------------------------------------
# _infer_service_metadata() — Node.js features
# ---------------------------------------------------------------------------

class TestInferServiceMetadataNodejs:
    """REQ-PLI-300: Node.js metadata inference."""

    def _infer(self, features, onboarding=None):
        from startd8.seeds.derivation import infer_service_metadata
        return infer_service_metadata(features, onboarding)

    def test_module_system_esm_from_feature(self):
        feat = _FakeFeature(
            target_files=["src/server.js"],
            module_system="esm",
        )
        meta = self._infer([feat])
        assert meta["module_system"] == "esm"

    def test_module_system_commonjs_from_feature(self):
        feat = _FakeFeature(
            target_files=["src/server.js"],
            module_system="commonjs",
        )
        meta = self._infer([feat])
        assert meta["module_system"] == "commonjs"

    def test_module_system_inferred_from_mjs(self):
        feat = _FakeFeature(
            target_files=["src/server.mjs"],
        )
        meta = self._infer([feat])
        assert meta["module_system"] == "esm"

    def test_module_system_inferred_from_cjs(self):
        feat = _FakeFeature(
            target_files=["src/server.cjs"],
        )
        meta = self._infer([feat])
        assert meta["module_system"] == "commonjs"

    def test_module_system_default_esm(self):
        feat = _FakeFeature(
            target_files=["src/server.js"],
        )
        meta = self._infer([feat])
        assert meta["module_system"] == "esm"

    def test_node_version_default(self):
        feat = _FakeFeature(
            target_files=["src/server.js"],
        )
        meta = self._infer([feat])
        assert meta["node_version"] == "20"

    def test_node_version_from_feature(self):
        feat = _FakeFeature(
            target_files=["src/server.js"],
            node_version="18",
        )
        meta = self._infer([feat])
        assert meta["node_version"] == "18"

    def test_node_version_from_onboarding(self):
        feat = _FakeFeature(
            target_files=["src/server.js"],
        )
        meta = self._infer([feat], onboarding={"node_version": "22"})
        assert meta["node_version"] == "22"

    def test_primary_language_nodejs(self):
        feat = _FakeFeature(
            target_files=["src/server.js"],
        )
        meta = self._infer([feat])
        assert meta["primary_language"] == "nodejs"

    def test_typescript_triggers_nodejs(self):
        """TypeScript files should trigger Node.js metadata inference."""
        feat = _FakeFeature(
            target_files=["src/server.ts"],
        )
        meta = self._infer([feat])
        # Both .ts and .js now map to canonical "nodejs" language_id
        assert meta["primary_language"] == "nodejs"
        # Node.js metadata should be inferred
        assert "module_system" in meta

    def test_mixed_js_ts_triggers_nodejs(self):
        """Mixed JS+TS projects share 'nodejs' language_id — single primary."""
        feat1 = _FakeFeature(target_files=["src/server.js"])
        feat2 = _FakeFeature(target_files=["src/types.ts"])
        meta = self._infer([feat1, feat2])
        # Both .js and .ts map to "nodejs" — single language, not a list
        assert meta["primary_language"] == "nodejs"
        # Node.js metadata should be inferred
        assert "module_system" in meta

    def test_no_nodejs_metadata_for_go(self):
        feat = _FakeFeature(
            target_files=["src/main.go"],
            module_path="github.com/org/repo",
        )
        meta = self._infer([feat])
        assert "module_system" not in meta
        assert "node_version" not in meta


# ---------------------------------------------------------------------------
# QP-1: Node.js fields in _CONTEXT_THREADABLE_FIELDS
# ---------------------------------------------------------------------------

class TestQP1NodejsFieldThreading:
    """REQ-PLI-301: Node.js fields in _CONTEXT_THREADABLE_FIELDS."""

    def test_nodejs_fields_in_threadable(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            _CONTEXT_THREADABLE_FIELDS,
        )
        assert "module_system" in _CONTEXT_THREADABLE_FIELDS
        assert "node_version" in _CONTEXT_THREADABLE_FIELDS


# ---------------------------------------------------------------------------
# ParsedFeature Node.js fields
# ---------------------------------------------------------------------------

class TestParsedFeatureNodejsFields:
    """REQ-PLI-700: Node.js fields on ParsedFeature."""

    def test_defaults(self):
        f = ParsedFeature(feature_id="F-001", name="test")
        assert f.module_system == ""
        assert f.node_version == ""

    def test_explicit_values(self):
        f = ParsedFeature(
            feature_id="F-001",
            name="test",
            module_system="esm",
            node_version="20",
        )
        assert f.module_system == "esm"
        assert f.node_version == "20"


# ---------------------------------------------------------------------------
# SeedTask Node.js fields
# ---------------------------------------------------------------------------

class TestSeedTaskNodejsFields:
    """REQ-PLI-701: Node.js fields on SeedTask."""

    def test_defaults(self):
        from startd8.seeds.models import SeedTask
        entry = {
            "task_id": "PI-001",
            "title": "Test task",
            "config": {"context": {}},
        }
        task = SeedTask.from_seed_entry(entry)
        assert task.module_system == ""
        assert task.node_version == ""

    def test_from_context(self):
        from startd8.seeds.models import SeedTask
        entry = {
            "task_id": "PI-001",
            "title": "Test task",
            "config": {
                "context": {
                    "module_system": "commonjs",
                    "node_version": "18",
                },
            },
        }
        task = SeedTask.from_seed_entry(entry)
        assert task.module_system == "commonjs"
        assert task.node_version == "18"


# ---------------------------------------------------------------------------
# REQ-PLI-202: _detect_plan_language()
# ---------------------------------------------------------------------------

class TestDetectPlanLanguage:
    """REQ-PLI-202: Pre-PARSE language detection from plan text."""

    def _detect(self, text):
        from startd8.workflows.builtin.plan_ingestion_workflow import _detect_plan_language
        return _detect_plan_language(text)

    def test_go_project(self):
        text = """
        # Online Boutique Go Services
        Implement the shippingservice in Go. The service uses gRPC
        and reads from go.mod for dependencies. Files: main.go, handler.go
        """
        assert self._detect(text) == "go"

    def test_java_project(self):
        text = """
        # Order Service (Java Spring Boot)
        Implement the OrderService using Spring Boot and JPA.
        Build with Gradle (build.gradle). Java 21.
        Files: OrderService.java, OrderRepository.java
        """
        assert self._detect(text) == "java"

    def test_nodejs_project(self):
        text = """
        # Currency Service (Node.js)
        Implement the currency conversion service using Express.
        Dependencies in package.json. Files: server.js, converter.ts
        """
        assert self._detect(text) == "nodejs"

    def test_python_project(self):
        text = """
        # Recommendation Engine (Python)
        Implement using Flask and pytest. Dependencies in requirements.txt.
        Files: app.py, recommender.py, test_recommender.py
        """
        assert self._detect(text) == "python"

    def test_ambiguous_returns_none(self):
        text = "Implement a microservice with REST API endpoints."
        assert self._detect(text) is None

    def test_empty_returns_none(self):
        assert self._detect("") is None


# ---------------------------------------------------------------------------
# REQ-PLI-201: _build_parse_prompt() structure
# ---------------------------------------------------------------------------

class TestBuildParsePrompt:
    """REQ-PLI-201: Language-agnostic PARSE prompt with extensions."""

    def _build(self, plan_text):
        from startd8.workflows.builtin.plan_ingestion_workflow import _build_parse_prompt
        return _build_parse_prompt(plan_text)

    def test_always_includes_all_language_schemas(self):
        prompt = self._build("Implement a simple utility.")
        assert "module_path" in prompt  # Go
        assert "java_package" in prompt  # Java
        assert "module_system" in prompt  # Node.js

    def test_always_includes_all_language_guidance(self):
        prompt = self._build("Implement a simple utility.")
        assert "Go projects only" in prompt
        assert "Java projects only" in prompt
        assert "Node.js projects only" in prompt

    def test_go_plan_gets_hint(self):
        prompt = self._build("Implement Go gRPC service with go.mod")
        assert "Detected language: go" in prompt

    def test_java_plan_gets_hint(self):
        prompt = self._build("Spring Boot Java service with build.gradle and JPA")
        assert "Detected language: java" in prompt

    def test_nodejs_plan_gets_hint(self):
        prompt = self._build("Node.js Express service with package.json")
        assert "Detected language: nodejs" in prompt

    def test_python_plan_no_hint(self):
        """Python is the default — no special hint needed."""
        prompt = self._build("Python Flask app with pytest and requirements.txt")
        assert "Detected language:" not in prompt

    def test_go_plan_gets_dep_ordering(self):
        prompt = self._build("Implement Go gRPC service with go.mod")
        assert "Go dependency ordering" in prompt

    def test_java_plan_gets_dep_ordering(self):
        prompt = self._build("Spring Boot Java service with build.gradle and JPA")
        assert "Java dependency ordering" in prompt

    def test_ambiguous_plan_no_hint(self):
        prompt = self._build("Implement a REST API service.")
        assert "Detected language:" not in prompt
        # But all language fields are still present
        assert "module_path" in prompt
