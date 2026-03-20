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
        # Per-file syntax check: gofmt -e parses Go source without needing
        # go.mod — works in multi-module repos where go.mod lives in a
        # subdirectory, not project_root.  go vet ./... requires go.mod at cwd.
        return ["gofmt", "-e", "{file}"]

    @property
    def lint_command(self) -> Optional[List[str]]:
        # go vet requires go.mod — skip lint at the per-file level.
        # Post-generation cleanup (goimports) handles import correctness.
        return None

    @property
    def test_command(self) -> Optional[List[str]]:
        # go test ./... requires go.mod at cwd — same issue as go vet ./...
        # In multi-service repos, cwd is project_root, not the service
        # subdirectory.  Disable until checkpoint supports per-service cwd.
        return None

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
        return True

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

    @property
    def stub_patterns(self) -> List[str]:
        return [
            r'panic\s*\(\s*"not implemented"',
            r'panic\s*\(\s*"TODO',
            r'panic\s*\(\s*"unimplemented',
            r'^\s*//\s*TODO\b',
            r'^\s*return\s+(nil,\s*)?fmt\.Errorf\s*\(\s*"not implemented',
        ]

    @property
    def function_start_pattern(self) -> Optional[str]:
        return r'^func\s+(?:\(.*?\)\s+)?(?P<name>[A-Za-z_]\w*)\s*\('

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

        # Resolve tool once — prefer goimports (fixes imports + formats),
        # fall back to gofmt (formats only).
        goimports_bin = shutil.which("goimports")
        gofmt_bin = shutil.which("gofmt")
        tool_bin = goimports_bin or gofmt_bin
        tool_name = "goimports" if goimports_bin else ("gofmt" if gofmt_bin else None)

        if tool_bin is None:
            warnings.append(
                "neither goimports nor gofmt found on PATH — "
                "install with: go install golang.org/x/tools/cmd/goimports@latest"
            )
            return warnings

        for go_file in go_files:
            cmd = [tool_bin, "-w", str(go_file)]
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
                logger.warning("%s failed for %s: %s", tool_name, go_file.name, exc, exc_info=True)

        if tool_name == "gofmt":
            warnings.append(
                "goimports not found — install with: go install golang.org/x/tools/cmd/goimports@latest"
            )

        return warnings

    def validate_syntax(self, code: str) -> tuple[bool, str]:
        """Validate Go syntax via gofmt -e on a temp file."""
        import tempfile
        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False)
            tmp.write(code)
            tmp.flush()
            tmp.close()
            result = subprocess.run(
                ["gofmt", "-e", tmp.name],
                capture_output=True, text=True, timeout=_GO_TOOL_TIMEOUT,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr.strip()
        except FileNotFoundError:
            # gofmt not installed — assume valid (best-effort)
            logger.warning("gofmt not found on PATH — skipping Go syntax validation")
            return True, ""
        except subprocess.TimeoutExpired:
            return False, "gofmt timed out"
        except OSError as exc:
            return False, str(exc)
        finally:
            if tmp is not None:
                import os
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

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


    def derive_service_metadata(
        self,
        features: Sequence[Any],
        *,
        onboarding: Optional[Dict[str, Any]] = None,
        api_signatures: Optional[List[str]] = None,
        runtime_dependencies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Derive Go-specific service metadata from plan features.

        Extracts module_path, service_name, and go_version.
        """
        metadata: Dict[str, Any] = {}
        api_sigs = api_signatures or []

        # module_path: prefer explicit feature attribute, else parse from api_signatures
        module_paths: List[str] = []
        service_names: List[str] = []
        for f in features:
            _mp = getattr(f, "module_path", "")
            if _mp:
                module_paths.append(_mp)
            _sn = getattr(f, "service_name", "")
            if _sn:
                service_names.append(_sn)

        if module_paths:
            metadata["module_path"] = module_paths[0]
        else:
            for sig in api_sigs:
                if sig.startswith("module "):
                    metadata["module_path"] = sig.split(None, 1)[1].strip()
                    break

        if service_names:
            metadata["service_name"] = service_names[0]
        else:
            go_dirs: set[str] = set()
            for feat in features:
                for tf in getattr(feat, "target_files", []):
                    if tf.endswith(".go"):
                        parts = tf.replace("\\", "/").rsplit("/", 1)
                        if len(parts) == 2:
                            go_dirs.add(parts[0].rsplit("/", 1)[-1])
            if len(go_dirs) == 1:
                metadata["service_name"] = go_dirs.pop()

        go_version = "1.23"
        if onboarding:
            go_version = str(onboarding.get("go_version", go_version))
        metadata["go_version"] = go_version

        return metadata

    def build_project_context_section(self, context: Dict[str, Any]) -> str:
        """Build Go module context section for correct package and import generation.

        Provides the LLM with the module path, package name, and Go-specific
        structural rules required for syntactically correct Go output.
        """
        # Derive package name from target file path
        target_files = context.get("target_files") or []
        package_name = "main"  # default for executable entry points
        service_name = context.get("service_name", "")
        module_path = context.get("module_path", "")

        # Also check service_metadata (populated at service level)
        svc_meta = context.get("service_metadata")
        if isinstance(svc_meta, dict):
            if not module_path:
                module_path = svc_meta.get("module_path", "")
            if not service_name:
                service_name = svc_meta.get("service_name", "")

        # Derive package from target file: main.go -> "main", server.go -> service dir name
        for tf in target_files:
            fname = tf.rsplit("/", 1)[-1] if "/" in tf else tf
            if fname == "main.go":
                package_name = "main"
                break
            elif fname.endswith("_test.go"):
                # Test files use same package as the code they test
                if service_name:
                    package_name = service_name.replace("-", "")
                break
            elif fname.endswith(".go"):
                # Non-main Go files use the service/directory name as package
                if service_name:
                    package_name = service_name.replace("-", "")
                break

        lines = [
            "## Go Module Context (CRITICAL — required for compilation)\n",
            f"- **Package declaration**: `package {package_name}` (MUST be the first line of the file)",
        ]
        if module_path:
            lines.append(f"- **Module path**: `{module_path}`")
            lines.append(f"  - Internal imports use: `\"{module_path}/...\"` paths")
        if service_name:
            lines.append(f"- **Service**: `{service_name}`")

        lines.extend([
            "",
            "**Go import rules:**",
            "- Every import must use the full quoted module path (e.g. `\"github.com/sirupsen/logrus\"`)",
            "- Group imports: stdlib first, then a blank line, then third-party",
            "- No unused imports (Go compiler error) — only import what you use",
            "- No unused variables (Go compiler error) — use `_` for intentionally unused values",
            "",
            "**Go structural rules:**",
            "- `context.Context` is always the first parameter in functions that accept it",
            "- Error is always the last return value: `func Foo() (ResultType, error)`",
            "- Exported names start with uppercase, unexported with lowercase",
            "- Use `if err != nil { return ..., err }` — do not use try/catch or panic for control flow",
        ])

        return "\n".join(lines)

    def strip_dependency_version(self, dep: str) -> str:
        """Strip version from Go dependency. 'mod v1.0' -> 'mod'."""
        return dep.split()[0].strip() if dep.strip() else dep

    def get_import_syntax_guidance(self) -> str:
        """Return Go import rules for LLM prompts."""
        return (
            "Use ONLY these modules plus Go stdlib. Every non-stdlib package you\n"
            "reference MUST have a corresponding import statement. Use full module\n"
            'paths in import statements (e.g. `import "github.com/sirupsen/logrus"`).\n'
            "Do NOT import modules not listed above.\n"
        )

    def extract_import_lines(self, source: str) -> list[str]:
        """Extract import statements from Go source (REQ-PE-400)."""
        import re
        imports: list[str] = []
        # Single imports: import "pkg"
        for m in re.finditer(r'^import\s+"([^"]+)"', source, re.MULTILINE):
            imports.append(f'import "{m.group(1)}"')
        # Block imports: import ( ... )
        for block in re.finditer(r'import\s*\((.*?)\)', source, re.DOTALL):
            for line in block.group(1).splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("//"):
                    imports.append(stripped)
        return imports

    @property
    def stub_marker_text(self) -> str:
        """Go stub marker for skeleton fill prompts."""
        return '`panic("not implemented")`'


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
