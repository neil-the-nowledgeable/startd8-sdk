"""
DomainPreflightWorkflow — Analyze artisan-context-seed.json tasks against
the real project environment and emit an enriched seed with per-task
domain classification, prompt constraints, environment checks, and
post-generation validator specs.

Pipeline:  load → scan → classify → check → enrich

Zero LLM calls — all analysis is deterministic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..base import WorkflowBase, ProgressCallback
from ..models import (
    AgentCount,
    StepResult,
    WorkflowInput,
    WorkflowMetadata,
    WorkflowMetrics,
    WorkflowResult,
)
from ...utils.file_operations import atomic_write_json

from .domain_preflight_models import (
    AvailableDeps,
    CheckStatus,
    DomainClassification,
    EnvironmentCheck,
    PreflightState,
    TaskDomain,
    TaskEnrichment,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stdlib fallback for Python < 3.10
# ---------------------------------------------------------------------------

_STDLIB_FALLBACK: Set[str] = {
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "audioop", "base64", "bdb", "binascii",
    "binhex", "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb",
    "chunk", "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
    "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
    "fnmatch", "fractions", "ftplib", "functools", "gc", "getopt",
    "getpass", "gettext", "glob", "graphlib", "grp", "gzip", "hashlib",
    "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
    "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "keyword", "lib2to3", "linecache", "locale", "logging",
    "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
    "mmap", "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev", "pathlib",
    "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
    "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
    "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc",
    "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
    "sqlite3", "sre_compile", "sre_constants", "sre_parse", "ssl",
    "stat", "statistics", "string", "stringprep", "struct", "subprocess",
    "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
    "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
    "threading", "time", "timeit", "tkinter", "token", "tokenize",
    "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
    "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib",
    "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
    "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
    "zipapp", "zipfile", "zipimport", "zlib", "zoneinfo",
}


# ---------------------------------------------------------------------------
# Dep name normalisation (PEP 503)
# ---------------------------------------------------------------------------

def _normalize_dep_name(name: str) -> str:
    """Normalize a dependency name: strip version specs, lowercase, replace - with _."""
    # Strip extras like [dev]
    name = re.split(r"\[", name, maxsplit=1)[0]
    # Strip version specs
    name = re.split(r"[><=!~;]", name, maxsplit=1)[0]
    return name.strip().lower().replace("-", "_")


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class DomainPreflightWorkflow(WorkflowBase):
    """
    Analyze artisan-context-seed.json tasks against the real project
    environment and emit an enriched seed with per-task domain
    classification, prompt constraints, environment checks, and
    post-generation validator specs.

    Zero LLM calls — all analysis is deterministic.
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="domain-preflight",
            name="Domain Preflight Workflow",
            description=(
                "Analyze artisan-context-seed tasks against the project "
                "environment and emit an enriched seed with domain "
                "classification, prompt constraints, and validator specs."
            ),
            version="1.0.0",
            capabilities=[
                "domain-classification",
                "environment-analysis",
                "prompt-constraint-generation",
            ],
            tags=["preflight", "artisan", "domain"],
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            max_agents=None,
            inputs=[
                WorkflowInput(
                    name="context_seed_path",
                    type="file",
                    required=True,
                    description="Path to artisan-context-seed.json",
                ),
                WorkflowInput(
                    name="project_root",
                    type="file",
                    required=False,
                    description="Project root directory (default: cwd)",
                ),
            ],
        )

    def _custom_validate(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        seed_path = config.get("context_seed_path")
        if seed_path:
            p = Path(str(seed_path)).expanduser()
            if not p.exists() or not p.is_file():
                errors.append(f"context_seed_path does not exist or is not a file: {p}")
        return errors

    # ------------------------------------------------------------------
    # Phase: LOAD
    # ------------------------------------------------------------------

    @staticmethod
    def _phase_load(seed_path: Path) -> Dict[str, Any]:
        """Read and validate the context seed JSON."""
        text = seed_path.read_text(encoding="utf-8")
        data = json.loads(text)

        version = data.get("version", "")
        if version != "1.0.0":
            raise ValueError(
                f"Unsupported context seed version: {version!r} (expected '1.0.0')"
            )

        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("Context seed missing 'tasks' list")

        return data

    # ------------------------------------------------------------------
    # Phase: SCAN
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_available_deps(project_root: Path) -> AvailableDeps:
        """Scan pyproject.toml + stdlib + project packages."""
        deps = AvailableDeps()

        # Stdlib
        if hasattr(sys, "stdlib_module_names"):
            deps.stdlib = set(sys.stdlib_module_names)
        else:
            deps.stdlib = set(_STDLIB_FALLBACK)

        # pyproject.toml
        pyproject_path = project_root / "pyproject.toml"
        if pyproject_path.exists():
            try:
                # Python 3.11+
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore[no-redef]
                except ImportError:
                    tomllib = None  # type: ignore[assignment]

            if tomllib is not None:
                try:
                    with open(pyproject_path, "rb") as f:
                        pyproject = tomllib.load(f)

                    # [project.dependencies]
                    for dep in pyproject.get("project", {}).get("dependencies", []):
                        deps.runtime.add(_normalize_dep_name(dep))

                    # [project.optional-dependencies]
                    for group, group_deps in (
                        pyproject.get("project", {})
                        .get("optional-dependencies", {})
                        .items()
                    ):
                        normalized = set()
                        for dep in group_deps:
                            normalized.add(_normalize_dep_name(dep))
                        deps.optional[group] = normalized

                except Exception as exc:
                    logger.warning("Failed to parse pyproject.toml: %s", exc)

        # Project packages: walk src/ for top-level __init__.py dirs
        src_dir = project_root / "src"
        if src_dir.is_dir():
            for child in src_dir.iterdir():
                if child.is_dir() and (child / "__init__.py").exists():
                    deps.project.add(child.name)

        return deps

    # ------------------------------------------------------------------
    # Phase: CLASSIFY
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_domain(
        target_file: str, project_root: Path
    ) -> DomainClassification:
        """Classify the domain for a target file path."""
        p = Path(target_file)
        ext = p.suffix.lower()
        name = p.name.lower()
        parts = p.parts

        # Non-Python files
        if ext != ".py":
            if ext == ".toml":
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.CONFIG_TOML,
                    reasoning=f"File extension is {ext}",
                )
            if ext in (".yaml", ".yml"):
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.CONFIG_YAML,
                    reasoning=f"File extension is {ext}",
                )
            if ext == ".json":
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.CONFIG_JSON,
                    reasoning=f"File extension is {ext}",
                )
            if ext:
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.NON_PYTHON,
                    reasoning=f"Non-Python extension: {ext}",
                )
            return DomainClassification(
                task_id="", target_file=target_file,
                domain=TaskDomain.UNKNOWN,
                reasoning="No file extension",
            )

        # Python test files
        if name.startswith("test_") or "test" in parts or "tests" in parts:
            return DomainClassification(
                task_id="", target_file=target_file,
                domain=TaskDomain.PYTHON_TEST,
                reasoning="Test file (name starts with test_ or path contains test/tests)",
            )

        # Python package module vs single module
        target_dir = (project_root / p).parent
        if target_dir.is_dir():
            has_init = (target_dir / "__init__.py").exists()
            py_siblings = [
                f.name for f in target_dir.iterdir()
                if f.suffix == ".py" and f.name != p.name and f.name != "__init__.py"
            ]
            if has_init or len(py_siblings) >= 2:
                return DomainClassification(
                    task_id="", target_file=target_file,
                    domain=TaskDomain.PYTHON_PACKAGE_MODULE,
                    reasoning=(
                        f"Package module: dir has __init__.py={has_init}, "
                        f"{len(py_siblings)} .py siblings"
                    ),
                )

        return DomainClassification(
            task_id="", target_file=target_file,
            domain=TaskDomain.PYTHON_SINGLE_MODULE,
            reasoning="Single Python module (no __init__.py, fewer than 2 siblings)",
        )

    # ------------------------------------------------------------------
    # Phase: CHECK
    # ------------------------------------------------------------------

    @staticmethod
    def _run_environment_checks(
        domain: TaskDomain,
        target_file: str,
        project_root: Path,
        available_deps: AvailableDeps,
    ) -> List[EnvironmentCheck]:
        """Run per-domain environment readiness checks."""
        checks: List[EnvironmentCheck] = []
        target_path = project_root / target_file
        target_dir = target_path.parent

        # All domains: parent directory exists
        if target_dir.exists():
            checks.append(EnvironmentCheck(
                check_name="parent_dir_exists",
                status=CheckStatus.PASS,
                message=f"Parent directory exists: {target_dir}",
            ))
        else:
            checks.append(EnvironmentCheck(
                check_name="parent_dir_exists",
                status=CheckStatus.WARN,
                message=f"Parent directory does not exist: {target_dir}",
                detail="Directory will need to be created before code generation",
            ))

        if domain == TaskDomain.PYTHON_SINGLE_MODULE:
            # Verify target is NOT inside a package
            init_path = target_dir / "__init__.py"
            if init_path.exists():
                checks.append(EnvironmentCheck(
                    check_name="not_in_package",
                    status=CheckStatus.WARN,
                    message="Target dir has __init__.py — may need package-module treatment",
                    detail=str(init_path),
                ))
            else:
                checks.append(EnvironmentCheck(
                    check_name="not_in_package",
                    status=CheckStatus.PASS,
                    message="Target is not inside a Python package (no __init__.py)",
                ))

        elif domain == TaskDomain.PYTHON_PACKAGE_MODULE:
            # __init__.py exists in target dir
            init_path = target_dir / "__init__.py"
            if init_path.exists():
                checks.append(EnvironmentCheck(
                    check_name="init_py_exists",
                    status=CheckStatus.PASS,
                    message="__init__.py exists in target directory",
                ))
            else:
                checks.append(EnvironmentCheck(
                    check_name="init_py_exists",
                    status=CheckStatus.FAIL,
                    message="Missing __init__.py in target directory",
                    detail=f"Expected at: {init_path}",
                ))

            # Parent package importable
            parent_init = target_dir.parent / "__init__.py"
            if target_dir.parent == project_root or parent_init.exists():
                checks.append(EnvironmentCheck(
                    check_name="parent_package_importable",
                    status=CheckStatus.PASS,
                    message="Parent package is importable",
                ))
            else:
                checks.append(EnvironmentCheck(
                    check_name="parent_package_importable",
                    status=CheckStatus.WARN,
                    message="Parent package may not be importable (no __init__.py)",
                    detail=str(target_dir.parent),
                ))

        elif domain == TaskDomain.PYTHON_TEST:
            # Source module under test exists
            # Heuristic: test_foo.py → foo.py in src/
            test_name = Path(target_file).stem
            if test_name.startswith("test_"):
                source_name = test_name[5:]  # strip test_ prefix
                # Search for source module
                src_dir = project_root / "src"
                found = False
                if src_dir.is_dir():
                    for match in src_dir.rglob(f"{source_name}.py"):
                        found = True
                        checks.append(EnvironmentCheck(
                            check_name="source_module_exists",
                            status=CheckStatus.PASS,
                            message=f"Source module found: {match.relative_to(project_root)}",
                        ))
                        break
                if not found:
                    checks.append(EnvironmentCheck(
                        check_name="source_module_exists",
                        status=CheckStatus.WARN,
                        message=f"Source module '{source_name}.py' not found in src/",
                        detail="May be a new module being created in this batch",
                    ))

            # Test directory exists
            if target_dir.exists():
                checks.append(EnvironmentCheck(
                    check_name="test_dir_exists",
                    status=CheckStatus.PASS,
                    message=f"Test directory exists: {target_dir}",
                ))
            else:
                checks.append(EnvironmentCheck(
                    check_name="test_dir_exists",
                    status=CheckStatus.WARN,
                    message=f"Test directory does not exist: {target_dir}",
                ))

            # conftest.py scannable
            conftest = target_dir / "conftest.py"
            if conftest.exists():
                checks.append(EnvironmentCheck(
                    check_name="conftest_scannable",
                    status=CheckStatus.PASS,
                    message="conftest.py found in test directory",
                ))
            else:
                checks.append(EnvironmentCheck(
                    check_name="conftest_scannable",
                    status=CheckStatus.SKIP,
                    message="No conftest.py in test directory",
                ))

        elif domain in (
            TaskDomain.CONFIG_TOML,
            TaskDomain.CONFIG_YAML,
            TaskDomain.CONFIG_JSON,
        ):
            # Current file exists and is valid format
            if target_path.exists():
                checks.append(EnvironmentCheck(
                    check_name="config_file_exists",
                    status=CheckStatus.PASS,
                    message=f"Config file exists: {target_file}",
                ))
                # Validate format
                try:
                    content = target_path.read_text(encoding="utf-8")
                    if domain == TaskDomain.CONFIG_JSON:
                        json.loads(content)
                    elif domain == TaskDomain.CONFIG_TOML:
                        try:
                            import tomllib
                        except ImportError:
                            try:
                                import tomli as tomllib  # type: ignore[no-redef]
                            except ImportError:
                                tomllib = None  # type: ignore[assignment]
                        if tomllib is not None:
                            with open(target_path, "rb") as f:
                                tomllib.load(f)
                    elif domain == TaskDomain.CONFIG_YAML:
                        import yaml
                        yaml.safe_load(content)
                    checks.append(EnvironmentCheck(
                        check_name="config_format_valid",
                        status=CheckStatus.PASS,
                        message="Existing config file is valid",
                    ))
                except Exception as exc:
                    checks.append(EnvironmentCheck(
                        check_name="config_format_valid",
                        status=CheckStatus.WARN,
                        message=f"Existing config file has format issues: {exc}",
                    ))
            else:
                checks.append(EnvironmentCheck(
                    check_name="config_file_exists",
                    status=CheckStatus.SKIP,
                    message="Config file does not exist yet (will be created)",
                ))

        return checks

    # ------------------------------------------------------------------
    # Phase: ENRICH
    # ------------------------------------------------------------------

    @staticmethod
    def _build_enrichment(
        task_id: str,
        domain: TaskDomain,
        domain_reasoning: str,
        target_file: str,
        project_root: Path,
        available_deps: AvailableDeps,
        checks: List[EnvironmentCheck],
    ) -> TaskEnrichment:
        """Build prompt constraints and validator specs for a task."""
        enrichment = TaskEnrichment(
            task_id=task_id,
            domain=domain,
            domain_reasoning=domain_reasoning,
            environment_checks=checks,
        )

        target_path = project_root / target_file
        target_dir = target_path.parent

        # Domain-specific prompt constraints
        if domain == TaskDomain.PYTHON_SINGLE_MODULE:
            enrichment.prompt_constraints = [
                "Output a single Python module -- not a package",
                "Do not use relative imports (from .module import ...)",
                f"Only import from: {', '.join(sorted(available_deps.all_importable)[:50])}",
                "Define utility functions before classes that reference them",
            ]
            enrichment.post_generation_validators = [
                "no_relative_imports",
                "deps_available",
                "definition_ordering",
            ]

        elif domain == TaskDomain.PYTHON_PACKAGE_MODULE:
            # Determine package name from path
            parts = Path(target_file).parts
            package_name = parts[-2] if len(parts) >= 2 else "unknown"

            # Collect siblings
            siblings: List[str] = []
            if target_dir.is_dir():
                siblings = [
                    f.stem for f in target_dir.iterdir()
                    if f.suffix == ".py"
                    and f.name != Path(target_file).name
                    and f.name != "__init__.py"
                ]
            enrichment.available_siblings = sorted(siblings)

            sibling_list = ", ".join(enrichment.available_siblings[:20]) or "(none)"
            enrichment.prompt_constraints = [
                f"This file is part of the {package_name} package",
                f"Use relative imports for siblings: {sibling_list}",
                "Use absolute imports for SDK modules",
            ]
            enrichment.post_generation_validators = [
                "relative_imports_valid",
                "deps_available",
                "no_circular_imports",
            ]

        elif domain == TaskDomain.PYTHON_TEST:
            # Scan conftest for fixtures
            fixtures: List[str] = []
            conftest = target_dir / "conftest.py"
            if conftest.exists():
                try:
                    content = conftest.read_text(encoding="utf-8")
                    # Simple regex to find fixture names
                    fixtures = re.findall(
                        r"@pytest\.fixture[^)]*\)\s*\ndef\s+(\w+)",
                        content,
                    )
                except Exception:
                    pass

            fixture_list = ", ".join(fixtures[:20]) or "(none found)"
            enrichment.prompt_constraints = [
                "Use pytest conventions (functions starting with test_, classes with Test)",
                f"Available fixtures: {fixture_list}",
                "Mock external dependencies -- do not make real API calls",
            ]
            enrichment.post_generation_validators = [
                "imports_resolve",
                "test_naming",
                "no_hardcoded_secrets",
            ]

        elif domain in (
            TaskDomain.CONFIG_TOML,
            TaskDomain.CONFIG_YAML,
            TaskDomain.CONFIG_JSON,
        ):
            constraints = ["Preserve existing sections"]
            if target_path.exists():
                constraints.append("Current content provided as context")
            enrichment.prompt_constraints = constraints
            enrichment.post_generation_validators = [
                "valid_format",
                "existing_keys_preserved",
            ]

        # Hash existing content if target file exists
        if target_path.exists() and target_path.is_file():
            try:
                content = target_path.read_bytes()
                enrichment.existing_content_hash = hashlib.sha256(content).hexdigest()[:16]
            except Exception:
                pass

        return enrichment

    # ------------------------------------------------------------------
    # Main execution
    # ------------------------------------------------------------------

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[Any]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        started_at = datetime.now(timezone.utc)
        steps: List[StepResult] = []
        state = PreflightState()

        seed_path = Path(str(config["context_seed_path"])).expanduser().resolve()
        project_root = Path(
            str(config.get("project_root", "."))
        ).expanduser().resolve()

        state.seed_path = str(seed_path)
        state.project_root = str(project_root)

        total_steps = 5
        current_step = 0

        def progress(msg: str):
            nonlocal current_step
            current_step += 1
            self._emit_progress(on_progress, current_step, total_steps, msg)

        def _fail(error_msg: str) -> WorkflowResult:
            state.current_phase = "failed"
            state.error = error_msg
            return WorkflowResult.from_error(
                self.metadata.workflow_id, error_msg, steps=steps,
            )

        try:
            # --- LOAD ---
            progress("Loading context seed")
            state.current_phase = "load"
            t0 = time.time()

            seed_data = self._phase_load(seed_path)
            tasks = seed_data.get("tasks", [])
            state.task_count = len(tasks)

            load_step = StepResult(
                step_name="load",
                output=f"Loaded {len(tasks)} tasks from {seed_path.name}",
                time_ms=int((time.time() - t0) * 1000),
            )
            steps.append(load_step)

            # --- SCAN ---
            progress("Scanning available dependencies")
            state.current_phase = "scan"
            t0 = time.time()

            available_deps = self._scan_available_deps(project_root)

            scan_step = StepResult(
                step_name="scan",
                output=(
                    f"Found {len(available_deps.runtime)} runtime deps, "
                    f"{len(available_deps.stdlib)} stdlib modules, "
                    f"{len(available_deps.project)} project packages"
                ),
                time_ms=int((time.time() - t0) * 1000),
            )
            steps.append(scan_step)

            # --- CLASSIFY + CHECK + ENRICH (per task) ---
            progress("Classifying task domains")
            state.current_phase = "classify"
            t0_classify = time.time()

            domain_summary: Dict[str, int] = {}
            check_summary: Dict[str, int] = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
            enrichments: List[TaskEnrichment] = []

            for task in tasks:
                task_id = task.get("task_id", "unknown")
                task_config = task.get("config", {})
                context = task_config.get("context", {})
                target_files = context.get("target_files", [])

                # Use first target file for classification
                target_file = target_files[0] if target_files else ""
                if not target_file:
                    enrichments.append(TaskEnrichment(
                        task_id=task_id,
                        domain=TaskDomain.UNKNOWN,
                        domain_reasoning="No target files specified",
                    ))
                    domain_summary["unknown"] = domain_summary.get("unknown", 0) + 1
                    continue

                # Classify
                classification = self._classify_domain(target_file, project_root)
                classification.task_id = task_id
                domain = classification.domain
                domain_summary[domain.value] = domain_summary.get(domain.value, 0) + 1

                # Check
                checks = self._run_environment_checks(
                    domain, target_file, project_root, available_deps,
                )
                for check in checks:
                    check_summary[check.status.value] = (
                        check_summary.get(check.status.value, 0) + 1
                    )

                # Enrich
                enrichment = self._build_enrichment(
                    task_id, domain, classification.reasoning,
                    target_file, project_root, available_deps, checks,
                )
                enrichments.append(enrichment)
                state.enriched_count += 1

            state.check_summary = check_summary

            classify_step = StepResult(
                step_name="classify_check_enrich",
                output=(
                    f"Classified {len(tasks)} tasks: "
                    f"{json.dumps(domain_summary)}"
                ),
                time_ms=int((time.time() - t0_classify) * 1000),
            )
            steps.append(classify_step)

            # Emit progress for check phase
            progress("Running environment checks")
            state.current_phase = "check"
            # Checks already done above in the loop

            # --- ENRICH (write output) ---
            progress("Writing enriched seed")
            state.current_phase = "enrich"
            t0 = time.time()

            # Build enriched seed: copy original with _enrichment per task
            enriched_seed = dict(seed_data)
            enrichment_by_id = {e.task_id: e for e in enrichments}

            enriched_tasks = []
            for task in enriched_seed.get("tasks", []):
                enriched_task = dict(task)
                task_id = task.get("task_id", "unknown")
                enrich = enrichment_by_id.get(task_id)
                if enrich:
                    enriched_task["_enrichment"] = enrich.to_dict()
                enriched_tasks.append(enriched_task)
            enriched_seed["tasks"] = enriched_tasks

            # Top-level _preflight summary
            enriched_seed["_preflight"] = {
                "workflow_version": self.metadata.version,
                "available_deps_count": len(available_deps.all_importable),
                "check_summary": check_summary,
                "domain_summary": domain_summary,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

            # Write enriched seed alongside original
            enriched_path = seed_path.parent / "artisan-context-seed-enriched.json"
            atomic_write_json(enriched_path, enriched_seed, indent=2)

            enrich_step = StepResult(
                step_name="enrich",
                output=f"Wrote {enriched_path}",
                time_ms=int((time.time() - t0) * 1000),
            )
            steps.append(enrich_step)

            # --- DONE ---
            state.current_phase = "completed"
            completed_at = datetime.now(timezone.utc)
            total_ms = int((completed_at - started_at).total_seconds() * 1000)

            output: Dict[str, Any] = {
                "enriched_seed_path": str(enriched_path),
                "original_seed_path": str(seed_path),
                "project_root": str(project_root),
                "task_count": len(tasks),
                "domain_summary": domain_summary,
                "check_summary": check_summary,
                "available_deps_count": len(available_deps.all_importable),
            }

            return WorkflowResult(
                workflow_id=self.metadata.workflow_id,
                success=True,
                output=output,
                metrics=WorkflowMetrics(
                    total_time_ms=total_ms,
                    step_count=len(steps),
                ),
                steps=steps,
                started_at=started_at,
                completed_at=completed_at,
            )

        except Exception as exc:
            logger.error("Domain preflight failed: %s", exc, exc_info=True)
            return _fail(str(exc))
