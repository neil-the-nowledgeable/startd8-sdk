"""JavaLanguageProfile — Java language support for Prime Contractor.

Most complex dependency file generation (Gradle), lowest payoff (1 service).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence


class JavaLanguageProfile:
    """Language profile for Java code generation."""

    @property
    def language_id(self) -> str:
        return "java"

    @property
    def display_name(self) -> str:
        return "Java"

    @property
    def source_extensions(self) -> List[str]:
        return [".java"]

    @property
    def build_file_patterns(self) -> List[str]:
        return ["build.gradle", "settings.gradle", "pom.xml", "build.gradle.kts"]

    @property
    def syntax_check_command(self) -> Optional[List[str]]:
        # Gradle compile is the primary validation path
        return ["gradle", "compileJava"]

    @property
    def lint_command(self) -> Optional[List[str]]:
        return None

    @property
    def test_command(self) -> Optional[List[str]]:
        return ["gradle", "test"]

    @property
    def framework_imports(self) -> Dict[str, dict]:
        return {
            "grpc": {
                "detect": ["grpc", "proto", "protobuf", "gRPC"],
                "dep_names": {"io.grpc:grpc-netty", "io.grpc:grpc-stub"},
                "imports": [
                    "import io.grpc.Server;",
                    "import io.grpc.ServerBuilder;",
                ],
                "conditional": {},
            },
            "logging": {
                "detect": ["log4j", "slf4j", "logging"],
                "dep_names": {"org.apache.logging.log4j:log4j-core"},
                "imports": [
                    "import org.apache.logging.log4j.LogManager;",
                    "import org.apache.logging.log4j.Logger;",
                ],
                "conditional": {},
            },
        }

    @property
    def package_alias_map(self) -> Dict[str, str]:
        return {}

    @property
    def cleanup_patterns(self) -> List[str]:
        return ["build/", ".gradle/", "target/", "*.class"]

    @property
    def blast_radius_extensions(self) -> List[str]:
        return [".java"]

    @property
    def import_pattern_template(self) -> str:
        return "import.*{module}"

    @property
    def system_prompt_role(self) -> str:
        return "an expert Java engineer"

    @property
    def coding_standards(self) -> str:
        return (
            "Java conventions: PascalCase classes, camelCase methods, explicit access "
            "modifiers. Prefer immutability. Use try-with-resources for AutoCloseable. "
            "No wildcard imports."
        )

    @property
    def merge_strategy_preference(self) -> str:
        return "simple"

    @property
    def repair_enabled(self) -> bool:
        return False

    @property
    def docker_base_image(self) -> str:
        return "eclipse-temurin:21-jdk"

    @property
    def docker_runtime_image(self) -> str:
        return "eclipse-temurin:21-jre-alpine"

    def supports_extension(self, ext: str) -> bool:
        return ext.lower() == ".java"

    def get_import_patterns(self, module_stem: str) -> List[str]:
        return [
            f"import {module_stem}",
            f"import static {module_stem}",
        ]

    def get_stdlib_prefixes(self) -> Sequence[str]:
        return _JAVA_STDLIB_PREFIXES


_JAVA_STDLIB_PREFIXES: tuple[str, ...] = (
    "java.", "javax.", "jdk.", "sun.",
)
