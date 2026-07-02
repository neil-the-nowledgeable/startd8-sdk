# Deterministic SDK Project-Init — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-07-02
**Status:** Draft
**Owner:** neil-the-nowledgeable

> **One-line.** A single, **deterministic ($0, no LLM)** flow — `startd8 project init` — that turns a
> directory into a fully set-up StartD8 project: detects greenfield/brownfield, establishes the
> `.startd8/` role postings, and makes the project **VIPP-inbox-*ready*** — plus a first-class
> non-interactive **inbox *producer seam*** (closing issue #76). The producer serializes
> **explicitly-supplied or greenfield-auto-derived** proposals; it never *invents* content, because
> proposals encode authored change-intent and project ground-truth only *adjudicates* it.

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). A codebase
> sweep against the real `project/`, `vipp/`, `concierge/`, `kickoff_experience/` seams produced **one
> load-bearing correction** (FR-5 was largely infeasible as written) plus several simplifications and 4
> new requirements — the loop working as intended. The central discovery: **project ground-truth is a
> *validator, not a generator*** — it cannot originate proposals, so "produce a first inbox from
> ground-truth" was the wrong frame.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| **FR-5:** init can deterministically produce a first inbox *from existing project ground-truth*. | **Largely infeasible.** `vipp/ground_truth.py` only `answer()`s VALIDATED/REFUTED/**OMIT** and "never fabricates a claim"; `vipp/evaluate.py:_build_questions` derives questions *from a proposal* — no proposal ⇒ the oracle is never consulted. Ground truth **adjudicates, never originates**. Of the 6 `PROPOSAL_KINDS`, **5 carry irreducibly authored content** (value/friction-prose/brief); only **`instantiate`** (bytes = packaged templates) is derivable, and only greenfield. | **FR-5 REWRITTEN** to a `$0` non-interactive *producer seam* over explicitly-supplied or greenfield-auto-derived proposals (the honest #76 fix); **never invents content**. |
| **FR-4/FR-5:** a project init "produces" an inbox. | **A healthy brownfield app has nothing to propose.** household-o11y (schema + all 4 kickoff inputs present, kickoff package instantiated, inbox already shredded) → no `instantiate` gap, no `capture` need. | **FR-4/5 reframed "inbox-produced" → "inbox-*ready*"** by default; production is gated on a real, declared gap (greenfield `instantiate`, or an explicit `--proposals` file). |
| **OQ-6:** unclear where the code lives; maybe a new `project/` module. | **`src/startd8/project/` already exists** (a *scaffolder* — `scaffold_project`, wired to `startd8 project new` under an existing `project_app`, `cli_project.py:12/18`). Unrelated to onboarding but the right home. | New `startd8 project init` slots under the **existing** `project_app`; a thin `project/init.py` *composes* `ensure_posting`/`build_instantiate_plan`/`serialize_buffer` — no new write primitive. Leave `project new` untouched. |
| **OQ-1:** maybe overload the existing `startd8 init`. | `cli.py:73-96 init()` = pure framework **storage** (`get_framework(storage_dir)`). Overloading it would confuse. | **OQ-1 resolved:** new `startd8 project init`; top-level `startd8 init` untouched. |
| **OQ-2:** establish concierge/fde postings too? | **There is NO concierge posting** — Concierge is stateless read-only (`concierge/core.py`, no `ensure_posting`, no `.startd8/concierge/`). `vipp`/`fde` postings are identical idempotent `ensure_posting(root, *, sdk_version)`. | **OQ-2 resolved:** VIPP posting by default; **FDE opt-in** (`--with-fde`); no concierge posting exists. |
| **FR-4:** "inbox mechanism = `.startd8/vipp/` existing." | The seam needs more: `.gitignore` (`*\n`) + a monotonic `inbox-seq` counter, currently created **only inside `serialize_buffer`** (`vipp_seam.py:199-217`). | **New FR-11** (parity refactor: extract `ensure_inbox_scaffold` so the two paths can't drift); FR-4 = posting + scaffold, **not** the inbox file. |
| — (unseen risks) | The inbox is the **trust boundary** the out-of-process VIPP reads; `serialize_buffer` refuses to clobber an undrained inbox; `instantiate` proposals must be built via `ProposedAction`+`serialize_buffer` (envelope parity is CI-guarded). | **New FR-12/13/14** (validate `--proposals` per-kind before serialize; surface no-clobber-of-undrained as exit 0; reuse `serialize_buffer`, never hand-roll the envelope). |

**Resolved open questions:** OQ-1 → `startd8 project init` (not overload `init`). OQ-2 → VIPP default,
FDE opt-in, no concierge posting. OQ-3 → the *only* deterministic ground-truth→proposal mapping is
greenfield `instantiate`; schema-drift/missing-inputs/survey-findings do NOT imply a proposal (they need
authored content). OQ-4 → **correct instinct — produce an inbox only on a real gap; healthy brownfield =
inbox-ready, no inbox file.** OQ-5 → greenfield init *offers* `instantiate` via the auto-proposal (opt-in
`--instantiate`), kept inside the VIPP negotiate→apply gate (assist, not operate). OQ-6 → `project/init.py`
orchestrator + `startd8 project init` in `cli_project.py`.

---

## 1. Problem Statement

Onboarding a directory as a StartD8 project is today **fragmented and partly manual**. There is no one
command that "makes this an SDK project." Worse, the VIPP loop (proven on household-o11y and
Summer2026-portal-rebuild) **cannot start without a manual inbox seed** — the only built-in producers
are the *paid* Concierge chat or a *TTY-gated* terminal command (issue #76).

### Gap table

| Concern | Current State | Gap |
|---------|--------------|-----|
| "Make this dir an SDK project" | `startd8 init` only creates a framework **storage** dir (`--dir`); it does not onboard | No unified project-init flow |
| Role postings (`.startd8/{vipp,fde,concierge}`) | Each created lazily/manually: `vipp init`, `fde init`, auto-on-first-use | No single step establishes the structure |
| Greenfield vs brownfield detection | Ad-hoc (`wireframe`, `concierge survey/assess` run separately) | Init doesn't detect/branch on project shape |
| VIPP opt-in | Manual `vipp init` (`vipp.context.ensure_posting`) | Not part of a project init |
| **VIPP inbox production** | Manual `serialize_buffer` seam; else paid chat / TTY concierge (issue #76) | **No `$0` non-interactive inbox producer** |
| Idempotency / no-surprise | `ensure_posting` is idempotent; `vipp_seam` is opt-in/byte-identical-when-absent | Init must preserve both invariants across the whole flow |

### What should exist

`startd8 project init [PROJECT_ROOT]` — deterministic, `$0`, that: (a) surveys the dir, (b) establishes
the `.startd8/` role postings, (c) opts the project into VIPP and stands up the inbox mechanism, (d)
optionally produces a **first inbox deterministically** from existing project ground-truth / kickoff
inputs, and (e) reports what it did. Re-runnable as a clean no-op.

---

## 2. Requirements

**FR-1 — Single deterministic entry point.** A **`startd8 project init [PROJECT_ROOT]`** command
(default cwd) under the **existing** `project_app` (`cli_project.py`), `$0`/no-LLM (bucket-1
applicational-completion), orchestrating the whole init. The top-level framework-storage `startd8 init`
is **left untouched** (D1/OQ-1). The command delegates to a thin `src/startd8/project/init.py`
orchestrator that only *composes* already-shipped, already-confined functions — no new write primitive.

**FR-2 — Greenfield/brownfield detection.** Init detects project shape deterministically: presence of
`prisma/schema.prisma` (or a contract), an `app/` package, existing kickoff inputs
(`docs/kickoff/inputs/*.yaml`), and any existing `.startd8/` postings. It branches behavior on this
(e.g. a brownfield app can seed an inbox from its schema; a greenfield dir cannot yet).

**FR-3 — Establish role postings.** Init creates the `.startd8/` posting structure via the **existing**
`ensure_posting` per role — at minimum **VIPP** (`vipp.context.ensure_posting`); optionally FDE and a
Concierge posting. It does not reinvent posting creation.

**FR-4 — Make the project VIPP-inbox-*ready*.** Init stands up the inbox *mechanism* (not the inbox
file): ensure `.startd8/vipp/`, the `.gitignore` (`*\n`), and an initialized monotonic `inbox-seq`
counter, so `vipp negotiate` gives a clean "no inbox yet" rather than a missing-dir error, and any
producer can serialize. **The default outcome is inbox-*ready*, not inbox-*produced*** — because a
healthy brownfield app has nothing to propose (D10). Writes ride `apply_write_plan` with `ACTION_NEW`
(no-clobber ⇒ re-run is a no-op). Does **not** write `proposals-inbox.json` (that's FR-5).

**FR-5 — `$0` non-interactive inbox *producer seam* (closes #76) — REFRAMED.** Init provides a
deterministic, non-interactive producer that serializes a proposal set via the existing
`vipp_seam.serialize_buffer` (no paid chat, no TTY). It **never invents content** — proposals encode
authored change-intent, and ground-truth only adjudicates (§0). Two supported sources, both `$0`:
- **`--proposals FILE`** — an explicitly-supplied, operator/agent-**authored** proposal set (small
  YAML/JSON); each entry validated per-kind before serialize (FR-12). This makes the #76 workaround
  first-class.
- **Greenfield `--instantiate`** — the *one* deterministic ground-truth→proposal mapping (D8): when the
  dir has no kickoff package, synthesize a single **`instantiate`** `ProposedAction` (`{posture}`; bytes
  = packaged templates, D13) and serialize it. The VIPP loop can apply it end-to-end (D14).
For a healthy `brownfield_ready` project, init produces **no inbox** and reports "inbox-ready; no
deterministic gap to propose against" (OQ-4). Production is always gated on a real, declared gap.

**FR-6 — Idempotent + byte-identical-when-absent (SOTTO).** Re-running init on an already-init'd project
is a clean no-op (no spurious rewrites). A project that never runs init is unchanged — init writes
nothing until invoked. Prove with a dict-equality/no-op test.

**FR-7 — Confined writes only.** Every write rides `concierge/safe_write.py:apply_write_plan` (symlink/
`..`/clobber/TOCTOU guards). Init never writes outside the confined project root.

**FR-8 — Posture alignment.** Init follows the established "assist, not operate" + provenance posture:
it sets up structure and *offers* a first inbox, but does not run the cascade, record a gate, or
auto-apply. Preview-by-default where it would write; report what it did/would do.

**FR-9 — Report + next-steps.** Init emits a deterministic summary (what postings/files it created,
whether an inbox was produced, brownfield/greenfield verdict) and the next command (`vipp negotiate`).
Posture-encoding exit codes (0 ok / 2 bad input / 3 write blocked).

**FR-10 — Idempotent re-init / `--check`.** A `--check` (read-only) mode reports whether the project is
init'd + in-sync, writing nothing (drift audit for the init structure). Exit **0=in-sync / 1=drift /
2=error**, mirroring `cli_generate.py:47` (D12).

**FR-11 — Inbox-scaffold parity refactor (NEW).** The `.gitignore` + `inbox-seq` bootstrap currently
lives *inside* `serialize_buffer` (`vipp_seam.py:199-217`). Extract a shared
`vipp_seam.ensure_inbox_scaffold(project_root)` used by BOTH `serialize_buffer` and FR-4, so the two
paths can't drift (P-E single-source-of-truth precedent in `writes.py`).

**FR-12 — Validate `--proposals` per-kind before serialize (NEW).** The inbox is the trust boundary the
out-of-process VIPP reads (`vipp_seam.py:8`). An authored `--proposals` file must have each entry's
`kind ∈ PROPOSAL_KINDS` and pass the **same per-kind validators the propose handler uses**
(`validate_posture`/`validate_friction`/`build_capture_plan`) *before* serialization; a bad entry fails
init with exit 2, never a half-written inbox.

**FR-13 — No-clobber-of-undrained is exit 0, not an error (NEW).** `serialize_buffer` refuses to
overwrite an undrained inbox (`vipp_seam.py:170`). When init's producer hits that, surface the `skipped`
result as **exit 0 with a "consume the existing inbox first (`vipp negotiate`/`apply`)" message** — not
a failure — so re-running init on a project mid-loop doesn't look broken.

**FR-14 — Build proposals via `ProposedAction` + `serialize_buffer`, never hand-roll (NEW).** The
greenfield `instantiate` proposal (and any producer output) must be built as
`ProposedAction("instantiate", {"posture": …}, id=…)` and serialized through `serialize_buffer` (with
its `_PROPOSAL_FIELDS` whitelist), so the `vipp.models.ProposalEnvelope.from_json` parity (CI-guarded,
`vipp_seam.py:15`) stays intact. Init never writes the envelope JSON directly.

---

## 3. Non-Requirements

- **NR-1.** Does not generate the app (that's the `generate` cascade) — init only sets up *project
  structure + the VIPP inbox mechanism*.
- **NR-2.** Does not run the Concierge agentic chat or any LLM — `$0`/deterministic only.
- **NR-3.** Does not author real content or proposals from nothing — a produced inbox derives only from
  *existing* ground-truth (schema/kickoff inputs), never invented.
- **NR-4.** Does not auto-apply proposals or run the cascade (assist, not operate).
- **NR-5.** Does not replace `vipp init`/`fde init` as standalone commands — init *composes* them.

---

## 4. Open Questions (residual — OQ-1..6 resolved in §0)

- **OQ-7.** `--proposals` file format — a small YAML mirroring `ProposedAction` (kind/params/id), or the
  `ProposalEnvelope` shape directly? Leaning a minimal `kind + params` list (init assigns ids + wraps).
- **OQ-8.** Should `startd8 vipp negotiate` be taught to treat a missing inbox as a clean "nothing to do"
  (exit 0) rather than exit 2, now that FR-4 makes "inbox-ready but no inbox file" the normal state?
  (A small `cli_vipp` nicety that pairs with FR-4 — in-scope or separate?)
- **OQ-9.** Does init default to `--with-fde` off (VIPP-only) forever, or auto-enable FDE for a
  brownfield app that has cap-dev-pipe run history (where the FDE explain path is useful)?

---

*v0.2 — Post-planning self-reflective update. FR-1/4/5 rewritten (FR-5 reframed from "derive proposals
from ground-truth" — infeasible — to a `$0` non-interactive producer *seam*; FR-4 "produced"→"ready");
4 requirements added (FR-11..14); OQ-1..6 resolved; OQ-7..9 surfaced. The load-bearing correction:
ground-truth adjudicates, it does not originate — a healthy brownfield project is inbox-**ready**, not
inbox-**produced**.*
