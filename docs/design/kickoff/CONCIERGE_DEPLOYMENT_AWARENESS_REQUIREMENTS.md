# Concierge Deployment-Awareness (items 4–6) — Requirements

**Version:** 0.4 (Post pressure-test against code — anchors corrected)
**Date:** 2026-07-02
**Status:** Ready for implementation
**Owner:** StartD8 SDK / concierge + wireframe + mcp
**Extends:** `CONCIERGE_MCP_REQUIREMENTS.md` (v0.3); builds on `cloud-native-deploy`,
`deploy-environments`, `deployment-mode`.

---

## 0.2 Pressure-Test Against Current Code (v0.4)

> v0.3 was frozen 2026-06-21; the codebase moved ~250 commits since. A phantom-reference audit of
> every code symbol this spec names (3 parallel read-only audits @ origin/main `177fb61f`) found the
> effort is **still fully unbuilt and valid** (deployment-awareness in concierge is net-new — not
> moot), but that **two anchors were factually wrong and one requirement carried an internal
> contradiction the CRP round did not catch.** All corrections are folded below; no scope added.

| v0.3 claim | Code reality (audited) | Correction |
|---|---|---|
| `deploy_coherence_verdict` is the single source of `unbound_bindings` (FR-CDA-1/2) | `deploy_coherence_verdict(findings, *, mode) -> (verdict, exit_code)` — takes findings as **input**, returns a 2-tuple, has **no `unbound_bindings`**. Only the subprocess `scripts/check_deploy_coherence.py:evaluate()` **payload** carries it. | **Single source = the subprocess `--json` payload** (FR-CDA-1/5 rewritten). Makes FR-CDA-5's subprocess load-bearing for FR-CDA-1, not merely preferred. |
| Tri-state readiness keys off `unbound_bindings is None` = "declared-not-generated" | `None` = generic **"unknown"** (contract absent **OR** unparseable **OR** malformed bindings). Cannot alone separate "declared-not-generated" from "generated-but-broken-contract". | **FR-CDA-1** readiness now derives from `(deployment declared) × (deploy/ tree present) × (contract parseable)`; malformed contract → distinct `unknown` advisory, never silent `generated`. |
| `_VALID_DEPLOY_KEYS` gates deploy keys (FR-CDA-4) | Phantom name. Real constant is **`_DEPLOY_KEYS`** (`manifest.py:24`). `_VALID_DEPLOYMENT_MODES` correct. | FR-CDA-4 symbol corrected. |
| "3 pre-existing broken **golden** tests" (FR-CDA-2) | No golden files. 3 **assertion** tests; **1 fails, 2 pass** (`test_deployment_section_deployed_posture`: asserts `PLANNED`, deployed now → coherence ERROR → `INVALID`). | FR-CDA-2 scope corrected to the 1 failing assertion test. |
| assess "surfaces the wireframe deployment section (delegated)" (plan M2) | `_assess_cascade` delegates to `build_wireframe_plan` but extracts only `{status, readiness, blockers}` — it **discards** `_deployment_section`. | FR-CDA-1 gains an explicit "extract the deployment section from the plan" clause; plan M2 updated. |
| FR-CDA-6 safe because writes are "CLI-only via the chokepoint" | `apply_write_plan` now has **non-CLI callers** (`kickoff_experience/web.py`, seam, proposals). MCP path still only **previews** (never writes) — the real guarantee holds. | FR-CDA-6 rationale re-grounded on "the MCP `handle_concierge_tool` instantiate path returns a plan, never applies," not "CLI is the only writer." |
| M1 `render_deploy_tree` near coherence | Lives in `deploy_renderer.py:538`; `render_deploy_overlays:538/503` **already exist** — reusable. | Anchor corrected; M1 reuses existing renderers. |

**Verified clean (no change):** `build_assess` (core.py:158), `_assess_cascade`→`build_wireframe_plan`
(core.py:222), `READ_ACTIONS=("survey","assess")`, `handle_concierge_tool` (core.py:255),
`VALID_POSTURES=("prototype","production")`, `parse_app_manifest` strict/no-LLM (manifest.py:142),
`deploy_environments` sorted-at-parse (manifest.py:128), the script's `--json` + exit-codes 0/1/2/3 +
fail-closed→3, the MCP wrapper path (`mcp/startd8-mcp-builder/startd8_mcp.py`, tool `startd8_concierge`
@ 3151), both kickoff templates (`src/startd8/concierge_templates/`) + confirmed absence of deploy content.

