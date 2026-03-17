"""GoLanguageProfile — Go language support for Prime Contractor.

Go profile values derived from the online-boutique-demo Go services.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence


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
