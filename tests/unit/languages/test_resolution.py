"""Tests for language resolution from file lists."""

import pytest

from startd8.languages.registry import LanguageRegistry
from startd8.languages.resolution import resolve_language


@pytest.fixture(autouse=True)
def clean_registry():
    LanguageRegistry.clear()
    LanguageRegistry.discover()
    yield
    LanguageRegistry.clear()


@pytest.mark.unit
class TestResolveLanguage:

    def test_python_files(self):
        profile = resolve_language(["src/emailservice/email_server.py"])
        assert profile.language_id == "python"

    def test_go_files(self):
        profile = resolve_language(["src/frontend/main.go", "src/frontend/handlers.go"])
        assert profile.language_id == "go"

    def test_js_files(self):
        profile = resolve_language(["src/currencyservice/server.js"])
        assert profile.language_id == "nodejs"

    def test_java_files(self):
        profile = resolve_language(["src/adservice/AdService.java"])
        assert profile.language_id == "java"

    def test_mixed_files_dominant_wins(self):
        """When files are mixed, the most common language wins."""
        profile = resolve_language([
            "src/service/main.go",
            "src/service/handler.go",
            "src/service/config.py",
        ])
        assert profile.language_id == "go"

    def test_empty_list_defaults_to_python(self):
        profile = resolve_language([])
        assert profile.language_id == "python"

    def test_none_defaults_to_python(self):
        profile = resolve_language(None)
        assert profile.language_id == "python"

    def test_unknown_extensions_default_to_python(self):
        profile = resolve_language(["Dockerfile", "README.md"])
        assert profile.language_id == "python"

    def test_dockerfile_with_go_files(self):
        """Dockerfile is ignored, Go wins."""
        profile = resolve_language([
            "Dockerfile",
            "src/service/main.go",
        ])
        assert profile.language_id == "go"

    def test_mjs_resolves_to_nodejs(self):
        profile = resolve_language(["src/service/index.mjs"])
        assert profile.language_id == "nodejs"

    def test_custom_default(self):
        profile = resolve_language([], default_id="go")
        assert profile.language_id == "go"

    # --- Build file resolution (go.mod, package.json, etc.) ---

    def test_go_mod_resolves_to_go(self):
        """go.mod should resolve to Go, not fall back to Python."""
        profile = resolve_language(["src/shippingservice/go.mod"])
        assert profile.language_id == "go"

    def test_package_json_resolves_to_nodejs(self):
        profile = resolve_language(["src/currencyservice/package.json"])
        assert profile.language_id == "nodejs"

    def test_build_gradle_resolves_to_java(self):
        profile = resolve_language(["src/adservice/build.gradle"])
        assert profile.language_id == "java"

    def test_dockerfile_alone_defaults_to_python(self):
        """Standalone Dockerfile with no sibling context → Python default."""
        profile = resolve_language(["src/shippingservice/Dockerfile"])
        assert profile.language_id == "python"

    def test_dockerfile_with_go_sibling_resolves_to_go(self):
        """Dockerfile alongside Go files in batch → Go."""
        profile = resolve_language([
            "src/shippingservice/Dockerfile",
            "src/shippingservice/main.go",
        ])
        assert profile.language_id == "go"

    def test_dockerfile_with_java_sibling_resolves_to_java(self):
        """Dockerfile in Java project with Java files in batch → Java."""
        profile = resolve_language([
            "src/adservice/Dockerfile",
            "src/adservice/src/main/java/hipstershop/AdService.java",
        ])
        assert profile.language_id == "java"

    def test_go_mod_with_go_files(self):
        """go.mod + .go files should still resolve to Go."""
        profile = resolve_language([
            "src/frontend/go.mod",
            "src/frontend/main.go",
        ])
        assert profile.language_id == "go"

    # --- Language-neutral file inference from siblings ---

    def test_html_with_go_sibling_resolves_to_go(self):
        """HTML template alongside .go files in same dir → Go."""
        profile = resolve_language([
            "src/frontend/templates/home.html",
            "src/frontend/templates/header.go",
        ])
        # .go sibling wins
        assert profile.language_id == "go"

    def test_standalone_html_defaults_to_python(self):
        """Lone HTML file with no context → Python default."""
        profile = resolve_language(["templates/home.html"])
        assert profile.language_id == "python"

    # --- batch_target_files cross-feature inference ---

    def test_dockerfile_with_java_batch_context(self):
        """Dockerfile alone with Java siblings in batch → Java."""
        profile = resolve_language(
            ["src/adservice/Dockerfile"],
            batch_target_files=[
                "src/adservice/build.gradle",
                "src/adservice/src/main/java/hipstershop/AdService.java",
                "src/adservice/Dockerfile",
            ],
        )
        assert profile.language_id == "java"

    def test_dockerfile_with_go_batch_context(self):
        """Dockerfile alone with Go siblings in batch → Go."""
        profile = resolve_language(
            ["src/shippingservice/Dockerfile"],
            batch_target_files=[
                "src/shippingservice/main.go",
                "src/shippingservice/Dockerfile",
            ],
        )
        assert profile.language_id == "go"

    def test_batch_context_ignored_when_extension_resolves(self):
        """Java file resolves by extension even with Go batch context."""
        profile = resolve_language(
            ["src/service/Main.java"],
            batch_target_files=[
                "src/service/main.go",
                "src/service/handler.go",
                "src/service/Main.java",
            ],
        )
        assert profile.language_id == "java"

    def test_dockerfile_in_frontend_service_resolves_to_go(self):
        """Dockerfile in a non-'service'-named Go dir with Go sibling."""
        profile = resolve_language([
            "src/frontend/Dockerfile",
            "src/frontend/main.go",
        ])
        assert profile.language_id == "go"

    # --- Java config/resource file resolution ---

    def test_gradle_wrapper_properties_resolves_to_java(self):
        """gradle-wrapper.properties is a Java build artifact."""
        profile = resolve_language(["src/adservice/gradle/wrapper/gradle-wrapper.properties"])
        assert profile.language_id == "java"

    def test_log4j2_xml_in_resources_resolves_to_java(self):
        """XML config under src/main/resources/ → Java."""
        profile = resolve_language(["src/adservice/src/main/resources/log4j2.xml"])
        assert profile.language_id == "java"

    def test_java_test_resources_resolves_to_java(self):
        """File under src/test/resources/ → Java."""
        profile = resolve_language(["src/service/src/test/resources/application-test.yml"])
        assert profile.language_id == "java"

    def test_settings_gradle_kts_resolves_to_java(self):
        """settings.gradle.kts is a Java/Kotlin build file."""
        profile = resolve_language(["src/service/settings.gradle.kts"])
        assert profile.language_id == "java"