### Reference Audit (symbols this spec depends on)

| Symbol | Verdict | Location |
|---|---|---|
| `deploy_coherence_verdict` return shape carries `unbound_bindings` | **PHANTOM** — returns `(verdict, exit_code)` | `scaffold_codegen/coherence.py:161` |
| `_VALID_DEPLOY_KEYS` | **PHANTOM name** → `_DEPLOY_KEYS` | `scaffold_codegen/manifest.py:24` |
| `unbound_bindings is None` = "declared-not-generated" | **DRIFTED** — means generic "unknown" | `scripts/check_deploy_coherence.py:45` |
| "3 broken golden tests" | **DRIFTED** — 1 failing assertion test, no goldens | `tests/unit/wireframe/test_deployment_section.py` |
| `_assess_cascade` surfaces `_deployment_section` | **GAP** — discards it (extracts summary only) | `concierge/core.py:222` |
| safe-writer "CLI-only" | **DRIFTED** — non-CLI callers exist; MCP-preview guarantee still holds | `concierge/safe_write.py` / `kickoff_experience/*` |
| `render_deploy_tree` / overlays | **EXISTS** (reuse) | `scaffold_codegen/deploy_renderer.py:538/503` |
| `evaluate` / `_count_unbound_bindings` / `--json` / exits 0-3 / fail-closed | **EXISTS** as specified | `scripts/check_deploy_coherence.py` |

---

## 0. Planning Insights (Self-Reflective Update)

> Planning against `concierge/core.py`, `writes.py`, and `wireframe/plan.py` (see
> `CONCIERGE_DEPLOYMENT_AWARENESS_PLAN.md` §1) showed **the substrate is further along than v0.1
> assumed** — a rich wireframe deployment section already exists and `assess` already delegates to it.
> ~40% of the work narrows to extensions + a default-seed + one MCP tool.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Wireframe deployment surfacing is new (FR-CDA-2) | `_deployment_section` already surfaces mode/persistence/bind/schema-init/secrets/observability/identity + coherence findings. | FR-CDA-2 → **extension only**: add environments + `deploy/` tree + per-env unbound bindings. |
| `assess` needs a new deployment view (FR-CDA-1) | `_assess_cascade` already delegates to `build_wireframe_plan` (FR-C10: never recompute). | FR-CDA-1 → **inherited**: surface the enriched section's data; don't recompute. |
| Posture may set mode (OQ-2) | `writes.py` posture drives `provenance_default` (convention authorship), **not** `deployment.mode`. | FR-CDA-3 → **seed a default** (prototype→installed, production→deployed), keep fields independent. |
| One MCP server to extend (OQ-4) | concierge FastMCP wrapper at `mcp/startd8-mcp-builder/startd8_mcp.py` → `handle_concierge_tool`; SDK already ships `check_deploy_coherence.py`. | FR-CDA-5 → thin read-only tool delegating to the existing verdict. |

**Resolved open questions:**
- **OQ-1 → assess delegates** to the wireframe cascade already (FR-C10) — enrich the section, assess inherits.
- **OQ-2 → posture currently maps to conventions only**, not mode.
- **OQ-3 → extension** of the existing `_deployment_section` (+ fix its 3 pre-existing-broken tests).
- **OQ-4 → `mcp/startd8-mcp-builder/startd8_mcp.py`** (FastMCP), delegating to `concierge` core / the SDK verdict.
- **OQ-5 → DEFAULT, not force** (mirrors deployment-mode OQ-5): explicit `deployment.mode` always wins.

---

## 1. Problem Statement

