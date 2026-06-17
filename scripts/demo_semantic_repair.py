#!/usr/bin/env python3
"""Demonstrate the SDK's deterministic semantic-repair capability — $0, no LLM.

OQ-2 from REPAIR_CAPABILITY_CAPTURE_REQUIREMENTS.md: the benchmark runs frontier models whose raw
output is already disk-clean, so semantic repair idles there. This script *exercises* the capability
directly by feeding the four defect patterns the requirements doc specifies through the REAL repair
pipeline (`run_semantic_repair`, apply mode, all categories enabled), and showing the before→after
transform + the DC-3 pre/post disk-quality uplift. Deterministic AST repair — no model calls.

  python3 scripts/demo_semantic_repair.py
"""
from __future__ import annotations

import sys, tempfile, difflib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.repair.config import RepairConfig                       # noqa: E402
from startd8.repair.orchestrator import run_semantic_repair          # noqa: E402
from startd8.forward_manifest_validator import validate_disk_compliance  # noqa: E402
from startd8.contractors.prime_postmortem import compute_disk_quality_score  # noqa: E402

# The four defect patterns, verbatim from SEMANTIC_REPAIR_REQUIREMENTS.md (§19–22).
DEFECTS = {
    "method_resolution__locustfile.py": '''\
from locust import TaskSet

def index(l):
    l.client.get("/")

class UserBehavior(TaskSet):
    def on_start(self):
        self.index()
    tasks = {index: 1}
''',
    "discarded_return__config.py": '''\
import os

os.environ.get("GCP_PROJECT_ID")
os.environ.get("PORT", "8080")
''',
    "duplicate_main_guard__server.py": '''\
def main():
    pass

if __name__ == "__main__":
    main()

def setup():
    pass

if __name__ == "__main__":
    setup()
''',
    "import_resolution__email_client.py": '''\
from emailservice.email_server import EmailServiceStub

def make():
    return EmailServiceStub(None)
''',
}
CATS = frozenset({"method_resolution", "import_resolution", "discarded_return", "duplicate_main_guard"})


def _score(fp: Path, root: Path) -> float:
    try:
        return compute_disk_quality_score(validate_disk_compliance(str(fp), str(root)))
    except Exception:
        return float("nan")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # import_resolution needs a flat-layout service dir with a sibling email_server.py
        svc = root / "emailservice"; svc.mkdir()
        (svc / "email_server.py").write_text("class EmailServiceStub:\n    def __init__(self, ch): ...\n")
        files = []
        for name, body in DEFECTS.items():
            cat, fname = name.split("__")
            target = (svc / fname) if cat == "import_resolution" else (root / fname)
            target.write_text(body)
            files.append((cat, target))

        pre = {c: _score(fp, root) for c, fp in files}
        before = {c: fp.read_text() for c, fp in files}

        cfg = RepairConfig(semantic_repair_categories=CATS)
        result = run_semantic_repair([fp for _, fp in files], cfg, root)

        print("=" * 78)
        print("SDK SEMANTIC REPAIR — capability demonstration (deterministic, $0, no LLM)")
        print("=" * 78)
        print(f"issues_found={result.get('issues_found')}  issues_repaired={result.get('issues_repaired')}"
              f"  issues_unfixable={result.get('issues_unfixable')}\n")
        for cat, fp in files:
            after = fp.read_text()
            post = _score(fp, root)
            changed = after != before[cat]
            print("-" * 78)
            print(f"[{cat}]  {fp.name}   {'REPAIRED' if changed else 'unchanged'}"
                  f"   disk-quality {pre[cat]:.3f} → {post:.3f}")
            if changed:
                diff = difflib.unified_diff(
                    before[cat].splitlines(), after.splitlines(),
                    lineterm="", n=1, fromfile="raw", tofile="repaired")
                for ln in diff:
                    if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---")):
                        print("   " + ln)
        print("-" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
