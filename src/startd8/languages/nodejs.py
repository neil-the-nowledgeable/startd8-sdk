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
        return [".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"]

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
            "otel": {
                "detect": ["opentelemetry", "OTel", "tracing", "instrumentation"],
                "dep_names": {
                    "@opentelemetry/sdk-node",
                    "@opentelemetry/api",
                    "@opentelemetry/instrumentation-grpc",
                    "@opentelemetry/exporter-trace-otlp-grpc",
                },
                "imports": [
                    "const opentelemetry = require('@opentelemetry/sdk-node');",
                    "const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-grpc');",
                    "const { GrpcInstrumentation } = require('@opentelemetry/instrumentation-grpc');",
                    "const { registerInstrumentations } = require('@opentelemetry/instrumentation');",
                ],
                "conditional": {},
            },
            "profiler": {
                "detect": ["profiler", "cloud profiler"],
                "dep_names": {"@google-cloud/profiler"},
                "imports": [
                    "require('@google-cloud/profiler').start({serviceContext: {service: '<SERVICE_NAME>', version: '1.0.0'}});",
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
            "uuid": {
                "detect": ["uuid", "transaction id"],
                "dep_names": {"uuid"},
                "imports": [
                    "const { v4: uuidv4 } = require('uuid');",
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
        return ext.lower() in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx")

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
        """Run prettier on generated JS files if available (REQ-NODE-300).

        Best-effort cosmetic formatting only — does not fix imports.
        Returns list of formatted file paths.
        """
        import shutil
        import subprocess

        prettier = shutil.which("prettier")
        if not prettier:
            return []

        formatted: List[str] = []
        js_exts = (".js", ".mjs", ".cjs")
        js_files = [f for f in files if f.suffix.lower() in js_exts]
        for f in js_files:
            try:
                subprocess.run(
                    [prettier, "--write", str(f)],
                    capture_output=True, timeout=30,
                )
                formatted.append(str(f))
            except (subprocess.TimeoutExpired, OSError):
                pass  # best-effort — skip on failure
        return formatted

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


    def derive_service_metadata(
        self,
        features: Sequence[Any],
        *,
        onboarding: Optional[Dict[str, Any]] = None,
        api_signatures: Optional[List[str]] = None,
        runtime_dependencies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Derive Node.js-specific service metadata from plan features.

        Extracts module_system and node_version.
        """
        metadata: Dict[str, Any] = {}

        # module_system: prefer explicit, else infer from file extensions
        module_systems: list[str] = []
        for f in features:
            ms = getattr(f, "module_system", "")
            if ms:
                module_systems.append(ms)
        if module_systems:
            metadata["module_system"] = module_systems[0]
        else:
            all_files = [tf for f in features for tf in getattr(f, "target_files", [])]
            has_mjs = any(tf.endswith(".mjs") for tf in all_files)
            has_cjs = any(tf.endswith(".cjs") for tf in all_files)
            if has_mjs and not has_cjs:
                metadata["module_system"] = "esm"
            elif has_cjs and not has_mjs:
                metadata["module_system"] = "commonjs"
            else:
                metadata["module_system"] = "esm"  # default

        # node_version
        node_version = "20"
        for f in features:
            nv = getattr(f, "node_version", "")
            if nv:
                node_version = nv
                break
        if onboarding:
            node_version = str(onboarding.get("node_version", node_version))
        metadata["node_version"] = node_version

        return metadata

    def build_project_context_section(self, context: Dict[str, Any]) -> str:
        """Build Node.js module context section for correct import/export generation."""
        module_system = context.get("module_system", "")
        node_version = context.get("node_version", "20")

        # Check service_metadata
        svc_meta = context.get("service_metadata")
        if isinstance(svc_meta, dict):
            if not module_system:
                module_system = svc_meta.get("module_system", "")
            if not node_version or node_version == "20":
                node_version = svc_meta.get("node_version", node_version)
        if not module_system:
            module_system = "commonjs"  # Node.js default when package.json has no "type" field

        is_esm = module_system == "esm"

        lines = [
            "## Node.js Module Context (CRITICAL — required for correct imports)\n",
            f"- **Module system**: {'ES Modules (ESM)' if is_esm else 'CommonJS (CJS)'}",
            f"- **Node.js version**: {node_version}",
        ]

        if is_esm:
            lines.extend([
                "",
                "**ESM import/export rules:**",
                "- Use `import X from 'pkg'` for default imports",
                "- Use `import { X, Y } from 'pkg'` for named imports",
                "- Use `export default` or `export { X, Y }` for exports",
                "- Use `import { readFile } from 'node:fs/promises'` for Node builtins (node: prefix)",
                "- File extensions required in relative imports: `import X from './util.js'`",
                "- No `require()` or `module.exports` — ESM only",
                "- Top-level `await` is supported",
            ])
        else:
            lines.extend([
                "",
                "**CommonJS import/export rules:**",
                "- Use `const X = require('pkg')` for imports",
                "- Use `const { X, Y } = require('pkg')` for destructured imports",
                "- Use `module.exports = X` or `exports.X = ...` for exports",
                "- Use `const fs = require('fs')` for Node builtins (no node: prefix needed)",
                "- No `import`/`export` statements — CommonJS only",
            ])

        lines.extend([
            "",
            "**Node.js structural rules:**",
            "- camelCase for variables and functions, PascalCase for classes",
            "- Use `async`/`await` for asynchronous code (not callbacks)",
            "- Handle errors with try/catch or `.catch()` — never swallow rejections",
            "- Use `const` by default, `let` only when reassignment is needed, never `var`",
        ])

        # REQ-NODE-601: Dockerfile context for Node.js services
        target_files = context.get("target_files") or []
        has_dockerfile = any(
            Path(f).name.lower().startswith("dockerfile")
            for f in target_files
        )
        if has_dockerfile:
            entry_point = "index.js"
            if isinstance(svc_meta, dict):
                entry_point = svc_meta.get("entry_point", entry_point)
            lines.extend([
                "",
                "**Dockerfile patterns for Node.js:**",
                "- Multi-stage build: `node:20-alpine` builder → `alpine` runtime with `apk add nodejs`",
                "- Builder stage: `COPY package*.json ./` then `RUN npm install --only=production`",
                "- Runtime stage: `COPY --from=builder /usr/src/app/node_modules ./node_modules`",
                f"- Entry point: `ENTRYPOINT [ \"node\", \"{entry_point}\" ]`",
                "- No HEALTHCHECK instruction — use gRPC health protocol instead",
            ])

        return "\n".join(lines)

    def strip_dependency_version(self, dep: str) -> str:
        """Strip version from Node.js dependency. '@scope/pkg@1.0' -> '@scope/pkg'."""
        if dep.startswith("@"):
            rest = dep[1:]
            at_idx = rest.find("@")
            return ("@" + rest[:at_idx]) if at_idx > 0 else dep.strip()
        return dep.split("@")[0].strip()

    def get_import_syntax_guidance(self) -> str:
        """Return Node.js import rules for LLM prompts."""
        return (
            "Use ONLY these packages plus Node.js builtins (fs, path, http, etc.).\n"
            "Every package you reference MUST be listed above or be a Node builtin.\n"
            "Do NOT import packages not listed above.\n"
        )


def detect_module_system(project_root: Path) -> str:
    """Detect CommonJS vs ESM from package.json ``type`` field (REQ-NODE-104).

    Returns ``"commonjs"`` or ``"esm"``. Defaults to ``"commonjs"``
    (Node.js default when ``package.json`` has no ``type`` field).
    """
    import json

    pkg_path = project_root / "package.json"
    if not pkg_path.is_file():
        return "commonjs"
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        return "esm" if data.get("type") == "module" else "commonjs"
    except (json.JSONDecodeError, OSError):
        return "commonjs"


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