This session added a deployment-configuration surface (mode, the `deploy:` block, environments,
coherence gates, the `deploy/` tree). The **Concierge** — the onboarding front door (`startd8
concierge` + the `startd8_concierge` MCP tool) — is deployment-blind: its `assess` reports
kickoff-input provenance + the `$0`-cascade readiness but says nothing about whether/how the project
deploys; its `instantiate-kickoff --posture prototype|production` knob is unrelated to
`deployment.mode`; the kickoff templates don't explain the deployment-posture inputs; and there is no
agent-callable "is this deployable?" gate. An operator onboarding a project can't see or declare its
deployment posture through the Concierge.

### Gap table

| Concern | Today | Gap |
|---------|-------|-----|
| `assess` deployment view | reports kickoff inputs + cascade only | no deployment posture/readiness |
| Wireframe deployment section | surfaces mode + per-dim posture + coherence | no environments, no `deploy/` tree, no per-env unbound bindings |
| `--posture prototype\|production` | drives convention provenance only | unrelated to `deployment.mode` / `deploy:` / environments |
| Kickoff templates | no deployment inputs | commissioner can't declare mode/deploy/environments |
| Agent deployability gate | none | no `check_deploy_coherence` MCP tool |

---

## 2. Requirements

- **FR-CDA-1 (assess surfaces deployment readiness — hardened v0.3, anchors corrected v0.4).**
  `concierge assess` SHALL include a `deployment` block: declared mode, `deploy:` posture (target
  cloud, secrets backend, trust_gateway), declared environments, a **four-state readiness** per
  env/overall, the unbound operator-binding count, and the deploy-coherence verdict.
  **Readiness derivation (corrected v0.4 — the `None` sentinel is broader than v0.3 assumed):**
  `unbound_bindings is None` means generic *unknown* (contract absent **OR** unparseable), so readiness
  SHALL be derived from three signals, not the sentinel alone:
    - `not-declared` — no `deployment`/`deploy` block in app.yaml.
    - `declared-not-generated` — declared, but no `deploy/` tree on disk.
    - `generated` — declared, `deploy/` tree present, `deploy/infra-contract.yaml` parseable (count known).
    - `unknown` — declared and `deploy/` present but the contract is **absent-yet-tree-exists or
      unparseable/malformed** (advisory; MUST NOT be silently reported as `generated`).
  (`stale` from FR-CDA-8 is orthogonal and layered on top of `generated`.)
  **Single source (R1-F2, corrected v0.4):** the unbound count + verdict SHALL be the values the
  **subprocess `check_deploy_coherence.py --json` payload** returns (`evaluate()` → `unbound_bindings`
  + `verdict`) — NOT the in-process `deploy_coherence_verdict`, which returns only `(verdict,
  exit_code)` and carries no binding count. assess/wireframe surface the payload, never re-derive
  (FR-C10). Because `_assess_cascade` currently extracts only `{status, readiness, blockers}` from the
  wireframe plan and **discards `_deployment_section`**, `build_assess` SHALL explicitly extract the
  deployment section (and the coherence payload) into the `deployment` block. assess/the tool SHALL
  surface only names/counts/status, **never secret values** from the infra-contract (R1-S9).
- **FR-CDA-2 (wireframe deployment section extended — narrowed v0.2, anchors corrected v0.4).** The
  EXISTING `_deployment_section` (`wireframe/plan.py:987` — already surfaces mode/persistence/bind/
  schema-init/`secrets-default`/observability/identity + `evaluate_coherence` findings) SHALL be
  extended with: declared environments, the emitted `deploy/` artifact set (reusing the EXISTING
  `render_deploy_tree`/`render_deploy_overlays` in `scaffold_codegen/deploy_renderer.py:538/503` —
  presence check only, no re-render), and per-env unbound bindings — **surfacing the subprocess
  payload's value, not an independent re-read** (R1-F2/S1, corrected v0.4 per FR-CDA-1). New per-env
  items SHALL be emitted in the manifest's already-sorted `deploy_environments` order so the section
  stays byte-stable/idempotent (R1-S7). Its **one currently-failing assertion test**
  (`test_deployment_section_deployed_posture` — asserts `Status.PLANNED` but a deployed manifest now
  yields a coherence ERROR → `Status.INVALID`; the other two pass) SHALL be fixed in passing. (There
  are **no golden files** — the v0.3 "3 broken golden tests" was inaccurate.)
