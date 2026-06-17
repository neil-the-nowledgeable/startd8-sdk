# Semantic Detector Fidelity — Analysis & Requirements Completion

**Date:** 2026-06-16
**Status:** Analysis + detector requirements (implementation queued)
**Motivated by:** `SEMANTIC_REPAIR_DEMONSTRATION.md` — 2 of 4 semantic repair categories did not fire.
**Scope:** the DETECTOR (`forward_manifest_validator.py`), not the repair steps (those are sound).

---

## 1. The question

The OQ-2 demo proved `discarded_return` and `duplicate_main_guard` repair correctly, but
`method_resolution` and `import_resolution` **did not fire**. For each: are the **requirements
complete**, is the **implementation faithful**, or a combination?

## 2. Findings (root-caused, empirically verified)

### Finding A — `method_resolution`: requirements COMPLETE, implementation UNFAITHFUL

- **Requirement (REQ-SR-100 §19.2)** uses this exact input and is explicit:
  ```python
  def index(l): ...
  class UserBehavior(TaskSet):
      def on_start(self):
          self.index()       # BUG → index(self)
      tasks = {index: 1}     # CORRECT — not touched
  ```
  → `self.index()` **must be flagged** even though `index` appears in `tasks = {index: 1}`.
- **Implementation (`_validate_method_resolution`, lines 2581–2590, 2599)** collects functions named
  in `tasks = {...}` into `dispatch_funcs` and then **excludes** `self.<f>()` from flagging when
  `f in dispatch_funcs`. So the canonical example is suppressed — the opposite of the requirement.
- **Why it's wrong:** dict-registration (`tasks = {index: 1}`) means the *framework* calls `index(self)`;
  it does **not** bind `index` as an attribute of `self`. `self.index()` raises `AttributeError` at
  runtime regardless. Dict membership is a *separate, valid* usage; it does not legitimize the `self.`
  call. The exclusion conflates the two.
- **Verdict: implementation bug.** Requirements need no change beyond making this explicit (DET-MR-1).

### Finding B — `import_resolution`: COMBINATION (requirements incomplete + implementation lenient)

- **Requirement (REQ-SR-200)** targets repairing `from emailservice.email_server import X` in a **flat
  layout** (sibling `email_server.py`, no `emailservice/__init__.py`) → `from email_server import X`.
  It **assumes the detector emits an `import_resolution` issue** for this — but the **detection**
  requirement for "package-style import into a flat-layout directory is unresolvable-at-runtime" is
  **not specified** anywhere.
- **Implementation (`resolve_import` via `discover_sibling_modules`)** treats the bare directory name
  as a resolvable module: verified — `resolve_import('emailservice.email_server')` → `'local:emailservice'`
  (non-None ⇒ not flagged ⇒ the repair never sees it). It counts a directory name as importable
  **without checking for `__init__.py`**, so flat-layout package imports look resolvable.
- **Verdict: combo.** The detection requirement is missing (reqs-incomplete) AND the resolver is too
  lenient (impl treats any sibling dir name as a package). Both must change.

## 3. Detector requirements (completion)

**DET-MR-1 — Method-resolution detection is dispatch-independent.** `self.<f>()` where `<f>` is a
module-level function and not a real method/attribute of the class MUST be flagged
`method_resolution`, **regardless** of whether `<f>` appears in a `tasks`/dispatch dict. The
dispatch-dict reference is a distinct valid usage and MUST NOT suppress the `self.<f>()` *call* flag.
(Bare non-call references like `tasks = {index: 1}` remain untouched — only `self.<f>()` *calls*.)

**DET-IR-1 — Flat-layout package imports are unresolvable.** A dotted import `from <dir>.<mod> import X`
where `<dir>` is a sibling directory **without `__init__.py`** (flat layout) MUST NOT resolve via the
bare directory name. `resolve_import` MUST treat a directory as a package source only when it carries
`__init__.py`; otherwise the import is flagged `import_resolution` (so REQ-SR-200 repair can rewrite
it to the flat form). Package layouts (`__init__.py` present) remain resolvable (unchanged).

**DET-V-1 — False-positive gate (mandatory before activation).** Each detector change MUST be
validated against round3's 245 `ok` cells: count NEW `method_resolution` / `import_resolution` issues
introduced. Per the SV2 gate, false-positive rate MUST be < 5% before the change is kept; report the
new-issue count and spot-check a sample. (Detector changes that newly-flag correct code are worse than
under-detection.)

## 4. Implementation plan (queued — blocked on the live run process exiting)

> `forward_manifest_validator.py` is imported by the per-cell generation path. Editing it is **blocked
> while any `run_ob_benchmark` process is alive** (the hard "don't edit src during a live run" rule),
> even though the OpenAI run's `cells.json` is already written. Implement once the process exits.

1. **`_validate_method_resolution`** — drop `dispatch_funcs` from the suppression set for `self.<f>()`
   *calls* (lines ~2581–2590 build it; ~2599 uses it). Keep `class_methods` exclusion. (~3-line change.)
2. **`resolve_import` / `discover_sibling_modules`** — when resolving a dotted path whose first
   segment is a sibling directory, resolve as a package only if `<dir>/__init__.py` exists; else return
   None (unresolvable) so `_validate_import_resolution` emits the issue. (Localized change + a unit test.)
3. **Re-run `scripts/demo_semantic_repair.py`** — all 4 categories should now fire; `method_resolution`
   rewrites `self.index()` → `index(self)`, `import_resolution` rewrites the flat-layout import.
4. **Run DET-V-1 FP validation** on round3; keep only if FP < 5%.
5. Add unit tests for both detectors (the canonical REQ-SR-100/200 inputs).

## 5. Acceptance

- Demo: `issues_found`/`issues_repaired` rises from 3 to ≥5; all 4 categories show a transform.
- DET-V-1: new-issue count on round3 ok cells within the 5% FP gate, sampled and confirmed real.
- Unit tests green; no edit to existing src while a run is live.

*Analysis complete. method_resolution = impl bug (dispatch suppression); import_resolution = combo
(missing flat-layout detection requirement + over-lenient resolver). Requirements completed (DET-MR-1,
DET-IR-1, DET-V-1); implementation queued behind the live-run guard with a mandatory FP gate.*
