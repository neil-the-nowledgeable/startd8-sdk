"""JavaLanguageProfile — Java language support for Prime Contractor.

Most complex dependency file generation (Gradle), lowest payoff (1 service).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ._validation_utils import check_balanced_braces


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
        return [
            "build.gradle", "settings.gradle", "pom.xml", "build.gradle.kts",
            "gradle-wrapper.properties", "settings.gradle.kts",
        ]

    @property
    def syntax_check_command(self) -> Optional[List[str]]:
        # Java cannot validate single files via subprocess — `gradle compileJava`
        # requires a complete project (build.gradle, resolved dependencies).
        # Per-file validation is handled by validate_syntax() using javalang.
        return None

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
            "No wildcard imports. "
            "SECURITY: Use PreparedStatement for ALL SQL — "
            "NEVER use String concatenation or String.format() in SQL strings. "
            "LOGGING: Use SLF4J (LoggerFactory.getLogger(ClassName.class)) — "
            "NEVER use System.out.println() or System.err.println() for logging. "
            "INTERFACES: Interface files MUST contain ONLY the interface definition, not implementations."
        )

    def sanitize_code_examples(self, text: str) -> str:
        """REQ-TDE-202: Transform Java anti-patterns in code examples.

        System.out.println → logger.info
        System.err.println → logger.error
        """
        text = re.sub(
            r'System\.err\.println\s*\(([^)]*)\)',
            r'logger.error(\1)',
            text,
        )
        text = re.sub(
            r'System\.out\.println\s*\(([^)]*)\)',
            r'logger.info(\1)',
            text,
        )
        return text

    @property
    def merge_strategy_preference(self) -> str:
        return "simple"

    @property
    def repair_enabled(self) -> bool:
        return True

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


    def derive_service_metadata(
        self,
        features: Sequence[Any],
        *,
        onboarding: Optional[Dict[str, Any]] = None,
        api_signatures: Optional[List[str]] = None,
        runtime_dependencies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Derive Java-specific service metadata from plan features.

        Extracts java_package, build_system, java_version, and spring_boot.
        """
        metadata: Dict[str, Any] = {}
        all_api_sigs = api_signatures or []
        all_runtime_deps = runtime_dependencies or []

        # java_package: derive from feature attribute or target file paths
        java_packages: list[str] = []
        for f in features:
            jp = getattr(f, "java_package", "")
            if jp:
                java_packages.append(jp)
        if java_packages:
            metadata["java_package"] = java_packages[0]
        else:
            for f in features:
                for tf in getattr(f, "target_files", []):
                    if tf.endswith(".java"):
                        from startd8.utils.java_file_assembler import _derive_package
                        pkg = _derive_package(tf)
                        if pkg:
                            metadata["java_package"] = pkg
                            break
                if "java_package" in metadata:
                    break

        # build_system
        build_systems: list[str] = []
        for f in features:
            bs = getattr(f, "build_system", "")
            if bs:
                build_systems.append(bs)
        if build_systems:
            metadata["build_system"] = build_systems[0]
        else:
            all_files = [tf for f in features for tf in getattr(f, "target_files", [])]
            if any("build.gradle" in tf or "build.gradle.kts" in tf for tf in all_files):
                metadata["build_system"] = "gradle"
            elif any("pom.xml" in tf for tf in all_files):
                metadata["build_system"] = "maven"
            else:
                metadata["build_system"] = "gradle"

        # java_version
        java_version = "21"
        for f in features:
            jv = getattr(f, "java_version", "")
            if jv:
                java_version = jv
                break
        if onboarding:
            java_version = str(onboarding.get("java_version", java_version))
        metadata["java_version"] = java_version

        # spring_boot detection
        for f in features:
            if getattr(f, "spring_boot", False):
                metadata["spring_boot"] = True
                break
        if "spring_boot" not in metadata:
            all_deps = " ".join(all_runtime_deps + all_api_sigs).lower()
            if "spring" in all_deps or "springboot" in all_deps:
                metadata["spring_boot"] = True

        return metadata

    def build_project_context_section(self, context: Dict[str, Any]) -> str:
        """Build Java project context section for correct package and import generation."""
        target_files = context.get("target_files") or []
        java_package = context.get("java_package", "")
        build_system = context.get("build_system", "")
        java_version = context.get("java_version", "21")

        # Check service_metadata
        svc_meta = context.get("service_metadata")
        if isinstance(svc_meta, dict):
            if not java_package:
                java_package = svc_meta.get("java_package", "")
            if not build_system:
                build_system = svc_meta.get("build_system", "")
        if not build_system:
            build_system = "gradle"

        # Derive package from target file if not provided
        if not java_package and target_files:
            for tf in target_files:
                if tf.endswith(".java"):
                    from startd8.utils.java_file_assembler import _derive_package
                    pkg = _derive_package(tf)
                    if pkg:
                        java_package = pkg
                        break

        # Derive class name from target file
        class_name = ""
        if target_files:
            from pathlib import PurePosixPath
            for tf in target_files:
                if tf.endswith(".java"):
                    class_name = PurePosixPath(tf).stem
                    break

        lines = [
            "## Java Project Context (CRITICAL — required for compilation)\n",
        ]
        if java_package:
            lines.append(f"- **Package**: `package {java_package};` (MUST be the first statement)")
        if class_name:
            lines.append(f"- **Public class**: `{class_name}` (MUST match filename)")
        lines.append(f"- **Java version**: {java_version}")
        lines.append(f"- **Build system**: {build_system.capitalize()}")

        lines.extend([
            "",
            "**Java import rules:**",
            "- Every import must be fully qualified (e.g. `import java.util.List;`)",
            "- Group imports: `java.*`/`javax.*` first, then blank line, then third-party",
            "- No wildcard imports (`import java.util.*`) — always explicit",
            "- Every import must end with `;`",
            "",
            "**Java structural rules (MANDATORY):**",
            "- One public class per file, class name MUST match filename",
            "- PascalCase for class names, camelCase for methods and fields",
            "- Explicit access modifiers on ALL classes, methods, and fields",
            "- Package declaration MUST match directory structure "
            "(e.g., `src/main/java/com/example/service/` → `package com.example.service;`)",
            "- Always annotate overridden methods with `@Override`",
            "- Prefer immutability — use `final` where possible",
            "- Use try-with-resources for ALL AutoCloseable resources "
            "(NEVER manually close in finally block)",
            "",
            "**Exception handling (MANDATORY):**",
            "- NEVER use empty catch blocks (`catch (Exception e) { }`)",
            "- Always log the exception: `logger.error(\"message\", e);`",
            "- Prefer catching specific exceptions over `catch (Exception e)`",
            "",
            "**Java service patterns (CRITICAL):**",
            "- Interface files MUST contain ONLY the interface definition — no implementations",
            "- Implementation classes go in their own files (e.g., RedisCartStore.java implements CartStore)",
            "- Use SLF4J (`LoggerFactory.getLogger(ClassName.class)`) for ALL logging — "
            "NEVER `System.out.println()`",
            "- Use `PreparedStatement` for ALL database access — "
            "NEVER String concatenation in SQL",
        ])

        return "\n".join(lines)

    def strip_dependency_version(self, dep: str) -> str:
        """Strip version from Java dependency. 'g:a:v' -> 'g:a'."""
        parts = dep.split(":")
        return ":".join(parts[:2]) if len(parts) >= 2 else dep.strip()

    def get_import_syntax_guidance(self) -> str:
        """Return Java import rules for LLM prompts."""
        return (
            "Use ONLY these packages plus Java stdlib (java.*/javax.*). Every\n"
            "class you reference MUST have a corresponding import statement.\n"
            "Use fully qualified imports (e.g. `import io.grpc.Server;`).\n"
            "No wildcard imports. Do NOT import packages not listed above.\n"
        )

    def extract_import_lines(self, source: str) -> list[str]:
        """Extract import statements from Java source (REQ-PE-400)."""
        import re
        imports: list[str] = []
        for m in re.finditer(r'^import\s+(?:static\s+)?[\w.]+\s*;', source, re.MULTILINE):
            imports.append(m.group(0))
        return imports

    @property
    def stub_marker_text(self) -> str:
        """Java stub marker for skeleton fill prompts."""
        return "`throw new UnsupportedOperationException()`"


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
    # Check for Python fingerprints (fast, catches cross-language contamination)
    for fp in _PYTHON_FINGERPRINTS:
        if fp in code:
            return False, f"Python fingerprint detected: {fp!r}"

    # Try javalang first
    try:
        import javalang
        try:
            tree = javalang.parse.parse(code)
            # Structural check: must contain at least one type declaration
            has_type = any(
                isinstance(node, (
                    javalang.tree.ClassDeclaration,
                    javalang.tree.InterfaceDeclaration,
                    javalang.tree.EnumDeclaration,
                ))
                for _, node in tree
                if hasattr(node, '__class__')
            )
            if not has_type:
                return False, "no type declaration found (class/interface/enum)"
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
    ok, msg = check_balanced_braces(code)
    if not ok:
        return False, msg

    # Must contain a type declaration
    if not _JAVA_TYPE_DECL_RE.search(code):
        return False, "no type declaration found (class/interface/enum/record)"

    return True, ""