- **FR-CDA-3 (posture → deployment DEFAULT, not force — clarified v0.2).** Posture currently drives
  *convention provenance* only (`writes.py`). `instantiate-kickoff --posture prototype|production`
  SHALL additionally **seed a default** `deployment.mode` (prototype→installed, production→deployed) +
  minimal `deploy:` block, with an explicit 3-step policy (R1-F5/S5): (1) read declared
  `deployment.mode`; (2) if unset, seed from posture; (3) if set and it disagrees with the posture
  mapping, **keep the declared value and emit an ADVISORY, never an error**. A **production *desktop/CLI*
  tool legitimately running `installed`** is a named non-conflict, not a warning. Mode/deploy stay
  independent declared fields (mirrors deployment-mode OQ-5). Any seeded `deploy:` keys SHALL be drawn
  only from `_DEPLOY_KEYS` (see FR-CDA-4) so the projected manifest round-trips `parse_app_manifest`.
- **FR-CDA-4 (kickoff templates deployment inputs — gated v0.3).** The concierge kickoff templates
  SHALL explain the deployment-posture inputs (mode, `deploy:` block, environments, secrets backend,
  trust_gateway) in commissioner-friendly terms, using ONLY keys the strict `parse_app_manifest`
  accepts (**`_DEPLOY_KEYS`** — corrected v0.4, the v0.3 `_VALID_DEPLOY_KEYS` was a phantom name — and
  `_VALID_DEPLOYMENT_MODES`). A grammar-coherence gate SHALL round-trip every taught deployment key
  through `parse_app_manifest` with zero strict-key errors (R1-F7/S6) — a template teaching a rejected
  key produces an unparseable manifest → fail-closed `hard`.
- **FR-CDA-5 (check_deploy_coherence MCP tool — subprocess, normative v0.3).** Add an agent-callable,
  read-only `check_deploy_coherence` MCP tool that invokes **`scripts/check_deploy_coherence.py
  --json` via subprocess** (NOT in-process), mapping returncode (0/1/2/3) → verdict + surfacing the
  payload (R1-F4/S2/OQ-7). This inherits the script's fail-closed exits (malformed app.yaml → `hard`)
  and matches cap-dev-pipe's returncode+JSON Keiyaku; no reimplementation. A missing script / unstartable
  subprocess / import error SHALL degrade to a structured `hard` verdict with a reason — never a tool
  crash, never a silent pass (R1-S8). The interpreter/venv + cwd SHALL be specified. **This subprocess
  payload is the SINGLE source of `unbound_bindings` for FR-CDA-1/FR-CDA-2 (corrected v0.4):** the
  in-process `deploy_coherence_verdict` returns only `(verdict, exit_code)` and cannot supply the
  count, so the `--json` payload is load-bearing, not merely the preferred coupling.
- **FR-CDA-6 (assist-not-operate preserved — tightened v0.3, rationale re-grounded v0.4).** All
  additions SHALL be read-only over MCP (Concierge never runs the deploy, applies manifests, or
  records a gate). **The load-bearing guarantee (corrected v0.4) is that the MCP path only *previews*:
  `handle_concierge_tool` returns a plan for `instantiate-kickoff` and never calls the writer** — NOT
  the v0.3 rationale "the CLI is the only writer," which has drifted (`apply_write_plan` now has
  non-CLI callers in `kickoff_experience/`). The subprocess in FR-CDA-5 MAY be invoked ONLY in its
  read-only `--json` form — **no flag that writes, binds, resolves provenance, or renders `deploy/`
  may be passed or reachable** (R1-F1). Surfaced JSON carries only names/counts/status, never secret
  values (R1-S9).
- **FR-CDA-7 (deterministic, $0).** No LLM; all surfaces derive from the manifest + the deterministic
  cascade + the coherence verdict.
- **FR-CDA-8 (Staleness guard — added v0.3 R1-F6/S4).** `assess`/wireframe read the live `app.yaml`
  but the unbound-binding/verdict data comes from a generated `deploy/` snapshot. When the declared
  environments (live app.yaml) are NOT a subset of those represented in `deploy/infra-contract.yaml`
  (e.g. an env added since generation), readiness SHALL report **`stale`** (advisory), not silently
  `generated`. A cheap set-diff keeps it $0.

