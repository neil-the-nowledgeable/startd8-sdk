"""GoLanguageProfile — Go language support for Prime Contractor.

Go profile values derived from the online-boutique-demo Go services.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Timeout for goimports/gofmt subprocess calls (seconds)
_GO_TOOL_TIMEOUT = 30


class GoLanguageProfile:
    """Language profile for Go code generation."""

    @property
    def language_id(self) -> str:
        return "go"

    @property
    def display_name(self) -> str:
        return "Go"

    @property
    def source_extensions(self) -> List[str]:
        return [".go"]

    @property
    def build_file_patterns(self) -> List[str]:
        return ["go.mod", "go.sum"]

    @property
    def syntax_check_command(self) -> Optional[List[str]]:
        return ["go", "vet", "./..."]

    @property
    def lint_command(self) -> Optional[List[str]]:
        # go vet covers most correctness issues; golangci-lint is optional
        return ["go", "vet", "./..."]

    @property
    def test_command(self) -> Optional[List[str]]:
        return ["go", "test", "./..."]

    @property
    def framework_imports(self) -> Dict[str, dict]:
        return {
            "grpc": {
                "detect": ["grpc", "proto", "protobuf", "gRPC"],
                "dep_names": {"google.golang.org/grpc"},
                "imports": [
                    '"google.golang.org/grpc"',
                ],
                "conditional": {},
            },
            "http": {
                "detect": ["gorilla", "mux", "HTTP", "REST"],
                "dep_names": {"github.com/gorilla/mux"},
                "imports": [
                    '"github.com/gorilla/mux"',
                    '"net/http"',
                ],
                "conditional": {},
            },
            "logging": {
                "detect": ["logrus", "log", "logging"],
                "dep_names": {"github.com/sirupsen/logrus"},
                "imports": [
                    'log "github.com/sirupsen/logrus"',
                ],
                "conditional": {},
            },
        }

    @property
    def package_alias_map(self) -> Dict[str, str]:
        # Go uses module paths, not PyPI-style aliases
        return {}

    @property
    def cleanup_patterns(self) -> List[str]:
        return ["vendor/"]

    @property
    def blast_radius_extensions(self) -> List[str]:
        return [".go"]

    @property
    def import_pattern_template(self) -> str:
        return 'import.*"{module}"'

    @property
    def system_prompt_role(self) -> str:
        return "an expert Go engineer"

    @property
    def coding_standards(self) -> str:
        return (
            "Idiomatic Go: exported names capitalized, explicit `if err != nil` "
            "error handling, composition over inheritance, no unused imports or "
            "variables (compiler-enforced). Use standard library where possible."
        )

    @property
    def merge_strategy_preference(self) -> str:
        return "simple"

    @property
    def repair_enabled(self) -> bool:
        # Go has compile-time checks — repair pipeline is less useful
        return False

    @property
    def docker_base_image(self) -> str:
        return "golang:1.23-alpine"

    @property
    def docker_runtime_image(self) -> str:
        return "gcr.io/distroless/static"

    def supports_extension(self, ext: str) -> bool:
        return ext.lower() == ".go"

    def get_import_patterns(self, module_stem: str) -> List[str]:
        return [
            f'"{module_stem}"',
            f'/{module_stem}"',
        ]

    def get_stdlib_prefixes(self) -> Sequence[str]:
        return _GO_STDLIB_PREFIXES

    def post_generation_cleanup(self, files: List[Path], project_root: Path) -> List[str]:
        """Run goimports and gofmt on generated Go files.

        goimports is authoritative for Go — it:
        - Adds missing imports (resolves the entire import audit problem)
        - Removes unused imports (Go compiler requires this)
        - Formats the import block (groups stdlib vs third-party)

        Falls back to gofmt if goimports is not installed.
        """
        warnings: List[str] = []
        go_files = [f for f in files if f.suffix == ".go" and f.exists()]
        if not go_files:
            return warnings

        # Prefer goimports (fixes imports + formats), fall back to gofmt (formats only)
        goimports_bin = shutil.which("goimports")
        gofmt_bin = shutil.which("gofmt")

        for go_file in go_files:
            tool_name = None
            cmd: List[str] = []

            if goimports_bin:
                tool_name = "goimports"
                cmd = [goimports_bin, "-w", str(go_file)]
            elif gofmt_bin:
                tool_name = "gofmt"
                cmd = [gofmt_bin, "-w", str(go_file)]
            else:
                warnings.append(
                    f"{go_file.name}: neither goimports nor gofmt found on PATH"
                )
                continue

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=project_root,
                    timeout=_GO_TOOL_TIMEOUT,
                )
                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    warnings.append(f"{go_file.name}: {tool_name} failed: {stderr}")
                    logger.warning(
                        "%s failed for %s: %s", tool_name, go_file.name, stderr,
                    )
                else:
                    logger.debug(
                        "%s succeeded for %s", tool_name, go_file.name,
                    )
            except subprocess.TimeoutExpired:
                warnings.append(
                    f"{go_file.name}: {tool_name} timed out after {_GO_TOOL_TIMEOUT}s"
                )
            except OSError as exc:
                warnings.append(f"{go_file.name}: {tool_name} failed: {exc}")

        if not goimports_bin and gofmt_bin:
            warnings.append(
                "goimports not found — install with: go install golang.org/x/tools/cmd/goimports@latest"
            )

        return warnings

    def generate_dependency_file(
        self,
        project_root: Path,
        service_name: str,
        module_path: str,
        dependencies: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Generate go.mod content from service metadata.

        Args:
            project_root: Project root directory.
            service_name: Service name (used as fallback module path).
            module_path: Go module path (e.g. 'github.com/user/repo/src/frontend').
            dependencies: List of Go module dependency strings.
                Format: 'module@version' or 'module version' or just 'module'.
            metadata: Optional dict with 'go_version' key (default '1.23').

        Returns:
            go.mod file content string.
        """
        go_version = "1.23"
        if metadata:
            go_version = str(metadata.get("go_version", go_version))

        if not module_path:
            module_path = service_name

        lines: List[str] = [
            f"module {module_path}",
            "",
            f"go {go_version}",
        ]

        # Parse dependencies into require block
        require_entries: List[str] = []
        for dep in dependencies:
            dep = dep.strip()
            if not dep:
                continue
            # Handle 'module@version' format
            if "@" in dep:
                parts = dep.split("@", 1)
                require_entries.append(f"\t{parts[0]} {parts[1]}")
            # Handle 'module version' format
            elif " " in dep:
                parts = dep.split(None, 1)
                require_entries.append(f"\t{parts[0]} {parts[1]}")
            else:
                # Module without version — use latest placeholder
                require_entries.append(f"\t{dep} v0.0.0")

        if require_entries:
            lines.append("")
            lines.append("require (")
            lines.extend(require_entries)
            lines.append(")")

        lines.append("")  # trailing newline
        return "\n".join(lines)


_GO_STDLIB_PREFIXES: tuple[str, ...] = (
    "bufio", "bytes", "compress", "container", "context",
    "crypto", "database", "debug", "embed", "encoding",
    "errors", "expvar", "flag", "fmt", "go",
    "hash", "html", "image", "index", "io",
    "log", "maps", "math", "mime", "net",
    "os", "path", "plugin", "reflect", "regexp",
    "runtime", "slices", "sort", "strconv", "strings",
    "sync", "syscall", "testing", "text", "time",
    "unicode", "unsafe",
)
