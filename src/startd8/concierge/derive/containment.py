"""FR-DC-14 — import containment for derive-contract.

Runtime introspection (FR-DC-10) executes the target package's top-level module code and its
transitive deps' import code. `derive-contract` is a *general* Concierge action that may be
pointed at less-trusted brownfield repos, so introspection runs in a **subprocess with a scrubbed
environment** (no inherited secrets), a **bounded timeout**, and **fail-closed** semantics: any
import-time exception, timeout, partial import, or unparseable result aborts with no facts
returned (never map the subset that imported — R1-S2).

The pure introspection logic is in ``introspect.py``; the subprocess entrypoint is
``_introspect_subproc.py``. This module is the trusted parent that spawns and guards it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from startd8.logging_config import get_logger

from .introspect import DeriveImportError, IntrospectionResult

logger = get_logger(__name__)

DEFAULT_TIMEOUT_S = 30.0
# Only these env vars cross into the subprocess — no API keys, tokens, or other secrets.
_SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SystemRoot")


def _sdk_src_root() -> str:
    """The directory containing the importable ``startd8`` package (so the subprocess can import
    the introspection logic). Derived from this file's location: …/src/startd8/concierge/derive."""
    return str(Path(__file__).resolve().parents[3])


def _scrubbed_env(project_pythonpath: Optional[str]) -> dict:
    """A minimal environment: PATH/locale only + a PYTHONPATH covering the SDK and the target
    project. Deliberately omits everything else the parent holds (secrets stay in the parent)."""
    env = {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ}
    parts = [project_pythonpath, _sdk_src_root()] if project_pythonpath else [_sdk_src_root()]
    env["PYTHONPATH"] = os.pathsep.join(p for p in parts if p)
    env["PYTHONUNBUFFERED"] = "1"
    # Refuse network for the pure-introspection path is not enforced here (documented posture);
    # offline DNS/socket policy is the operator env's job. The scrubbed secrets are the control.
    return env


def run_contained_introspection(
    modules: List[str],
    *,
    project_pythonpath: Optional[str] = None,
    model_names: Optional[List[str]] = None,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> IntrospectionResult:
    """Introspect *modules* in a contained subprocess (FR-DC-14). Returns the facts, or raises
    ``DeriveImportError`` (fail-closed) on any import error, timeout, non-zero exit, or unparseable
    output — never a partial result.

    *project_pythonpath* puts the target project's sources on the subprocess path; *model_names*
    restricts to specific classes (FR-DC-3 explicit selection)."""
    request = json.dumps({"modules": list(modules), "model_names": model_names})
    env = _scrubbed_env(project_pythonpath)
    logger.info("derive.introspect contained: modules=%s timeout=%ss", modules, timeout)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "startd8.concierge.derive._introspect_subproc"],
            input=request, env=env, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise DeriveImportError(
            f"introspection timed out after {timeout}s (fail-closed; no contract emitted)"
        ) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()[-1:] or ["(no stderr)"]
        raise DeriveImportError(
            f"target import/introspection failed (fail-closed): {detail[0][:400]}"
        )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise DeriveImportError(
            "introspection produced no parseable result (fail-closed)"
        ) from exc
    return IntrospectionResult.from_dict(data)