## 3. Non-Requirements

- NOT running/applying the deploy (operator + Kestra/Argo); NOT the cap-dev-pipe gate (orchestrator).
- NOT auto-forcing `deployment.mode` from posture — only seeding a default.
- NOT a new MCP server — extend the existing concierge FastMCP wrapper.
- NOT authoring real per-env values (operator/company content, bucket 4).

## 4. Open Questions

> OQ-1..OQ-5 resolved by the planning pass — see §0. **OQ-6/OQ-7 RESOLVED by CRP R1:**
> - **OQ-6 → YES, tri-state readiness** (not-declared / declared-not-generated / generated), reusing
>   `unbound_bindings is None` = no-contract. Folded into FR-CDA-1 (R1-F3/S3).
> - **OQ-7 → subprocess** (`--json`, returncode→verdict): inherits fail-closed exits + the cap-dev-pipe
>   Keiyaku; no in-process coupling. Folded into FR-CDA-5 (R1-F4/S2).
>
> No open questions remain.

---

*v0.2 — Post-planning self-reflective update. 5 OQs resolved, 2 new for CRP.*

*v0.3 — Post-CRP R1 triage (claude-opus-4-8-1m). 16 suggestions ACCEPTED (0 rejected). Themes:
single-source unbound bindings (FR-C10 no-recompute), subprocess+fail-closed MCP tool (OQ-7),
tri-state readiness (OQ-6), staleness guard (new FR-CDA-8), posture conflict policy + production-installed
exception, grammar-coherence gate, argv-safety + secret-value redaction. Dispositions in Appendix A.*

*v0.4 — Post pressure-test against code (3 parallel phantom-reference audits @ origin/main 177fb61f).
Effort confirmed still-unbuilt/valid. 2 phantom anchors corrected (`_VALID_DEPLOY_KEYS`→`_DEPLOY_KEYS`;
`deploy_coherence_verdict` carries NO `unbound_bindings` — single source is the subprocess `--json`
payload), 1 internal contradiction resolved (FR-CDA-1↔FR-CDA-5 unbound-binding source), 1 under-spec
fixed (readiness is 4-state derived from declared×tree×parseable, not the broad `None` sentinel), 3
descriptions corrected (1 failing assertion test not 3 goldens; `_assess_cascade` discards the section;
FR-CDA-6 rationale re-grounded on MCP-preview). See §0.2 + Reference Audit. No scope added.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

> **Triage (v0.3, 2026-06-21):** all 16 R1 suggestions (7 F + 9 S) ACCEPTED, 0 rejected. Plan-side
> S-items map to the same FRs as their F-pairs; the plan's §2A carries the milestone deltas.

### Appendix A: Applied Suggestions

| ID | Suggestion | Disposition (where merged) | Date |
|----|------------|----------------------------|------|
| R1-F1 | No mutating subprocess flag (invocation-contract read-only) | → FR-CDA-6 | 2026-06-21 |
| R1-F2 / R1-S1 | Single source for unbound bindings (verdict value, no re-read) | → FR-CDA-1/FR-CDA-2 | 2026-06-21 |
| R1-F3 / R1-S3 | Tri-state readiness (OQ-6) | → FR-CDA-1; OQ-6 resolved | 2026-06-21 |
| R1-F4 / R1-S2 | Subprocess + fail-closed, normative (OQ-7) | → FR-CDA-5; OQ-7 resolved | 2026-06-21 |
| R1-F5 / R1-S5 | Posture seed order + advisory conflict + production-installed | → FR-CDA-3 | 2026-06-21 |
| R1-F6 / R1-S4 | Staleness guard | → FR-CDA-8 (new) | 2026-06-21 |
| R1-F7 / R1-S6 | Template grammar-coherence gate | → FR-CDA-4 | 2026-06-21 |
| R1-S7 | Sorted/idempotent per-env wireframe items | → FR-CDA-2 | 2026-06-21 |
| R1-S8 | Unstartable subprocess → structured hard (not crash/silent pass) | → FR-CDA-5 | 2026-06-21 |
| R1-S9 | Never echo secret values (names/counts/status only) | → FR-CDA-1/FR-CDA-6 | 2026-06-21 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All R1 suggestions accepted | 2026-06-21 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-21

