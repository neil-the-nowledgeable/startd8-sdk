"""Run the REAL pipeline TODO-completion path against the A/B/C probe.

Uses production SDK functions (the same ones _run_todo_scan_and_inject calls):
  scan_directory -> classify -> derive_tasks_from_todos -> uncomment_block (Cat A)

Validates:
  A -> classified A, uncomment_block removes markers deterministically ($0)
  B -> classified B, derived as an 'implement' task (would route to LLM)
  C -> classified C, correctly NOT injected (filtered out of A/B task list)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from startd8.validators.todo_scanner import scan_directory, uncomment_block, _detect_language
from startd8.seeds.todo_derivation import derive_tasks_from_todos

PROBE = Path(__file__).parent / "probe_module.py"


def main() -> int:
    # Default: isolated temp copy. Optional arg: drop the probe into a real
    # run's generated/ dir and validate there (e.g. .../run-NNN/plan-ingestion/generated).
    tmp = None
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy(PROBE, target / "probe_module.py")
        print(f"[probe] dropped into live dir: {target}\n")
    else:
        tmp = Path(tempfile.mkdtemp(prefix="todo-probe-"))
        target = tmp / "generated"
        target.mkdir()
        shutil.copy(PROBE, target / "probe_module.py")

    print("=" * 68)
    print("STEP 1 — scan_directory (production scanner) on generated/ copy")
    print("=" * 68)
    inv = scan_directory(target)
    by_cat = {c: [e for e in inv.entries if e.category == c] for c in ("A", "B", "C")}
    for c in ("A", "B", "C"):
        for e in by_cat[c]:
            print(f"  {c}  {e.containing_function or '<module>'}():{e.line}  ::  {e.raw_text.strip()[:50]}")
    ok_detect = len(by_cat["A"]) == 1 and len(by_cat["B"]) == 1 and len(by_cat["C"]) == 1

    print("\n" + "=" * 68)
    print("STEP 2 — derive_tasks_from_todos (A+B only, C must be excluded)")
    print("=" * 68)
    # Mirror the pipeline: filter to actionable A/B before derivation.
    actionable = type(inv)()
    actionable.entries = by_cat["A"] + by_cat["B"]
    actionable.compute_summary()
    tasks = derive_tasks_from_todos(actionable, source_run_id="probe")
    for t in tasks:
        print(f"  task {t.get('task_id')}  type={t.get('task_type')!r}  ::  {t.get('title','')[:50]}")
    task_types = {t.get("task_type") for t in tasks}
    # C is excluded iff no derived task targets the parse_config function.
    # Check titles + target_files (not full str — implement tasks embed file
    # context that legitimately mentions neighbouring functions).
    c_excluded = (
        len(tasks) == 2
        and not any("parse_config" in (t.get("title") or "") for t in tasks)
        and not any(
            "parse_config" in str(t.get("target_files") or "") for t in tasks
        )
    )

    print("\n" + "=" * 68)
    print("STEP 3 — Category A uncomment shortcut (deterministic, $0)")
    print("=" * 68)
    content = (target / "probe_module.py").read_text()
    lang = _detect_language(str(target / "probe_module.py"))
    result, count = uncomment_block(content, language=lang)
    a_uncommented = count > 0 and "policy = RetryPolicy(max_attempts=5)" in result
    print(f"  uncomment_block: {count} block(s) restored; RetryPolicy line live = {a_uncommented}")

    print("\n" + "=" * 68)
    print("VERDICT")
    print("=" * 68)
    checks = {
        "A/B/C all detected (1 each)": ok_detect,
        "Category A derived as uncomment task": "uncomment" in task_types,
        "Category B derived as implement task": "implement" in task_types,
        "Category C NOT injected": c_excluded,
        "Category A uncomment is deterministic ($0)": a_uncommented,
    }
    for label, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")

    if tmp is not None:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
