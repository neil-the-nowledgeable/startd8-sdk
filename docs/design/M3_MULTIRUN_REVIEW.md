# M3 Multi-Run (3-provider) — Pre-Execution Review

**Date:** 2026-06-02
**Reviewed:** `strtd8/docs/M3_RUN_GUIDE.md` + `.cap-dev-pipe/python/` profile, against the
`compare-models-e2e` harness.
**Goal:** run the M3 LLM codegen batch 3× serially, alphabetically **Anthropic → Google → OpenAI**,
landmark models, as a multi-run "build the app" comparison. **Not executing yet** — this is the
landmine sweep + config validation.

## Config / shape — VALID (dry-run clean)
- One batch, 3 models in alphabetical order (harness preserves `--model` order ⇒ serial A→G→O):
  `-m anthropic:claude-opus-4-8 -m gemini:gemini-2.5-pro -m openai:gpt-5.5`.
- `--source-root` = `strtd8` (currently on `rebuild/python-spine` @ `5035dbc`, clean — the green spine ✅).
- `--plan .cap-dev-pipe/python/python-plan.md` `--requirements .../python-requirements.md`.
- `--batch-root` **OUTSIDE** source (e.g. `~/Documents/dev/m3-comparison/run-<ts>`) so the per-model
  copy preserves `.cap-dev-pipe/` (python profile + `upstream-anchors.txt`) — confirmed in dry-run.
- question-answers auto-resolves to `strtd8/.cap-dev-pipe/design/question-answers.yaml` ✅.

---

## LANDMINES (resolve or consciously accept before a live run)

### L1 — Harness drives a *different* entry than M3 was designed for; the anchor/Mode-B path is UNVALIDATED
- M3 is written for **`startd8-cap-dlv-pipe.sh --lang python`** → `run.sh` → `run-atomic.sh` →
  (cap-delivery → plan-ingestion → **`run-prime-contractor.sh --fresh`**). That `--fresh` is the
  **anchor-aware** clean (REQ-CDP-INT-008): it will *not* wipe the 59 owned spine files.
- Our harness instead calls cap-delivery + plan-ingestion + **`run_prime_workflow.py --force-regenerate`**
  directly. `--force-regenerate` removes files in the seed's `forward_manifest.file_specs`.
- **Mitigant found:** the 59-file anchor floor is **embedded in `python-plan.md`**
  (`<!-- cap-dev-pipe: upstream-anchors -->`, line 55) and "plan-ingestion emits these as the seed's"
  anchors (line 50). Since the harness passes that plan, the inheritance *should* ride through.
- **But unverified:** (a) neither `run_prime_workflow.py` nor `plan_ingestion_workflow.py` reference
  `upstream_anchor` by name — the parse path is unconfirmed; (b) the harness was validated only on a
  *from-scratch* feature (run-013), never on an **anchored / Mode-B-inheritance** run; (c) if the seed's
  `forward_manifest.file_specs` were to include any spine file, `--force-regenerate` would **delete it**
  in the sandbox copy.
- **Risk:** the model regenerates/edits the owned spine instead of inheriting it → invalid M3 build,
  determinism boundary violated, comparison meaningless. (Spine is git-tracked, so the *source* is
  safe; only each disposable workdir copy is at risk.)
- **Gate before live (cheap):** run **cap-delivery + plan-ingestion only** for ONE model into a temp
  batch, then inspect the produced seed: confirm the 59 spine files are listed as **inherited upstream
  anchors** and are **absent from the to-generate / `forward_manifest.file_specs`** set. If yes → the
  harness path is valid for M3. If no → switch prime to `run-prime-contractor.sh --fresh` (anchor-aware)
  or use the native `--lang python` chain with model-threading.

### L2 — Build gate needs the app's deps inside each sandbox (else it loud-degrades to non-pass)
- M3's quality check is `compileall + mypy + pytest` and the python_toolchain gate
  (`STARTD8_PY_TYPECHECK`). These need `fastapi sqlmodel jinja2 uvicorn anthropic mypy pytest httpx`
  **available in the per-model workdir's environment**. The sandbox copy **excludes `.venv`**.
- **Risk:** the gate reports non-pass because tools/deps are absent — looks like a code-quality failure
  but is a missing-deps artifact, polluting the comparison.
- **Fix:** provision a venv per sandbox (or a shared one) with those deps before the gate runs, or
  treat the gate as N/A and compare on other signals — but then we lose the headline M3 quality metric.

### L3 — RESOLVED ✅ (wired): determinism-boundary signal now auto-captured
- M3 success = "wrote **only** `app/ai/` + `app/server.py` + `tests/`, **never edited an owned spine
  file**" — measured by `startd8 generate backend --check` → `in_sync, all 59`.
- **Done:** `live_stage_runner` now runs `startd8 generate backend --check` per model after prime
  (exit 0=in_sync / 1=drift / 2=error), recording `spine_in_sync` + status into the metrics; the
  analysis surfaces a **`spine_in_sync`** column (`yes` / `NO ⚠` / `—`). A model that edited an owned
  spine file shows `NO ⚠` → that build is flagged not-M3-valid. No-op for non-prisma targets.
- Combined with `--force-regenerate` now OFF (no spine wipe), this **reduces L1 to a self-checking
  post-condition** — a pre-flight seed inspection is no longer required for safety; a boundary
  violation simply shows up as `spine_in_sync: NO ⚠` in the central report.

---

## WRINKLES (smaller, worth addressing)

- **W1 — Runtime AI provider is fixed to `anthropic`** (M3 §4: AI dep in `requirements-app.txt`; the
  app's `/ai/extract` calls Anthropic at runtime). The comparison varies **who writes the M3 code**,
  not the runtime provider. So all three variants generate code that imports `anthropic`. That's fine —
  but frame results as *codegen quality*, not *runtime-provider* comparison. Any boot-smoke needs
  `ANTHROPIC_API_KEY` regardless of the codegen model; don't boot-smoke all three — smoke the winner.
- **W2 — "3 times serial alphabetically"** = one batch, 3 models in A/G/O order (not 3 separate
  batches, not repeats). Confirmed this is what the config does.
- **W3 — Operator gates:** the native `--lang`/`run-atomic` chain has start/seed-quality/pause prompts
  (REQ-CDP-INT-010) needing `CDP_NON_INTERACTIVE`. Our direct-harness path **avoids** run-atomic, so it
  sidesteps these — but that avoidance is the very thing causing L1. (Trade-off to weigh.)
- **W4 — Cost/time:** M3 is tiny (3 features + anchors as context). 3 landmark runs ≈ cheap and ~30–60
  min total; `$15`/model cap is ample.
- **W5 — Seed-hash integrity (FR-15)** will compare each model's M3 seed; expect them to differ (good).
- **W6 — Single-run, indicative.** One run per model — directional, not statistical (NR-3 caveat holds).

---

## Recommended path
1. **Pre-flight L1 gate** (cheap, ~one ingestion): cap-delivery + plan-ingestion for one model →
   inspect the seed proves the spine is inherited-not-generated. **Do this before any prime run.**
2. **Decide L2:** provision deps per sandbox (keeps the gate meaningful) vs accept gate-N/A.
3. **Implement L3:** add the `spine_in_sync` (`generate backend --check`) capture — small, high value.
4. Then run the configured 3-model A/G/O batch and auto-aggregate (FR-24).

The harness is structurally ready and the config is valid; **L1 (anchor inheritance) is the gating
unknown** — validate it before trusting any M3 comparison output.