- **Reviewer**: claude-opus-4-8 (1M context)
- **Date**: 2026-06-21 20:05:00 UTC
- **Scope**: Requirements review weighted to the CRP focus file — assist-not-operate boundary (FR-CDA-6), FR-C10 no-recompute, posture→mode default-not-force (FR-CDA-3), MCP subprocess/fail-closed (OQ-7), readiness-vs-presence (OQ-6), staleness, template/grammar coherence. Code grounded against `concierge/core.py` (`build_assess`/`_assess_cascade`/`READ_ACTIONS`), `concierge/writes.py` (`VALID_POSTURES`/`build_instantiate_plan`), `wireframe/plan.py:_deployment_section`, `scaffold_codegen/coherence.py:deploy_coherence_verdict`, `scaffold_codegen/manifest.py` (parsed `deploy.*`/environments), and `scripts/check_deploy_coherence.py:evaluate`.

##### Focus-file asks (answered before standard F-suggestions)

**Ask 1 — assist-not-operate boundary (FR-CDA-6): does deployment-readiness or check_deploy_coherence cross into "operate"?**
- **Summary answer:** No, provided the MCP tool stays read-only and FR-CDA-1's "per-env unbound binding count" reads, never writes, the infra-contract.
- **Rationale:** `READ_ACTIONS=("survey","assess")` and all four data sources (parsed manifest, wireframe section, `_count_unbound_bindings`, `deploy_coherence_verdict`) are pure reads; `scripts/check_deploy_coherence.py:evaluate` is "pure except for reading the project files." FR-CDA-6 is satisfied by construction. The one latent risk is FR-CDA-5's subprocess choice: a script that *resolved provenance* or *touched* `deploy/` would breach the boundary — the requirement must forbid the tool passing any flag that mutates.
- **Assumptions / conditions:** The MCP tool invokes the coherence check in a read/`--json` posture only; no `--apply`/`--write`/`--bind` flags exist or are reachable.
- **Suggested improvements:** Add to FR-CDA-6 an explicit "no subprocess invoked by the Concierge may take a mutating flag; the only permitted invocation is the read-only `--json` verdict." (see R1-F1).

