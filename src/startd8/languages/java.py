"""JavaLanguageProfile — Java language support for Prime Contractor.

Most complex dependency file generation (Gradle), lowest payoff (1 service).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# ~55 Java keywords + contextual keywords (Java 17+)
_JAVA_RESERVED: frozenset[str] = frozenset({
    # Standard keywords
    "abstract", "assert", "boolean", "break", "byte", "case", "catch",
    "char", "class", "const", "continue", "default", "do", "double",
    "else", "enum", "extends", "final", "finally", "float", "for",
    "goto", "if", "implements", "import", "instanceof", "int",
    "interface", "long", "native", "new", "package", "private",
    "protected", "public", "return", "short", "static", "strictfp",
    "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while",
    # Contextual keywords (Java 10+/14+/17+)
    "var", "yield", "record", "sealed", "permits", "non-sealed",
    # Literals that act as keywords
    "true", "false", "null",
})


def _java_literal_coerce(value: object) -> str:
    """Coerce a Python literal to Java syntax.

    ``True`` → ``true``, ``None`` → ``null``, ``[1, 2]`` → ``List.of(1, 2)``.
    """
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, list):
        items = ", ".join(_java_literal_coerce(v) for v in value)
        return f"List.of({items})"
    if isinstance(value, dict):
        entries = ", ".join(
            f"{_java_literal_coerce(k)}, {_java_literal_coerce(v)}"
            for k, v in value.items()
        )
        return f"Map.of({entries})"
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


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
            "spring_boot": {
                "detect": [
                    "@SpringBootApplication", "spring-boot-starter",
                    "SpringApplication", "spring-boot",
                ],
                "dep_names": {
                    "org.springframework.boot:spring-boot-starter",
                    "org.springframework.boot:spring-boot-starter-web",
                },
                "imports": [
                    "import org.springframework.boot.SpringApplication;",
                    "import org.springframework.boot.autoconfigure.SpringBootApplication;",
                ],
                "conditional": {},
            },
            "jpa": {
                "detect": [
                    "@Entity", "jakarta.persistence", "javax.persistence",
                    "JpaRepository", "CrudRepository",
                ],
                "dep_names": {
                    "org.springframework.boot:spring-boot-starter-data-jpa",
                    "jakarta.persistence:jakarta.persistence-api",
                },
                "imports": [
                    "import jakarta.persistence.Entity;",
                    "import jakarta.persistence.Id;",
                    "import jakarta.persistence.GeneratedValue;",
                ],
                "conditional": {},
            },
            "slf4j": {
                "detect": ["SLF4J", "LoggerFactory", "slf4j", "@Slf4j"],
                "dep_names": {"org.slf4j:slf4j-api"},
                "imports": [
                    "import org.slf4j.Logger;",
                    "import org.slf4j.LoggerFactory;",
                ],
                "conditional": {},
            },
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
                "detect": ["log4j", "logging"],
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

    @property
    def stub_patterns(self) -> List[str]:
        return [
            r'throw\s+new\s+UnsupportedOperationException\s*\(',
            r'throw\s+new\s+RuntimeException\s*\(\s*"not implemented',
            r'throw\s+new\s+RuntimeException\s*\(\s*"TODO',
            r'^\s*//\s*TODO\b',
        ]

    @property
    def function_start_pattern(self) -> Optional[str]:
        return r'^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:\w+\s+)?(?P<name>[A-Za-z_]\w*)\s*\('

    def get_stdlib_prefixes(self) -> Sequence[str]:
        return _JAVA_STDLIB_PREFIXES

    def post_generation_cleanup(self, files: List[Path], project_root: Path) -> List[str]:
        # Java has no authoritative import fixer callable from CLI.
        # google-java-format could format but requires java runtime.
        return []

    def validate_syntax(self, code: str) -> tuple[bool, str]:
        """Java syntax validation via javalang parser (with text-based fallback)."""
        return _validate_java_syntax(code)

    def generate_dependency_file(
        self,
        project_root: Path,
        service_name: str,
        module_path: str,
        dependencies: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Generate build.gradle content from service metadata."""
        java_version = "21"
        if metadata:
            java_version = str(metadata.get("java_version", java_version))

        lines = [
            "plugins {",
            "    id 'java'",
            "    id 'application'",
            "}",
            "",
            "java {",
            f"    sourceCompatibility = JavaVersion.VERSION_{java_version}",
            f"    targetCompatibility = JavaVersion.VERSION_{java_version}",
            "}",
            "",
            "repositories {",
            "    mavenCentral()",
            "}",
            "",
        ]

        if dependencies:
            lines.append("dependencies {")
            for dep in dependencies:
                dep = dep.strip()
                if not dep:
                    continue
                # Assume Gradle coordinate format: group:artifact:version
                lines.append(f"    implementation '{dep}'")
            lines.append("}")
            lines.append("")

        if module_path:
            lines.append(f"application {{")
            lines.append(f"    mainClass = '{module_path}'")
            lines.append("}")
            lines.append("")

        return "\n".join(lines)


_JAVA_STDLIB_PREFIXES: tuple[str, ...] = (
    "java.", "javax.", "jdk.", "sun.",
)


# Python fingerprints — if these appear in a .java file, it's cross-language contamination.
_PYTHON_FINGERPRINTS = (
    "def ", "import os", "from __future__", "print(", "self.",
    "#!/usr/bin/env python", "#!/usr/bin/python",
)

# Java type declaration patterns (class, interface, enum, record, @interface)
_JAVA_TYPE_DECL_RE = re.compile(
    r"\b(?:class|interface|enum|record|@interface)\s+\w+",
)


def _validate_java_syntax(code: str) -> tuple[bool, str]:
    """Validate Java source via javalang AST parser; fall back to text heuristics.

    Returns ``(True, "")`` on success or ``(False, error_message)`` on failure.
    """
    # Try javalang first
    try:
        import javalang
        try:
            javalang.parse.parse(code)
            return True, ""
        except javalang.parser.JavaSyntaxError as exc:
            return False, f"javalang syntax error: {exc}"
        except javalang.tokenizer.LexerError as exc:
            return False, f"javalang lexer error: {exc}"
    except ImportError:
        pass  # Fall through to text-based validation

    # Text-based fallback (when javalang is not installed)
    return _text_based_java_validate(code)


def _text_based_java_validate(code: str) -> tuple[bool, str]:
    """Lightweight text-based Java validation (no javalang dependency).

    Checks:
    1. Balanced braces
    2. Contains at least one type declaration (class/interface/enum/record)
    3. No Python fingerprints
    """
    # Check for Python fingerprints
    for fp in _PYTHON_FINGERPRINTS:
        if fp in code:
            return False, f"Python fingerprint detected: {fp!r}"

    # Balanced braces
    depth = 0
    for ch in code:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False, "unbalanced braces (extra closing brace)"
    if depth != 0:
        return False, f"unbalanced braces (depth={depth})"

    # Must contain a type declaration
    if not _JAVA_TYPE_DECL_RE.search(code):
        return False, "no type declaration found (class/interface/enum/record)"

    return True, ""
