#!/usr/bin/env python3
"""Preflight S4 suite-authoring analysis without executing untrusted suites.

The preflight is deliberately fail-closed.  It permits only an accepted promoted
batch and an accepted oracle/mutant gate, creates auditable placeholder matrices,
and requires a reviewed isolated bridge before model-authored Python is executed.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
AUDIT_ROOT = REPO / "docs/design/benchmark-bias-audit/bias_audit_openai"
DEFAULT_STORE_ROOT = REPO / ".startd8/bias-audit-store"
DEFAULT_BATCH_ID = "pricing-cross-tool-authoring-v1"
DEFAULT_RESULTS_ROOT = AUDIT_ROOT / "analysis/s4-results"
DEFAULT_GATE = AUDIT_ROOT / "oracle/validation-gate.json"
DEFAULT_MUTANTS = AUDIT_ROOT / "mutants/manifest.json"
DEFAULT_PRE_REGISTRATION = AUDIT_ROOT / "analysis/s4-pre-registration.json"
DEFAULT_BRIDGE_MANIFEST = AUDIT_ROOT / "analysis/s4-bridge-manifest.json"
DEFAULT_SUITE_DISPOSITIONS = AUDIT_ROOT / "analysis/s4-suite-dispositions.json"
ALLOWED_SUITE_DISPOSITION_REASONS = {
    "suite_over_specifies_canonical_output_shape",
}

SECRET_ENV_MARKERS = (
    "API_KEY", "_TOKEN", "TOKEN_", "_SECRET", "SECRET_", "PASSWORD",
    "ANTHROPIC", "OPENAI", "GOOGLE", "GEMINI", "MISTRAL", "NVIDIA",
    "AWS_", "DOPPLER", "_KEY", "CREDENTIAL",
)
SAFE_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "SystemRoot")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def scrub_bridge_env(workspace: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    source = dict(os.environ if base is None else base)
    clean = {
        key: value for key, value in source.items()
        if key in SAFE_ENV_KEYS and not any(marker in key.upper() for marker in SECRET_ENV_MARKERS)
    }
    clean["HOME"] = str(workspace)
    clean["TMPDIR"] = str(workspace)
    clean["PYTHONDONTWRITEBYTECODE"] = "1"
    clean["PYTHONUNBUFFERED"] = "1"
    return clean


def bridge_pythonpath(workspace: Path) -> str:
    """Return a narrow import path for isolated bridge execution.

    The caller's PYTHONPATH can contain arbitrary project directories and is deliberately scrubbed.
    Pytest may still need installed site-packages (for example terminal/color dependencies), so the
    bridge reconstructs a minimal path from the isolated workspace plus current interpreter
    site-packages entries only.
    """
    paths = [str(workspace)]
    for value in sys.path:
        if value and "site-packages" in value and value not in paths:
            paths.append(value)
    return os.pathsep.join(paths)


def bridge_caps() -> dict[str, bool]:
    return {
        "sandbox_exec": sys.platform == "darwin" and shutil.which("sandbox-exec") is not None,
        "unshare": sys.platform.startswith("linux") and shutil.which("unshare") is not None,
    }


def wrap_no_egress_command(cmd: list[str], caps: dict[str, bool]) -> tuple[list[str], str | None]:
    if caps.get("sandbox_exec"):
        profile = "(version 1)(allow default)(deny network*)"
        return ["sandbox-exec", "-p", profile, *cmd], "seatbelt-no-egress"
    if caps.get("unshare"):
        return ["unshare", "-rn", *cmd], "linux-netns-no-egress"
    return cmd, None


def bridge_dry_run_gate(
    bridge_manifest_path: Path, results_root: Path, *,
    caps: dict[str, bool] | None = None,
    runner=subprocess.run,
) -> tuple[dict, list[str]]:
    """Validate reviewed S4 bridge prerequisites without importing or running generated suites."""
    errors: list[str] = []
    if not bridge_manifest_path.is_file():
        return {
            "status": "not_installed",
            "manifest_path": str(bridge_manifest_path),
            "dry_run": "not_run",
        }, [f"reviewed S4 bridge manifest is not installed:{bridge_manifest_path}"]

    try:
        manifest = load_json(bridge_manifest_path, "S4 bridge manifest")
    except ValueError as exc:
        return {
            "status": "invalid_manifest",
            "manifest_path": str(bridge_manifest_path),
            "dry_run": "not_run",
        }, [str(exc)]

    if manifest.get("status") != "reviewed":
        errors.append("reviewed S4 bridge manifest status is not reviewed")
    if manifest.get("require_no_egress") is not True:
        errors.append("reviewed S4 bridge manifest does not require no-egress isolation")
    if manifest.get("require_scrubbed_env") is not True:
        errors.append("reviewed S4 bridge manifest does not require scrubbed environment")
    if manifest.get("require_identical_inventory") is not True:
        errors.append("reviewed S4 bridge manifest does not require identical target inventory")

    caps = bridge_caps() if caps is None else caps
    dry_workspace = results_root / "bridge-dry-run-workspace"
    dry_workspace.mkdir(parents=True, exist_ok=True)
    command, isolation = wrap_no_egress_command(
        [sys.executable, "-c", "print('s4-bridge-dry-run-ok')"], caps
    )
    if isolation is None:
        errors.append("no real no-egress isolation capability available for S4 bridge dry-run")

    timeout_s = float(manifest.get("timeout_seconds", 10))
    max_output = int(manifest.get("max_output_bytes", 4096))
    dry_run = {
        "workspace": str(dry_workspace),
        "isolation": isolation,
        "timeout_seconds": timeout_s,
        "max_output_bytes": max_output,
    }
    if isolation is not None and not errors:
        try:
            proc = runner(
                command,
                cwd=str(dry_workspace),
                env=scrub_bridge_env(dry_workspace),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            dry_run.update({
                "returncode": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-max_output:],
                "stderr_tail": (proc.stderr or "")[-max_output:],
            })
            if proc.returncode != 0:
                errors.append(f"S4 bridge dry-run failed:{proc.returncode}")
        except subprocess.TimeoutExpired:
            dry_run["timed_out"] = True
            errors.append(f"S4 bridge dry-run timed out after {timeout_s}s")

    return {
        "status": "ready" if not errors else "blocked",
        "manifest_path": str(bridge_manifest_path),
        "manifest_sha256": sha256(bridge_manifest_path),
        "capabilities": caps,
        "dry_run": dry_run,
    }, errors


def bridge_executor_gate(manifest_path: Path) -> tuple[dict, list[str]]:
    """Validate reviewed executor manifest fields before semantic suite execution."""
    errors: list[str] = []
    try:
        manifest = load_json(manifest_path, "S4 bridge manifest")
    except ValueError as exc:
        return {"status": "invalid_manifest", "manifest_path": str(manifest_path)}, [str(exc)]
    executor = manifest.get("executor")
    if not isinstance(executor, dict):
        errors.append("reviewed S4 bridge manifest has no executor section")
        executor = {}
    if manifest.get("allow_semantic_execution") is not True:
        errors.append("reviewed S4 bridge manifest does not allow semantic execution")
    if executor.get("status") != "reviewed":
        errors.append("reviewed S4 bridge executor status is not reviewed")
    if executor.get("require_opt_in_flag") is not True:
        errors.append("reviewed S4 bridge executor does not require explicit opt-in flag")
    if executor.get("suite_module_name") != "suite":
        errors.append("reviewed S4 bridge executor must load generated suites as module 'suite'")
    if executor.get("target_function") != "assess_lines":
        errors.append("reviewed S4 bridge executor target function must be assess_lines")
    return {
        "status": "ready" if not errors else "blocked",
        "manifest_path": str(manifest_path),
        "executor": executor,
    }, errors


def suite_disposition_gate(
    disposition_path: Path,
    *,
    batch_id: str,
    suites: list[dict],
) -> tuple[dict[str, dict], dict, list[str]]:
    """Load reviewed suite-level S4 exclusions without mutating generated suites."""
    if not disposition_path.is_file():
        return {}, {"status": "not_installed", "path": str(disposition_path), "exclusions": []}, []

    errors: list[str] = []
    try:
        manifest = load_json(disposition_path, "S4 suite disposition manifest")
    except ValueError as exc:
        return {}, {"status": "invalid", "path": str(disposition_path), "exclusions": []}, [str(exc)]

    if manifest.get("status") != "reviewed":
        errors.append("S4 suite disposition manifest status is not reviewed")
    if manifest.get("batch_id") != batch_id:
        errors.append("S4 suite disposition manifest batch_id does not match requested batch")

    suite_by_id = {suite["run_id"]: suite for suite in suites if suite.get("run_id")}
    exclusions = manifest.get("exclusions")
    if not isinstance(exclusions, list):
        errors.append("S4 suite disposition manifest exclusions must be a list")
        exclusions = []

    accepted: dict[str, dict] = {}
    normalized_exclusions = []
    for index, exclusion in enumerate(exclusions):
        if not isinstance(exclusion, dict):
            errors.append(f"S4 suite disposition exclusion is not an object:{index}")
            continue
        run_id = exclusion.get("run_id")
        reason_class = exclusion.get("reason_class")
        normalized_sha = exclusion.get("normalized_sha256")
        disposition = exclusion.get("disposition")
        if not isinstance(run_id, str) or not run_id:
            errors.append(f"S4 suite disposition exclusion missing run_id:{index}")
            continue
        suite = suite_by_id.get(run_id)
        if suite is None:
            errors.append(f"S4 suite disposition references unknown run_id:{run_id}")
            continue
        if normalized_sha != suite.get("normalized_sha256"):
            errors.append(f"S4 suite disposition normalized_sha256 mismatch:{run_id}")
        if reason_class not in ALLOWED_SUITE_DISPOSITION_REASONS:
            errors.append(f"S4 suite disposition reason_class is not allowed:{run_id}:{reason_class}")
        if disposition != "exclude_from_s4_evidence":
            errors.append(f"S4 suite disposition action is not allowed:{run_id}:{disposition}")
        record = {
            "run_id": run_id,
            "normalized_sha256": normalized_sha,
            "reason_class": reason_class,
            "disposition": disposition,
            "reviewed_by": exclusion.get("reviewed_by", manifest.get("reviewer")),
            "rationale": exclusion.get("rationale"),
        }
        normalized_exclusions.append(record)
        accepted[run_id] = record

    if errors:
        accepted = {}

    status = "reviewed" if not errors else "blocked"
    return accepted, {
        "status": status,
        "path": str(disposition_path),
        "exclusions": normalized_exclusions,
    }, errors


def accepted_suite_rows(ledger: dict) -> list[dict]:
    return [
        row
        for row in ledger.get("runs", [])
        if row.get("status") == "accepted" and row.get("experiment") == "suite_author"
    ]


def suite_author_rows(ledger: dict) -> list[dict]:
    return [row for row in ledger.get("runs", []) if row.get("experiment") == "suite_author"]


def validated_suite_replacement_ids(ledger: dict) -> tuple[set[str], list[str]]:
    """Return rejected suite run IDs that have an accepted replacement.

    A disposition is not enough by itself to suppress a rejected suite row. S4 may ignore the
    rejected row only when the replacement relationship is explicit and the replacement row is an
    accepted `suite_author` artifact in the same intake ledger.
    """
    errors: list[str] = []
    replaced_run_ids: set[str] = set()
    rows_by_id = {
        row.get("run_id"): row
        for row in ledger.get("runs", [])
        if isinstance(row.get("run_id"), str) and row.get("run_id")
    }
    dispositions = ledger.get("dispositions", [])
    if not isinstance(dispositions, list):
        return set(), ["intake ledger dispositions must be a list"]

    for index, disposition in enumerate(dispositions):
        if not isinstance(disposition, dict):
            errors.append(f"invalid suite replacement disposition:{index}:not_object")
            continue
        rejected_id = disposition.get("rejected_run_id")
        replacement_id = disposition.get("replacement_run_id")
        if not isinstance(rejected_id, str) or not rejected_id:
            errors.append(f"invalid suite replacement disposition:{index}:missing rejected_run_id")
            continue
        if not isinstance(replacement_id, str) or not replacement_id:
            errors.append(f"invalid suite replacement disposition:{index}:missing replacement_run_id")
            continue
        rejected_row = rows_by_id.get(rejected_id)
        replacement_row = rows_by_id.get(replacement_id)
        if rejected_row is None:
            errors.append(f"suite replacement disposition references missing rejected run:{rejected_id}")
            continue
        if replacement_row is None:
            errors.append(f"suite replacement disposition references missing replacement run:{replacement_id}")
            continue
        if rejected_row.get("experiment") != "suite_author":
            errors.append(f"suite replacement rejected run is not suite_author:{rejected_id}")
            continue
        if replacement_row.get("experiment") != "suite_author":
            errors.append(f"suite replacement replacement run is not suite_author:{replacement_id}")
            continue
        if replacement_row.get("status") != "accepted":
            errors.append(f"suite replacement run is not accepted:{replacement_id}")
            continue
        replaced_run_ids.add(rejected_id)
    return replaced_run_ids, errors


def normalized_suite_record(batch_root: Path, row: dict, run_dir: str) -> tuple[dict, list[str]]:
    """Validate the promoted normalized suite artifact before any bridge inspection.

    S4 must consume exactly the artifact admitted by intake. Missing files, missing hashes, or
    checksum drift are input-gate failures, not bridge failures and never execution evidence.
    """
    errors: list[str] = []
    run_id = row.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return {
            "run_id": run_id,
            "status": "invalid_intake",
            "detail": "accepted suite_author row has no run_id",
        }, ["intake accepted suite_author row has no run_id"]

    suite_path = batch_root / "normalized" / run_dir / "suite.py"
    manifest_path = batch_root / "normalized" / run_dir / "suite_manifest.json"
    expected_sha = row.get("normalized_sha256")
    actual_sha = sha256(suite_path) if suite_path.is_file() else None

    if not suite_path.is_file():
        errors.append(f"accepted suite_author missing normalized suite.py:{run_id}")
    if not manifest_path.is_file():
        errors.append(f"accepted suite_author missing normalized suite_manifest.json:{run_id}")
    if not isinstance(expected_sha, str) or not expected_sha:
        errors.append(f"accepted suite_author missing normalized_sha256:{run_id}")
    elif actual_sha is not None and actual_sha != expected_sha:
        errors.append(f"accepted suite_author normalized_sha256 mismatch:{run_id}")

    record = {
        "run_id": run_id,
        "author_vendor": row.get("author_vendor"),
        "sample_index": row.get("sample_index"),
        "normalized_sha256": expected_sha,
        "normalized_sha256_actual": actual_sha,
        "suite_path": str(suite_path),
        "manifest_path": str(manifest_path),
        "intake_status": row.get("status"),
    }
    return record, errors


def declared_bridge_contract(suite_path: Path, manifest_path: Path) -> dict:
    """Describe a declared adapter convention without importing model-authored code."""
    try:
        tree = ast.parse(suite_path.read_text(encoding="utf-8"), filename=str(suite_path))
        functions = sorted(node.name for node in tree.body if isinstance(node, ast.FunctionDef))
    except (OSError, SyntaxError) as exc:
        return {"status": "invalid_execution", "detail": f"static_parse_failed:{type(exc).__name__}"}

    try:
        manifest = load_json(manifest_path, "suite manifest")
    except ValueError as exc:
        return {"status": "invalid_execution", "detail": str(exc)}

    conventions = [
        name
        for name in ("configure", "bind_invoker", "run_all", "run_case", "run_ok_cases", "run_invalid_cases")
        if name in functions
    ]
    bridge_contract = manifest.get("bridge_contract")
    if not isinstance(bridge_contract, dict):
        return {
            "status": "not_executable",
            "detail": "suite_manifest.json missing top-level bridge_contract object",
            "declared_manifest_fields": [key for key in ("adapter_contract", "invoker_contract", "harness_notes") if key in manifest],
            "conventions": conventions,
        }

    declared_callable_names = _declared_callable_names(bridge_contract)
    if not isinstance(declared_callable_names, list) or not all(isinstance(name, str) for name in declared_callable_names):
        return {
            "status": "not_executable",
            "detail": "bridge_contract missing callable_names list",
            "declared_manifest_fields": ["bridge_contract"],
            "conventions": conventions,
        }

    declared_conventions = sorted(set(declared_callable_names).intersection(conventions))
    if not declared_conventions:
        return {
            "status": "not_executable",
            "detail": "bridge_contract callable_names do not match exported suite.py bridge callables",
            "declared_manifest_fields": ["bridge_contract"],
            "declared_callable_names": declared_callable_names,
            "conventions": conventions,
        }

    missing_contract_fields = []
    if not any(key in bridge_contract for key in ("request_shape", "request", "input_shape")):
        missing_contract_fields.append("request_shape")
    if not any(key in bridge_contract for key in ("response_shape", "response", "output_shape")):
        missing_contract_fields.append("response_shape")
    if not any(
        key in bridge_contract
        for key in (
            "invalid_argument_convention",
            "invalid_argument_signal",
            "invalid_argument_signaling",
            "invalid_argument_signaling_convention",
            "invalid_argument",
            "invalid_case_convention",
            "error_convention",
        )
    ):
        missing_contract_fields.append("invalid_argument_convention")
    if missing_contract_fields:
        return {
            "status": "not_executable",
            "detail": f"bridge_contract missing required fields:{','.join(missing_contract_fields)}",
            "declared_manifest_fields": ["bridge_contract"],
            "declared_callable_names": declared_callable_names,
            "conventions": conventions,
        }

    return {
        "status": "bridge_required",
        "detail": "declared bridge_contract found; reviewed isolated S4 bridge required",
        "declared_manifest_fields": ["bridge_contract"],
        "declared_callable_names": declared_callable_names,
        "conventions": conventions,
    }


def _callable_basename(value: str) -> str:
    """Normalize manifest callable declarations such as ``run_all(call=None)``."""
    return value.split("(", 1)[0].strip()


def _declared_callable_names(bridge_contract: dict) -> list[str] | None:
    """Extract callable names from reviewed prompt-era aliases.

    Earlier bridge manifests expected ``callable_names`` as a list. Later authoring prompt
    variants also produce ``callables`` / ``exported_callables`` as either a list or an object
    mapping callable name to description. The bridge admission check can safely normalize these
    declaration shapes without mutating generated artifacts.
    """
    declared = bridge_contract.get("callable_names")
    if declared is None:
        declared = bridge_contract.get("callables")
    if declared is None:
        declared = bridge_contract.get("exported_callables")
    if isinstance(declared, dict):
        declared = list(declared)
    if isinstance(declared, str):
        declared = [declared]
    if isinstance(declared, list):
        return [
            _callable_basename(item)
            for item in declared
            if isinstance(item, str) and _callable_basename(item)
        ]
    return declared


def bridge_adapter_source() -> str:
    """Return the reviewed pytest bridge used inside each isolated execution workspace."""
    return r'''
import importlib

import pytest

import suite
import target_module


class BridgeInvalidArgument(Exception):
    def __init__(self, message="INVALID_ARGUMENT"):
        super().__init__(message)
        self.code = "INVALID_ARGUMENT"


DISCOUNT_STRATEGY = {
    0: "DISCOUNT_STRATEGY_UNSPECIFIED",
    1: "DISCOUNT_STRATEGY_CASCADE",
    2: "DISCOUNT_STRATEGY_SUM",
}
ROUNDING_MODE = {
    0: "ROUNDING_MODE_UNSPECIFIED",
    1: "ROUNDING_MODE_HALF_EVEN",
    2: "ROUNDING_MODE_HALF_UP",
    3: "ROUNDING_MODE_DOWN",
}
REDUCTION_KIND = {
    0: "REDUCTION_KIND_UNSPECIFIED",
    1: "REDUCTION_KIND_PERCENT_LEVELS",
    2: "REDUCTION_KIND_FIXED_AMOUNT",
}
MONEY_FIELDS = {
    "unit_amount",
    "comparison_unit_amount",
    "candidate_unit_amount",
    "selected_unit_amount",
    "line_base_amount",
    "line_due_amount",
    "base_amount",
    "reduction_amount",
    "due_amount",
    "amount",
}


def _amount_in(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return {"decimal": value}
    return value


def _normalize_request(value, key=None):
    if isinstance(value, list):
        return [_normalize_request(item) for item in value]
    if isinstance(value, dict):
        normalized = {
            k: _normalize_request(v, k)
            for k, v in value.items()
            if v is not None
        }
        if "lines" in normalized and "currency_code" not in normalized:
            normalized["currency_code"] = ""
        return normalized
    if key in MONEY_FIELDS:
        return _amount_in(value)
    if key == "discount_strategy":
        return DISCOUNT_STRATEGY.get(value, value)
    if key == "rounding_mode":
        return ROUNDING_MODE.get(value, value)
    if key == "kind":
        return REDUCTION_KIND.get(value, value)
    return value


def _money_out(value):
    if isinstance(value, dict) and set(value) == {"decimal"}:
        return value["decimal"]
    return value


def _bare_response(value):
    if isinstance(value, list):
        return [_bare_response(item) for item in value]
    if isinstance(value, dict):
        return {k: _bare_response(_money_out(v)) for k, v in value.items()}
    return value


def _target_call(request):
    try:
        return target_module.assess_lines(_normalize_request(request))
    except Exception as exc:
        raise BridgeInvalidArgument(str(exc)) from exc


def _raise_suite_invalid_for(module, message):
    if hasattr(module, "RpcStatusError"):
        raise module.RpcStatusError("INVALID_ARGUMENT", message)
    if hasattr(module, "InvalidArgument"):
        raise module.InvalidArgument(message)
    if hasattr(module, "InvalidRequest"):
        raise module.InvalidRequest(message)
    raise BridgeInvalidArgument(message)


def _target_call_suite_native_for(module, request):
    try:
        return target_module.assess_lines(_normalize_request(request))
    except Exception as exc:
        _raise_suite_invalid_for(module, str(exc))


def _target_call_suite_native(request):
    return _target_call_suite_native_for(suite, request)


def _target_call_bare(request):
    return _bare_response(_target_call(request))


def _target_call_suite_native_bare(request):
    return _bare_response(_target_call_suite_native(request))


def _target_call_suite_native_bare_for(module, request):
    return _bare_response(_target_call_suite_native_for(module, request))


def _target_result_mapping(request):
    try:
        return {"ok": True, "response": _target_call_bare(request), "code": None}
    except BridgeInvalidArgument:
        return {"ok": False, "response": None, "code": "INVALID_ARGUMENT"}


class _Client:
    def assess(self, request):
        return _target_call_bare(request)

    def AssessLines(self, request):
        return _target_call(request)


def _bind_suite_module(module):
    if hasattr(module, "configure"):
        module.configure(_target_result_mapping)
    if hasattr(module, "bind_invoker"):
        module.bind_invoker(lambda request, _module=module: _target_call_suite_native_for(_module, request))
    if hasattr(module, "set_client"):
        module.set_client(_Client())
    if hasattr(module, "INVOKER"):
        module.INVOKER = _target_call
    if hasattr(module, "ASSESS_FN"):
        module.ASSESS_FN = lambda request, _module=module: _target_call_suite_native_for(_module, request)
    if hasattr(module, "INVALID_ARGUMENT_EXCEPTIONS"):
        try:
            module.INVALID_ARGUMENT_EXCEPTIONS = tuple(set(tuple(module.INVALID_ARGUMENT_EXCEPTIONS) + (BridgeInvalidArgument,)))
        except TypeError:
            module.INVALID_ARGUMENT_EXCEPTIONS = (BridgeInvalidArgument,)


def pytest_configure(config):
    _bind_suite_module(suite)


def pytest_collection_modifyitems(session, config, items):
    for item in items:
        module = getattr(item, "module", None)
        if module is not None:
            _bind_suite_module(module)
'''


def bridge_contract_test_source() -> str:
    """Return reviewed pytest tests for callable-only suite bridge conventions."""
    return r'''
import inspect

import suite
from conftest import (
    _Client,
    _target_call_suite_native,
    _target_call_suite_native_bare,
)


def _accepts_argument(fn):
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return True
    required = [
        param for param in signature.parameters.values()
        if param.default is inspect.Parameter.empty
        and param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return bool(required)


def _call_with_optional_adapter(fn, adapter):
    if _accepts_argument(fn):
        return fn(adapter)
    return fn()


def test_bridge_callable_ok_cases_if_declared():
    fn = getattr(suite, "run_ok_cases", None)
    if fn is None:
        return
    _call_with_optional_adapter(fn, _target_call_suite_native)


def test_bridge_callable_invalid_cases_if_declared():
    fn = getattr(suite, "run_invalid_cases", None)
    if fn is None:
        return
    _call_with_optional_adapter(fn, _target_call_suite_native)


def test_bridge_callable_golden_if_declared():
    fn = getattr(suite, "run_golden", None)
    if fn is None:
        return
    _call_with_optional_adapter(fn, _target_call_suite_native)


def test_bridge_callable_run_all_if_declared():
    fn = getattr(suite, "run_all", None)
    if fn is None:
        return
    try:
        fn(_Client())
    except TypeError:
        try:
            fn(_target_call_suite_native_bare)
        except TypeError:
            fn()
'''


def target_source_path(target: dict, mutants_path: Path, oracle_path: Path) -> Path | None:
    if target.get("target_id") == "reference_oracle":
        return oracle_path
    source = target.get("source")
    if isinstance(source, str):
        return mutants_path.parent / source
    return None


def execute_bridge_cell(
    suite_record: dict,
    target: dict,
    *,
    results_root: Path,
    mutants_path: Path,
    oracle_path: Path,
    bridge: dict,
    runner=subprocess.run,
) -> dict:
    """Execute one suite/target pair in an isolated copied workspace."""
    run_id = suite_record["run_id"]
    target_id = target["target_id"]
    disposition = suite_record.get("s4_disposition")
    if disposition:
        return {
            "suite_run_id": run_id,
            "target_id": target_id,
            "status": "excluded",
            "detail": disposition.get("reason_class"),
            "disposition": disposition,
        }
    if suite_record.get("bridge", {}).get("status") != "bridge_required":
        return {
            "suite_run_id": run_id,
            "target_id": target_id,
            "status": "not_executable",
            "detail": suite_record.get("bridge", {}).get("detail"),
        }

    source_path = target_source_path(target, mutants_path, oracle_path)
    if source_path is None or not source_path.is_file():
        return {
            "suite_run_id": run_id,
            "target_id": target_id,
            "status": "invalid_target",
            "detail": f"target source is missing:{target_id}",
        }

    workspace = results_root / "bridge-exec-workspace" / run_id / target_id
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copy2(suite_record["suite_path"], workspace / "suite.py")
    shutil.copy2(source_path, workspace / "target_module.py")
    reference_oracle = oracle_path
    if reference_oracle.is_file():
        shutil.copy2(reference_oracle, workspace / "reference_oracle.py")
    (workspace / "conftest.py").write_text(textwrap.dedent(bridge_adapter_source()).lstrip(), encoding="utf-8")
    (workspace / "test_bridge_contract.py").write_text(
        textwrap.dedent(bridge_contract_test_source()).lstrip(),
        encoding="utf-8",
    )

    command, isolation = wrap_no_egress_command(
        [sys.executable, "-m", "pytest", "-q", "suite.py", "test_bridge_contract.py", "--tb=short"],
        bridge.get("capabilities", {}),
    )
    if isolation is None:
        return {
            "suite_run_id": run_id,
            "target_id": target_id,
            "status": "blocked",
            "detail": "no real no-egress isolation available for bridge execution",
        }

    timeout_s = float(bridge.get("dry_run", {}).get("timeout_seconds", 10))
    max_output = int(bridge.get("dry_run", {}).get("max_output_bytes", 4096))
    try:
        proc = runner(
            command,
            cwd=str(workspace),
            env={**scrub_bridge_env(workspace), "PYTHONPATH": bridge_pythonpath(workspace)},
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "suite_run_id": run_id,
            "target_id": target_id,
            "status": "timeout",
            "workspace": str(workspace),
            "isolation": isolation,
        }

    return {
        "suite_run_id": run_id,
        "target_id": target_id,
        "status": "pass" if proc.returncode == 0 else "fail",
        "returncode": proc.returncode,
        "workspace": str(workspace),
        "isolation": isolation,
        "stdout_tail": (proc.stdout or "")[-max_output:],
        "stderr_tail": (proc.stderr or "")[-max_output:],
    }


def execute_reviewed_bridge(
    suites: list[dict],
    targets: list[dict],
    *,
    results_root: Path,
    mutants_path: Path,
    oracle_path: Path,
    bridge: dict,
    runner=subprocess.run,
) -> dict:
    cells = []
    for suite_record in suites:
        for target in targets:
            cells.append(execute_bridge_cell(
                suite_record,
                target,
                results_root=results_root,
                mutants_path=mutants_path,
                oracle_path=oracle_path,
                bridge=bridge,
                runner=runner,
            ))
    terminal = {"pass", "fail", "not_executable", "excluded"}
    return {
        "status": "complete" if cells and all(cell["status"] in terminal for cell in cells) else "blocked",
        "cells": cells,
    }


def target_inventory(manifest: dict, manifest_path: Path) -> list[dict]:
    targets = [{"target_id": "reference_oracle", "status": "accepted"}]
    for mutant in manifest.get("mutants", []):
        if mutant.get("status", manifest.get("status")) != "accepted":
            continue
        source = mutant.get("source") or mutant.get("path")
        record = {"target_id": mutant.get("id", "unnamed_mutant"), "status": "accepted"}
        if isinstance(source, str):
            candidate = manifest_path.parent / source
            record["source"] = source
            if candidate.is_file():
                record["sha256"] = sha256(candidate)
        targets.append(record)
    return targets


def write_matrices(results_root: Path, suite_rows: list[dict], targets: list[dict], cells: list[dict] | None = None) -> None:
    results_root.mkdir(parents=True, exist_ok=True)
    ids = [row["run_id"] for row in suite_rows]
    by_cell = {
        (cell["suite_run_id"], cell["target_id"]): cell["status"]
        for cell in (cells or [])
    }
    with (results_root / "mutant_kill_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["suite_run_id", "execution_status", *[target["target_id"] for target in targets]])
        for suite_id in ids:
            statuses = [by_cell.get((suite_id, target["target_id"]), "not_executed") for target in targets]
            if statuses and all(status == "excluded" for status in statuses):
                execution_status = "excluded"
            else:
                execution_status = "executed" if any(status != "not_executed" for status in statuses) else "not_executed"
            writer.writerow([suite_id, execution_status, *statuses])
    with (results_root / "suite_equivalence_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["suite_run_id", *ids])
        for suite_id in ids:
            writer.writerow([suite_id, *["not_executed" for _ in ids]])


def run_preflight(
    *, store_root: Path, batch_id: str, results_root: Path, gate_path: Path,
    mutants_path: Path, pre_registration_path: Path, bridge_manifest_path: Path = DEFAULT_BRIDGE_MANIFEST,
    suite_disposition_path: Path = DEFAULT_SUITE_DISPOSITIONS,
    execute_reviewed: bool = False,
) -> tuple[int, dict]:
    errors: list[str] = []
    try:
        pre_registration = load_json(pre_registration_path, "S4 pre-registration")
    except ValueError as exc:
        return 2, {"status": "blocked", "errors": [str(exc)]}
    if pre_registration.get("status") != "pre_registered":
        errors.append("S4 pre-registration is not frozen")
    if pre_registration.get("batch_id") != batch_id:
        errors.append("S4 pre-registration batch_id does not match requested batch")

    batch_root = store_root / batch_id
    try:
        reconciliation = load_json(batch_root / "reconciliation-report.json", "reconciliation report")
        ledger = load_json(batch_root / "intake-ledger.json", "intake ledger")
        gate = load_json(gate_path, "oracle gate")
        mutant_manifest = load_json(mutants_path, "mutant manifest")
    except ValueError as exc:
        errors.append(str(exc))
        reconciliation, ledger, gate, mutant_manifest = {}, {}, {}, {}

    if reconciliation.get("status") != "accepted":
        errors.append("promoted batch reconciliation is not accepted")
    if gate.get("status") != "accepted":
        errors.append("oracle/mutant gate is not accepted")
    if mutant_manifest.get("status") != "accepted":
        errors.append("mutant manifest is not accepted")

    # Build a lookup from run_id to run_dir name from the reconciliation report
    run_dir_by_id = {}
    for run in reconciliation.get("runs", []):
        r_id = run.get("metadata", {}).get("run_id")
        r_dir = run.get("run_dir")
        if r_id and r_dir:
            run_dir_by_id[r_id] = r_dir

    replaced_run_ids, replacement_errors = validated_suite_replacement_ids(ledger)
    errors.extend(replacement_errors)

    all_suite_rows = suite_author_rows(ledger)
    rejected_suite_rows = [
        row for row in all_suite_rows
        if row.get("status") != "accepted" and row.get("run_id") not in replaced_run_ids
    ]
    if rejected_suite_rows:
        errors.append(f"intake ledger has rejected suite_author artifacts:{len(rejected_suite_rows)}")

    suite_rows = accepted_suite_rows(ledger)
    if not suite_rows:
        errors.append("intake ledger has no accepted suite_author artifacts")
    targets = target_inventory(mutant_manifest, mutants_path)
    if len(targets) == 1:
        errors.append("mutant manifest has no accepted executable mutants")

    suites = []
    for row in suite_rows:
        run_id = row.get("run_id")
        run_dir = run_dir_by_id.get(run_id, run_id) # Fallback to run_id if missing
        suite_record, suite_errors = normalized_suite_record(batch_root, row, run_dir)
        errors.extend(suite_errors)
        if suite_errors:
            suite_record["bridge"] = {
                "status": "invalid_intake",
                "detail": "normalized suite artifact failed S4 intake invariants",
            }
        else:
            suite_record["bridge"] = declared_bridge_contract(
                Path(suite_record["suite_path"]), Path(suite_record["manifest_path"])
            )
            if suite_record["bridge"].get("status") != "bridge_required":
                errors.append(
                    f"S4 suite bridge contract invalid:{run_id}:{suite_record['bridge'].get('detail')}"
                )
        suites.append(suite_record)

    suite_dispositions, suite_disposition_summary, suite_disposition_errors = suite_disposition_gate(
        suite_disposition_path,
        batch_id=batch_id,
        suites=suites,
    )
    errors.extend(suite_disposition_errors)
    for suite_record in suites:
        disposition = suite_dispositions.get(suite_record.get("run_id"))
        if disposition:
            suite_record["s4_disposition"] = disposition

    bridge, bridge_errors = bridge_dry_run_gate(bridge_manifest_path, results_root)
    errors.extend(bridge_errors)
    execution = {"status": "not_requested", "cells": []}
    if execute_reviewed:
        executor, executor_errors = bridge_executor_gate(bridge_manifest_path)
        errors.extend(executor_errors)
        if bridge.get("status") == "ready" and not executor_errors:
            execution = execute_reviewed_bridge(
                suites,
                targets,
                results_root=results_root,
                mutants_path=mutants_path,
                oracle_path=gate_path.parent / "reference_oracle.py",
                bridge=bridge,
            )
            for cell in execution.get("cells", []):
                if cell.get("target_id") == "reference_oracle" and cell.get("status") == "fail":
                    errors.append(f"S4 bridge reference oracle failed:{cell['suite_run_id']}")
                elif cell.get("status") not in {"pass", "fail", "not_executable", "excluded"}:
                    errors.append(
                        f"S4 bridge execution cell error:{cell['suite_run_id']}:{cell['target_id']}:{cell['status']}"
                    )
        else:
            execution = {"status": "blocked", "executor": executor, "cells": []}
    else:
        errors.append("S4 reviewed bridge execution not requested; rerun with --execute-reviewed-bridge")
    write_matrices(results_root, suite_rows, targets, execution.get("cells"))
    output = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if execute_reviewed and not errors else "blocked",
        "phase": "S4_suite_authoring",
        "batch_id": batch_id,
        "pre_registration_sha256": sha256(pre_registration_path),
        "inputs": {
            "store_root": str(store_root),
            "reconciliation_status": reconciliation.get("status"),
            "intake_status": {"accepted_suite_author": len(suite_rows), "total": ledger.get("total")},
            "oracle_gate_status": gate.get("status"),
            "mutant_manifest_status": mutant_manifest.get("status"),
        },
        "targets": targets,
        "suites": suites,
        "bridge": bridge,
        "suite_dispositions": suite_disposition_summary,
        "execution": execution,
        "matrix_cell_status": "executed" if execution.get("cells") else "not_executed",
        "errors": list(dict.fromkeys(errors)),
    }
    (results_root / "s4-preflight.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return (0 if output["status"] == "complete" else 2), output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE_ROOT)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--gate-path", type=Path, default=DEFAULT_GATE)
    parser.add_argument("--mutants-path", type=Path, default=DEFAULT_MUTANTS)
    parser.add_argument("--pre-registration-path", type=Path, default=DEFAULT_PRE_REGISTRATION)
    parser.add_argument("--bridge-manifest-path", type=Path, default=DEFAULT_BRIDGE_MANIFEST)
    parser.add_argument("--suite-disposition-path", type=Path, default=DEFAULT_SUITE_DISPOSITIONS)
    parser.add_argument("--execute-reviewed-bridge", action="store_true",
                        help="Opt in to reviewed isolated S4 bridge execution after all preflight gates pass.")
    args = parser.parse_args(argv)
    code, result = run_preflight(
        store_root=args.store_root, batch_id=args.batch_id, results_root=args.results_root,
        gate_path=args.gate_path, mutants_path=args.mutants_path,
        pre_registration_path=args.pre_registration_path, bridge_manifest_path=args.bridge_manifest_path,
        suite_disposition_path=args.suite_disposition_path,
        execute_reviewed=args.execute_reviewed_bridge,
    )
    print(json.dumps({"status": result["status"], "results_root": str(args.results_root), "errors": result["errors"]}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
