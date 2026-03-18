"""Tests for Java framework detection (Phase 5)."""

import pytest
from startd8.languages.java import JavaLanguageProfile


class TestJavaFrameworkImports:

    def _profile(self):
        return JavaLanguageProfile()

    def test_spring_boot_present(self):
        fw = self._profile().framework_imports
        assert "spring_boot" in fw

    def test_spring_boot_detect_keywords(self):
        fw = self._profile().framework_imports["spring_boot"]
        assert "@SpringBootApplication" in fw["detect"]
        assert "spring-boot-starter" in fw["detect"]

    def test_jpa_present(self):
        fw = self._profile().framework_imports
        assert "jpa" in fw

    def test_jpa_detect_keywords(self):
        fw = self._profile().framework_imports["jpa"]
        assert "@Entity" in fw["detect"]
        assert "jakarta.persistence" in fw["detect"]

    def test_slf4j_present(self):
        fw = self._profile().framework_imports
        assert "slf4j" in fw

    def test_slf4j_detect_keywords(self):
        fw = self._profile().framework_imports["slf4j"]
        assert "LoggerFactory" in fw["detect"]

    def test_grpc_still_present(self):
        fw = self._profile().framework_imports
        assert "grpc" in fw

    def test_multiple_frameworks_detectable(self):
        """All frameworks should have non-overlapping detect keywords."""
        fw = self._profile().framework_imports
        all_detects = set()
        for name, spec in fw.items():
            for keyword in spec["detect"]:
                assert keyword not in all_detects or keyword in ("logging",), \
                    f"Duplicate detect keyword: {keyword}"
                all_detects.add(keyword)

    def test_structure_valid(self):
        """Each framework entry should have detect, dep_names, imports, conditional."""
        fw = self._profile().framework_imports
        for name, spec in fw.items():
            assert "detect" in spec, f"Missing detect in {name}"
            assert "dep_names" in spec, f"Missing dep_names in {name}"
            assert "imports" in spec, f"Missing imports in {name}"
            assert "conditional" in spec, f"Missing conditional in {name}"


class TestJavaFrameworkDetectionInSpec:
    """Tests for detect_java_frameworks() in spec_builder."""

    def test_spring_boot_detected(self):
        from startd8.implementation_engine.spec_builder import detect_java_frameworks
        context = {"description": "Build a @SpringBootApplication REST API"}
        frameworks = detect_java_frameworks(context)
        assert any("Spring Boot" in f for f in frameworks)

    def test_jpa_detected(self):
        from startd8.implementation_engine.spec_builder import detect_java_frameworks
        context = {"description": "Create @Entity classes with jakarta.persistence"}
        frameworks = detect_java_frameworks(context)
        assert any("JPA" in f for f in frameworks)

    def test_no_framework(self):
        from startd8.implementation_engine.spec_builder import detect_java_frameworks
        context = {"description": "Build a simple utility class"}
        frameworks = detect_java_frameworks(context)
        assert frameworks == []

    def test_multiple_frameworks(self):
        from startd8.implementation_engine.spec_builder import detect_java_frameworks
        context = {"description": "Spring Boot app with @Entity and LoggerFactory"}
        frameworks = detect_java_frameworks(context)
        assert len(frameworks) >= 2
