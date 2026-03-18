"""Tests for Java disk validators in forward_manifest_validator.py (Phase 1)."""

import pytest
from startd8.forward_manifest_validator import (
    _validate_java_file,
    _validate_build_gradle,
    DiskComplianceResult,
)


VALID_JAVA = """\
package com.example;

import java.util.List;

public class Example {
    private String name;

    public Example(String name) {
        this.name = name;
    }
}
"""

INVALID_JAVA_PYTHON = """\
def hello():
    print("hello")
"""

INVALID_JAVA_NO_TYPE = """\
package com.example;
// just a comment, no type here
"""

NO_PACKAGE_JAVA = """\
import java.util.List;

public class NoPackage {
    public void doWork() {}
}
"""

VALID_GRADLE = """\
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter:3.2.0'
}
"""

GRADLE_NO_PLUGINS = """\
repositories {
    mavenCentral()
}

dependencies {
    implementation 'com.google.guava:guava:33.0.0-jre'
}
"""

GRADLE_PYTHON_CONTENT = """\
def hello():
    print("hi")
"""


class TestValidateJavaFile:

    def _make_result(self):
        return DiskComplianceResult(file_path="Test.java")

    def test_valid_java(self):
        result = _validate_java_file(VALID_JAVA, self._make_result())
        assert result.error is None or result.error == ""
        assert result.contract_compliance >= 0.7

    def test_python_fingerprint_rejected(self):
        result = _validate_java_file(INVALID_JAVA_PYTHON, self._make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert "fingerprint" in (result.error or "").lower()

    def test_no_type_declaration_warning(self):
        result = _validate_java_file(INVALID_JAVA_NO_TYPE, self._make_result())
        assert any(
            "no type declaration" in str(issue).lower()
            for issue in result.semantic_issues
        )

    def test_missing_package_warning(self):
        result = _validate_java_file(NO_PACKAGE_JAVA, self._make_result())
        assert any(
            "missing package" in str(issue).lower()
            for issue in result.semantic_issues
        )

    def test_unbalanced_braces(self):
        code = "package com.example;\npublic class Bad {\n"
        result = _validate_java_file(code, self._make_result())
        # May fail via javalang or text fallback
        assert result.ast_valid is False or len(result.semantic_issues) > 0


class TestValidateBuildGradle:

    def _make_result(self):
        return DiskComplianceResult(file_path="build.gradle")

    def test_valid_gradle(self):
        result = _validate_build_gradle(VALID_GRADLE, self._make_result())
        assert result.error is None or result.error == ""
        assert result.contract_compliance >= 0.7

    def test_missing_plugins(self):
        result = _validate_build_gradle(GRADLE_NO_PLUGINS, self._make_result())
        assert any(
            "missing plugins" in str(issue).lower()
            for issue in result.semantic_issues
        )

    def test_python_content_rejected(self):
        result = _validate_build_gradle(GRADLE_PYTHON_CONTENT, self._make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0

    def test_no_dependencies_info(self):
        code = "plugins {\n    id 'java'\n}\n"
        result = _validate_build_gradle(code, self._make_result())
        assert any(
            "no dependencies" in str(issue).lower()
            for issue in result.semantic_issues
        )
