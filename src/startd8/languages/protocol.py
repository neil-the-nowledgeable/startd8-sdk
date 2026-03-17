"""LanguageProfile protocol — the extension point all language providers implement.

One monolithic protocol with ~15 properties/methods. Rationale: the pipeline
always needs all capabilities for a given language — you never need "Go
validation but Python prompts." If it grows too large later, extract then.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable


@runtime_checkable
class LanguageProfile(Protocol):
    """Defines language-specific behavior for code generation pipelines.

    Implementations provide:
    - File identification (extensions, build files)
    - Validation commands (syntax, lint, test)
    - Prompt fragments (system prompt role, coding standards)
    - Dependency management (framework imports, package aliases)
    - Cleanup patterns and merge strategy preferences
    """

    @property
    def language_id(self) -> str:
        """Unique identifier (e.g. 'python', 'go', 'nodejs', 'java')."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name (e.g. 'Python', 'Go', 'Node.js', 'Java')."""
        ...

    @property
    def source_extensions(self) -> List[str]:
        """Source file extensions including the dot (e.g. ['.py'], ['.go'])."""
        ...

    @property
    def build_file_patterns(self) -> List[str]:
        """Build/dependency file names (e.g. ['requirements.txt', 'pyproject.toml'])."""
        ...

    @property
    def syntax_check_command(self) -> Optional[List[str]]:
        """Command template for syntax validation.

        Use ``{file}`` as placeholder for the file path.
        Return None if the language has no standalone syntax check.
        Example: ``['python3', '-m', 'py_compile', '{file}']``
        """
        ...

    @property
    def lint_command(self) -> Optional[List[str]]:
        """Command template for linting.

        Use ``{file}`` as placeholder for the file path.
        Return None if no linter is available.
        Example: ``['python3', '-m', 'ruff', 'check', '{file}', '--select=E7,E9,F', '--output-format=concise']``
        """
        ...

    @property
    def test_command(self) -> Optional[List[str]]:
        """Command for running the project test suite.

        Return None if no test runner is configured.
        Example: ``['python3', '-m', 'pytest', '-v', '--tb=short', '-q']``
        """
        ...

    @property
    def framework_imports(self) -> Dict[str, dict]:
        """Framework import registry (same schema as FRAMEWORK_IMPORTS).

        Keys are framework identifiers, values have:
        - detect: list of keywords for detection
        - dep_names: set of dependency names
        - imports: list of import statements
        - conditional: dict of trigger_pkg -> import statements
        """
        ...

    @property
    def package_alias_map(self) -> Dict[str, str]:
        """Maps distribution/package names to import names.

        Example: {'grpcio': 'grpc', 'pyyaml': 'yaml'}
        """
        ...

    @property
    def cleanup_patterns(self) -> List[str]:
        """Directory/file patterns to clean up (e.g. ['__pycache__'])."""
        ...

    @property
    def blast_radius_extensions(self) -> List[str]:
        """File extensions to scan for blast radius (e.g. ['.py'])."""
        ...

    @property
    def import_pattern_template(self) -> str:
        """Regex-friendly pattern for detecting imports in source files.

        Use ``{module}`` as placeholder.
        Example for Python: ``'import {module}|from {module}'``
        Example for Go: ``'import.*"{module}"'``
        """
        ...

    @property
    def system_prompt_role(self) -> str:
        """Language-specific role for system prompts.

        Example: 'an expert Python engineer'
        """
        ...

    @property
    def coding_standards(self) -> str:
        """Language-specific coding standards for system prompts.

        Example: 'Ruff: no single-letter vars l/O/I; define helpers before use.'
        """
        ...

    @property
    def merge_strategy_preference(self) -> str:
        """Preferred merge strategy name (e.g. 'ast' for Python, 'simple' for others)."""
        ...

    @property
    def repair_enabled(self) -> bool:
        """Whether the repair pipeline should run for this language.

        Go has compile-time checks, so repair is less useful.
        """
        ...

    @property
    def docker_base_image(self) -> str:
        """Default Docker base image for this language.

        Example: 'python:3.12-slim'
        """
        ...

    @property
    def docker_runtime_image(self) -> str:
        """Default Docker runtime image (distroless/minimal).

        Example: 'python:3.12-slim' or 'gcr.io/distroless/static'
        """
        ...

    def supports_extension(self, ext: str) -> bool:
        """Check if this profile handles files with the given extension."""
        ...

    def get_import_patterns(self, module_stem: str) -> List[str]:
        """Return text patterns to search for when computing blast radius.

        Args:
            module_stem: The stem of the target file (without extension).

        Returns:
            List of string patterns to grep for in source files.
        """
        ...

    def get_stdlib_prefixes(self) -> Sequence[str]:
        """Return standard library top-level module names.

        Used to exclude stdlib imports from dependency alignment checks.
        """
        ...

    @property
    def stub_patterns(self) -> List[str]:
        """Regex patterns that indicate a function body is a stub.

        Each pattern is matched against individual lines within a function body.
        If any line matches, the function is considered a stub.

        Example for Go: ``[r'panic\\("not implemented"\\)', r'^\\s*//\\s*TODO']``
        """
        ...

    @property
    def function_start_pattern(self) -> Optional[str]:
        """Regex pattern that matches the start of a function/method declaration.

        Used for text-based stub detection in non-Python languages.
        The pattern should capture a ``name`` group.

        Example for Go: ``r'^func\\s+(?:\\(.*?\\)\\s+)?(?P<name>\\w+)\\s*\\('``
        """
        ...

    def post_generation_cleanup(self, files: List[Path], project_root: Path) -> List[str]:
        """Run language-specific cleanup on generated files before validation.

        Called after code generation, before checkpoint validation. Use for
        tools like ``goimports`` (Go) or ``prettier`` (Node.js) that
        authoritatively fix formatting and imports.

        Args:
            files: Generated source files to clean up.
            project_root: Project root for running tools.

        Returns:
            List of warning/info messages (empty if all succeeded).
        """
        ...

    def validate_syntax(self, code: str) -> tuple[bool, str]:
        """Return (True, '') if code is syntactically valid, (False, error_msg) otherwise.

        Used by MicroPrime to replace hardcoded ``ast.parse()`` validation
        gates with language-dispatched validation.
        """
        ...

    def generate_dependency_file(
        self,
        project_root: Path,
        service_name: str,
        module_path: str,
        dependencies: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Generate language-specific dependency manifest content.

        Args:
            project_root: Project root directory.
            service_name: Name of the service being generated.
            module_path: Module/package path (e.g. Go module path).
            dependencies: List of dependency strings.
            metadata: Optional service metadata (language version, etc.).

        Returns:
            File content string, or None if not applicable.
        """
        ...
