"""NodeLanguageProfile — Node.js/JavaScript language support for Prime Contractor.

Handles both CommonJS (require) and ESM (import from) patterns.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence


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

    def get_stdlib_prefixes(self) -> Sequence[str]:
        return _NODE_STDLIB_PREFIXES


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
