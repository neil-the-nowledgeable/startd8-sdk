"""NodeLanguageProfile — Node.js/JavaScript language support for Prime Contractor.

Handles both CommonJS (require) and ESM (import from) patterns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


class NodeLanguageProfile:
    """Language profile for Node.js code generation."""

    @property
    def language_id(self) -> str:
        return "nodejs"

    @property
    def display_name(self) -> str:
        return "Node.js"

    @property
    def source_extensions(self) -> List[str]:
        return [".js", ".mjs", ".cjs"]

    @property
    def build_file_patterns(self) -> List[str]:
        return ["package.json", "package-lock.json", "yarn.lock"]

    @property
    def syntax_check_command(self) -> Optional[List[str]]:
        return ["node", "--check", "{file}"]

    @property
    def lint_command(self) -> Optional[List[str]]:
        # ESLint if available; syntax check is the fallback
        return None

    @property
    def test_command(self) -> Optional[List[str]]:
        return ["npm", "test"]

    @property
    def framework_imports(self) -> Dict[str, dict]:
        return {
            "grpc": {
                "detect": ["grpc", "proto", "protobuf", "gRPC"],
                "dep_names": {"@grpc/grpc-js", "@grpc/proto-loader"},
                "imports": [
                    "const grpc = require('@grpc/grpc-js');",
                    "const protoLoader = require('@grpc/proto-loader');",
                ],
                "conditional": {},
            },
            "express": {
                "detect": ["express", "web server", "REST API"],
                "dep_names": {"express"},
                "imports": [
                    "const express = require('express');",
                ],
                "conditional": {},
            },
            "logging": {
                "detect": ["pino", "winston", "log"],
                "dep_names": {"pino"},
                "imports": [
                    "const pino = require('pino');",
                ],
                "conditional": {},
            },
        }

    @property
    def package_alias_map(self) -> Dict[str, str]:
        # Node packages generally match their import names
        return {}

    @property
    def cleanup_patterns(self) -> List[str]:
        return ["node_modules/", ".npm/"]

    @property
    def blast_radius_extensions(self) -> List[str]:
        return [".js", ".mjs", ".cjs"]

    @property
    def import_pattern_template(self) -> str:
        # Match both CommonJS and ESM
        return "require\\(['\"].*{module}|from ['\"].*{module}"

    @property
    def system_prompt_role(self) -> str:
        return "an expert Node.js engineer"

    @property
    def coding_standards(self) -> str:
        return (
            "Modern JavaScript: async/await, const by default, destructuring. "
            "No var. Use explicit error handling for async operations."
        )

    @property
    def merge_strategy_preference(self) -> str:
        return "simple"

    @property
    def repair_enabled(self) -> bool:
        # No static type checking — weaker validation than Go/Python
        return True

    @property
    def docker_base_image(self) -> str:
        return "node:20-alpine"

    @property
    def docker_runtime_image(self) -> str:
        return "node:20-alpine"

    def supports_extension(self, ext: str) -> bool:
        return ext.lower() in (".js", ".mjs", ".cjs")

    def get_import_patterns(self, module_stem: str) -> List[str]:
        return [
            f"require('{module_stem}",
            f'require("{module_stem}',
            f"from '{module_stem}",
            f'from "{module_stem}',
        ]

    @property
    def stub_patterns(self) -> List[str]:
        return [
            r'throw\s+new\s+Error\s*\(\s*["\']not implemented',
            r'throw\s+new\s+Error\s*\(\s*["\']TODO',
            r'^\s*//\s*TODO\b',
        ]

    @property
    def function_start_pattern(self) -> Optional[str]:
        return r'^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$]\w*)\s*\('

    def get_stdlib_prefixes(self) -> Sequence[str]:
        return _NODE_STDLIB_PREFIXES

    def post_generation_cleanup(self, files: List[Path], project_root: Path) -> List[str]:
        # Node.js has no authoritative import fixer like goimports.
        # prettier could format, but doesn't fix imports.
        return []

    def validate_syntax(self, code: str) -> tuple[bool, str]:
        """Validate Node.js syntax via node --check on a temp file."""
        import subprocess
        import tempfile
        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False)
            tmp.write(code)
            tmp.flush()
            tmp.close()
            result = subprocess.run(
                ["node", "--check", tmp.name],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr.strip()
        except FileNotFoundError:
            return True, ""  # node not installed — best-effort
        except subprocess.TimeoutExpired:
            return False, "node --check timed out"
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
        """Generate package.json content from service metadata."""
        import json

        pkg: Dict[str, Any] = {
            "name": service_name,
            "version": "1.0.0",
            "private": True,
        }

        if dependencies:
            deps: Dict[str, str] = {}
            for dep in dependencies:
                dep = dep.strip()
                if not dep:
                    continue
                # Handle name@version format.
                # Scoped packages start with @ (e.g. @grpc/grpc-js@^1.10.0)
                # so we count @ occurrences: scoped+versioned has 2+, plain has 1.
                at_count = dep.count("@")
                if at_count >= 2 or (at_count == 1 and not dep.startswith("@")):
                    parts = dep.rsplit("@", 1)
                    deps[parts[0]] = parts[1]
                elif " " in dep:
                    parts = dep.split(None, 1)
                    deps[parts[0]] = parts[1]
                else:
                    deps[dep] = "*"
            if deps:
                pkg["dependencies"] = deps

        return json.dumps(pkg, indent=2) + "\n"


_NODE_STDLIB_PREFIXES: tuple[str, ...] = (
    "assert", "async_hooks", "buffer", "child_process", "cluster",
    "console", "crypto", "dgram", "dns", "domain",
    "events", "fs", "http", "http2", "https",
    "inspector", "module", "net", "os", "path",
    "perf_hooks", "process", "querystring", "readline", "repl",
    "stream", "string_decoder", "timers", "tls", "trace_events",
    "tty", "url", "util", "v8", "vm",
    "wasi", "worker_threads", "zlib",
    # Node built-in prefix
    "node:",
)
