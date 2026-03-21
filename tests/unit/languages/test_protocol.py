"""Tests for LanguageProfile protocol satisfaction (duck typing)."""

import pytest

from startd8.languages.protocol import LanguageProfile
from startd8.languages.python import PythonLanguageProfile
from startd8.languages.go import GoLanguageProfile
from startd8.languages.nodejs import NodeLanguageProfile
from startd8.languages.java import JavaLanguageProfile


@pytest.mark.unit
class TestProtocolSatisfaction:
    """Every language profile must satisfy the LanguageProfile protocol."""

    @pytest.mark.parametrize("profile_cls", [
        PythonLanguageProfile,
        GoLanguageProfile,
        NodeLanguageProfile,
        JavaLanguageProfile,
    ])
    def test_isinstance_check(self, profile_cls):
        """Profile instances pass runtime_checkable isinstance check."""
        profile = profile_cls()
        assert isinstance(profile, LanguageProfile)

    @pytest.mark.parametrize("profile_cls,expected_id", [
        (PythonLanguageProfile, "python"),
        (GoLanguageProfile, "go"),
        (NodeLanguageProfile, "nodejs"),
        (JavaLanguageProfile, "java"),
    ])
    def test_language_id(self, profile_cls, expected_id):
        assert profile_cls().language_id == expected_id

    @pytest.mark.parametrize("profile_cls", [
        PythonLanguageProfile,
        GoLanguageProfile,
        NodeLanguageProfile,
        JavaLanguageProfile,
    ])
    def test_required_properties_are_non_empty(self, profile_cls):
        """All required properties return non-empty values."""
        p = profile_cls()
        assert p.display_name
        assert len(p.source_extensions) > 0
        assert len(p.build_file_patterns) > 0
        assert p.system_prompt_role
        assert p.coding_standards
        assert p.merge_strategy_preference
        assert p.docker_base_image
        assert p.docker_runtime_image
        assert len(p.blast_radius_extensions) > 0

    @pytest.mark.parametrize("profile_cls", [
        PythonLanguageProfile,
        GoLanguageProfile,
        NodeLanguageProfile,
        JavaLanguageProfile,
    ])
    def test_supports_own_extensions(self, profile_cls):
        """Profile supports its own declared extensions."""
        p = profile_cls()
        for ext in p.source_extensions:
            assert p.supports_extension(ext), f"{p.language_id} should support {ext}"

    @pytest.mark.parametrize("profile_cls", [
        PythonLanguageProfile,
        GoLanguageProfile,
        NodeLanguageProfile,
        JavaLanguageProfile,
    ])
    def test_get_import_patterns_returns_list(self, profile_cls):
        """get_import_patterns returns a non-empty list of strings."""
        p = profile_cls()
        patterns = p.get_import_patterns("mymodule")
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        for pat in patterns:
            assert isinstance(pat, str)
            assert "mymodule" in pat

    @pytest.mark.parametrize("profile_cls", [
        PythonLanguageProfile,
        GoLanguageProfile,
        NodeLanguageProfile,
        JavaLanguageProfile,
    ])
    def test_get_stdlib_prefixes_returns_sequence(self, profile_cls):
        p = profile_cls()
        prefixes = p.get_stdlib_prefixes()
        assert len(prefixes) > 0


@pytest.mark.unit
class TestPythonProfile:
    """Python-specific profile tests."""

    def test_syntax_command_uses_py_compile(self):
        p = PythonLanguageProfile()
        cmd = p.syntax_check_command
        assert cmd is not None
        assert "py_compile" in " ".join(cmd)
        assert "{file}" in cmd

    def test_lint_command_uses_ruff(self):
        p = PythonLanguageProfile()
        cmd = p.lint_command
        assert cmd is not None
        assert "ruff" in " ".join(cmd)

    def test_repair_enabled(self):
        assert PythonLanguageProfile().repair_enabled is True

    def test_merge_strategy_prefers_ast(self):
        assert PythonLanguageProfile().merge_strategy_preference == "ast"

    def test_framework_imports_contain_grpc(self):
        p = PythonLanguageProfile()
        assert "grpc" in p.framework_imports

    def test_package_alias_map_contains_grpcio(self):
        p = PythonLanguageProfile()
        assert "grpcio" in p.package_alias_map


@pytest.mark.unit
class TestGoProfile:

    def test_syntax_uses_gofmt(self):
        p = GoLanguageProfile()
        cmd = p.syntax_check_command
        assert cmd is not None
        assert "gofmt" in cmd[0]
        assert "{file}" in cmd

    def test_lint_is_none(self):
        """go vet requires go.mod — lint is disabled at per-file level."""
        p = GoLanguageProfile()
        assert p.lint_command is None

    def test_repair_enabled(self):
        assert GoLanguageProfile().repair_enabled is True

    def test_merge_strategy_simple(self):
        assert GoLanguageProfile().merge_strategy_preference == "simple"

    def test_does_not_support_py(self):
        assert GoLanguageProfile().supports_extension(".py") is False


@pytest.mark.unit
class TestNodeProfile:

    def test_supports_js_mjs_cjs(self):
        p = NodeLanguageProfile()
        assert p.supports_extension(".js")
        assert p.supports_extension(".mjs")
        assert p.supports_extension(".cjs")

    def test_syntax_uses_node_check(self):
        p = NodeLanguageProfile()
        cmd = p.syntax_check_command
        assert cmd is not None
        assert "node" in cmd[0]
        assert "--check" in cmd


@pytest.mark.unit
class TestJavaProfile:

    def test_supports_java(self):
        assert JavaLanguageProfile().supports_extension(".java")

    def test_repair_enabled(self):
        assert JavaLanguageProfile().repair_enabled is True

    def test_build_files_include_gradle(self):
        p = JavaLanguageProfile()
        assert "build.gradle" in p.build_file_patterns