**Ask 2 — FR-C10 no-recompute: does surfacing the verdict + per-env unbound bindings sneak a recompute?**
- **Summary answer:** Partial — as written, yes, it risks a *second, divergent* computation.
- **Rationale:** `scripts/check_deploy_coherence.py:evaluate` already computes `{verdict, findings, unbound_bindings}` from app.yaml + `deploy/infra-contract.yaml`. FR-CDA-2 *also* asks `_deployment_section` to compute per-env unbound bindings, and FR-CDA-1 asks `assess` to surface both the verdict and the unbound count. If the wireframe section re-reads the contract independently of the coherence verdict, two code paths derive "unbound bindings" — that is a recompute in spirit (FR-C10) and a divergence bug (they can disagree). FR-C10 says assess must not recompute *provisioning state*; unbound-binding counting IS provisioning state.
- **Assumptions / conditions:** Both `_count_unbound_bindings` (script) and the proposed `_deployment_section` reader parse the same `deploy/infra-contract.yaml`.
- **Suggested improvements:** Require a single source of truth for unbound bindings — assess/wireframe surface the value the coherence verdict already returns, rather than re-deriving it (see R1-F2).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | FR-CDA-6 currently says "read-only over MCP" but does not constrain the subprocess in FR-CDA-5. Add: the Concierge MAY invoke `check_deploy_coherence.py` ONLY in its read-only `--json` verdict form; no flag that writes, binds, resolves provenance, or renders the `deploy/` tree may be passed or reachable. | "Read-only over MCP" is necessary but not sufficient once FR-CDA-5 spawns a subprocess — the boundary must be stated at the invocation contract, not just the action verb. | FR-CDA-6, add a second sentence | Code review of the tool's argv list; a unit test asserting the argv contains only the project path + `--json`. |
| R1-F2 | Data | high | FR-CDA-1 and FR-CDA-2 both surface "per-env unbound bindings." Specify a SINGLE source: the value returned by the coherence verdict (`unbound_bindings` in `evaluate()`), not an independent re-read in `_deployment_section`. State that the two surfaces must be byte-identical. | Prevents an FR-C10 recompute and a divergence bug where the wireframe section and the verdict disagree on the count. `scripts/check_deploy_coherence.py` already computes it. | FR-CDA-1/FR-CDA-2 + a new consistency clause | Test that `assess.deployment.unbound_bindings == check_deploy_coherence(... ).unbound_bindings` for the same project. |
| R1-F3 | Validation | high | OQ-6: make readiness-vs-presence a REQUIREMENT, not an open question. FR-CDA-1 should emit a tri-state per env/overall: `declared-not-generated` (deploy block present, no `deploy/` tree), `generated`, and `not-declared`. `_count_unbound_bindings` already returns `None` for "unknown (no contract)" — reuse that semantic. | Presence-only ("deploy/ tree present: true/false") misleads an operator who declared environments but never ran the cascade; the substrate already distinguishes None/unknown. | FR-CDA-1, replace "whether the deploy/ tree is present" with the tri-state | `assess` on (a) declared-only and (b) generated projects yields distinct readiness states; golden JSON. |
| R1-F4 | Risks | high | OQ-7: pick subprocess and write it into FR-CDA-5 as normative. Rationale belongs in the requirement: subprocess matches cap-dev-pipe's returncode+JSON Keiyaku, inherits the script's fail-closed exits (2=skip/3=hard on unparseable app.yaml), and avoids coupling the MCP tool to SDK internals. | OQ-7 left open blocks implementation and invites an in-process shortcut that loses the script's fail-closed guarantees (the script wraps every exception → verdict=hard). | FR-CDA-5, change "delegating to the existing SDK check" to "via subprocess to `scripts/check_deploy_coherence.py --json`, surfacing returncode+payload" | Tool returns `verdict=hard` (not an exception) on a malformed app.yaml; assert non-zero returncode is mapped, not swallowed. |
| R1-F5 | Architecture | medium | FR-CDA-3 maps prototype→installed and production→deployed, but a production *desktop tool* is legitimately `installed`. Weaken the coupling: state the mapping is a DEFAULT SEED only, and that posture and mode are independent declared fields whose mismatch is ADVISORY, never an error. Name the legitimate production-installed case explicitly. | The focus file flags this exact over-coupling. The mapping is a heuristic, not a truth; coding it as authoritative will mis-seed production CLI/desktop apps. | FR-CDA-3, add the production-installed exception sentence | Seed a `production` posture, then verify an explicit `deployment.mode: installed` survives and only an advisory (not an error) is emitted. |
| R1-F6 | Ops | medium | Add a staleness requirement: `assess`/wireframe read app.yaml (current) AND `deploy/infra-contract.yaml` (a snapshot of the last-generated `deploy/`). When the on-disk `deploy/` is stale vs current app.yaml (e.g., environments added since generation), readiness MUST be reported as `stale`/advisory, not silently as `generated`. | `_deployment_section` reads the live manifest while unbound-binding counts come from a generated artifact; a drift between them mis-reports readiness with no signal. FR-CDA-7's "deterministic, $0" makes a cheap mtime/declared-env-set comparison feasible. | New FR-CDA-8 (staleness) or a clause on FR-CDA-1 | Add an env to app.yaml without regenerating `deploy/`; assert readiness flips to `stale`, not `generated`. |
| R1-F7 | Interfaces | medium | FR-CDA-4 (templates) must state that any deployment inputs the templates teach (mode, `deploy:`, environments, secrets, trust_gateway) use ONLY keys the strict `parse_app_manifest` accepts (`_VALID_DEPLOY_KEYS`/`_VALID_DEPLOYMENT_MODES`). A template that teaches a key the strict parser rejects produces an unparseable manifest → fail-closed `hard`. | The manifest parser is strict ("never an LLM fallback"); template/grammar drift is a real failure path the focus file calls out. | FR-CDA-4, add a grammar-coherence clause | A test that parses every deployment key example in the rendered templates through `parse_app_manifest` with zero strict-key errors. |

##### Endorsements
- (none — R1 is the first round; no prior untriaged items.)
