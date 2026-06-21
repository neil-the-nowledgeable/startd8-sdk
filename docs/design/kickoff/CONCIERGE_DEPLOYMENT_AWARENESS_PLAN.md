# Concierge Deployment-Awareness — Implementation Plan

**Version:** 1.0
**Tracks:** `CONCIERGE_DEPLOYMENT_AWARENESS_REQUIREMENTS.md` (v0.2)
**Date:** 2026-06-21

---

## 1. Planning Discoveries (fed back into requirements §0)

| Requirements assumed (v0.1) | Code reality | Impact |
|---|---|---|
| Wireframe deployment surfacing is new (FR-CDA-2) | `wireframe/plan.py:_deployment_section` already exists and is rich: mode/persistence/bind/schema-init/secrets-default/observability/identity + FR-CFG-5 coherence findings. | **FR-CDA-2 narrows to an EXTENSION** — add only environments + `deploy/` artifacts + per-env unbound bindings. (Its 3 tests are among the pre-existing broken goldens — fix in passing.) |
| `assess` needs a new deployment view (FR-CDA-1) | `concierge/core.py:_assess_cascade` delegates to `build_wireframe_plan` (FR-C10 — "never recomputes provisioning state"). | **FR-CDA-1 is mostly inherited**: enrich the wireframe section (FR-CDA-2) and have `assess` surface that section's `deployment` data — no recomputation, honoring FR-C10. |
| Posture might already set mode (OQ-2) | `writes.py`: `VALID_POSTURES=("prototype","production")` drives `provenance_default` (templated vs authored **conventions**) — **not** `deployment.mode` at all. | Posture and mode are currently orthogonal. **FR-CDA-3 = seed a default** (prototype→installed, production→deployed), keeping them independent (mirrors deployment-mode OQ-5: a default, not a subsumption). Resolves OQ-5. |
| One MCP server to extend (FR-CDA-5) | The concierge tool is a FastMCP wrapper at `mcp/startd8-mcp-builder/startd8_mcp.py`; the callable core is `concierge/handle_concierge_tool`. The SDK already ships `scripts/check_deploy_coherence.py` + `coherence.deploy_coherence_verdict`. | FR-CDA-5 = a thin read-only tool in that wrapper delegating to the existing verdict (no reimplementation, NR). |
| `assess` is read-only/safe | `READ_ACTIONS=("survey","assess")`; writes go through the safe-writer chokepoint (CLI-only). | FR-CDA-6 satisfied by construction — the new surfaces are reads. |

> ~40% narrowed: the wireframe section + assess delegation already exist; posture-vs-mode is a
> default-seed not a merge. The real new work is small: extend one section, seed posture defaults,
> add template prose, add one MCP tool.

## 2. Approach (milestones)

**M1 — Wireframe deployment section extension (FR-CDA-2).** In `_deployment_section`, append items for
declared environments (names), the `deploy/` artifact set (from `render_deploy_tree`/overlays
presence), and per-env unbound-binding counts (read from `deploy/infra-contract.yaml`). Update the 3
deployment-section golden tests.

**M2 — assess deployment block (FR-CDA-1).** `build_assess` surfaces the wireframe deployment
section's data under a `deployment` key (delegated, not recomputed — FR-C10). Add the coherence
verdict (via `deploy_coherence_verdict`).

**M3 — posture → deployment defaults (FR-CDA-3).** `writes.build_instantiate_plan`: posture seeds a
default `deployment.mode` + minimal `deploy:` block in the projected app.yaml (production→deployed +
environments scaffold + secrets backend + a `trust_gateway` prompt; prototype→installed). Independent
fields; an advisory notes the relationship.

**M4 — kickoff template deployment inputs (FR-CDA-4).** Extend `KICKOFF_INPUTS_EXPLAINED_TEMPLATE.md`
+ `KICKOFF_INTRO_TEMPLATE.md` with a plain-language deployment-posture section (mode, `deploy:`,
environments, secrets, trust_gateway), keyed to posture.

**M5 — check_deploy_coherence MCP tool (FR-CDA-5).** Add a read-only tool to the concierge FastMCP
wrapper delegating to `scripts/check_deploy_coherence.py` (subprocess) or `deploy_coherence_verdict`;
returns `{verdict, findings, unbound_bindings}`.

## 3. Validation

- M1: wireframe of a deployed+environments project surfaces env names + `deploy/` artifacts + per-env
  bindings; installed project unaffected; the 3 deployment-section tests pass.
- M2: `concierge assess --json` on a deployed project has a `deployment` block with the verdict.
- M3: `instantiate-kickoff --posture production` projects `deployment.mode: deployed` (+ deploy block);
  prototype → installed; both remain operator-overridable.
- M4: templates render the deployment section; golden check.
- M5: the MCP tool returns the verdict; HARD on a no-gateway deployed project.

## 4. Risks

| Risk | Mitigation |
|---|---|
| assess recomputes provisioning (violates FR-C10) | delegate to the wireframe section; never recompute |
| posture silently overrides an explicit mode | seed only when mode unset; explicit `deployment.mode` wins; advisory on conflict |
| MCP tool reimplements coherence (NR) | delegate to the existing SDK verdict; tool is a thin wrapper |
| Wireframe section golden churn | update the 3 existing tests; byte-stable additions |

## 5. Out of scope
- Running/applying the deploy; the cap-dev-pipe gate; real per-env values.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-21

- **Reviewer**: claude-opus-4-8 (1M context)
- **Date**: 2026-06-21 20:05:00 UTC
- **Scope**: Plan review weighted to the CRP focus file — FR-C10 no-recompute (single source for unbound bindings), assist-not-operate (FR-CDA-6) in M5's subprocess, posture-default sequencing/conflict (M3), readiness-vs-presence (M2/OQ-6), staleness (M1↔M2), template/grammar coherence (M4). Grounded against `concierge/core.py:build_assess`, `wireframe/plan.py:_deployment_section`, `scripts/check_deploy_coherence.py:evaluate` (`_count_unbound_bindings` returns None=unknown), `concierge/writes.py:build_instantiate_plan`, `scaffold_codegen/manifest.py` (`deploy_environments`/`has_environments`/strict `_VALID_DEPLOY_KEYS`).

##### Executive summary
- M1 and M5 both read `deploy/infra-contract.yaml` for unbound bindings → two code paths derive the same provisioning state (FR-C10 recompute + divergence bug). Pick one source.
- M5 leaves subprocess-vs-in-process unresolved (OQ-7); subprocess inherits the script's fail-closed exits and the cap-dev-pipe Keiyaku — recommend subprocess, normatively.
- OQ-6 readiness-vs-presence is implementable cheaply: `_count_unbound_bindings` already returns None for "no contract" — M2 should emit a tri-state, not a boolean.
- No staleness guard between M1 (reads live app.yaml) and the generated `deploy/` snapshot M1/M5 read for bindings — drift mis-reports `generated`.
- M3's posture seed needs an explicit ordering + conflict rule (seed only when mode unset; advisory, never error) and must guard the legitimate production-installed case.
- M4 template prose can teach keys the strict parser rejects → unparseable manifest = fail-closed; needs a parse-the-examples gate.
- M1 risk "byte-stable additions" is asserted but `_deployment_section` emits per-env items; ordering must be sorted (the manifest already sorts `deploy_environments`) to stay deterministic.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Data | high | M1 ("per-env unbound-binding counts ... read from `deploy/infra-contract.yaml`") and M5 (delegates to the script, which computes `unbound_bindings`) both parse the same contract. Make the coherence verdict the SINGLE source; M1/M2 surface the verdict's `unbound_bindings`, not an independent re-read. | Two readers of provisioning state violate FR-C10 in spirit and can diverge. `scripts/check_deploy_coherence.py:_count_unbound_bindings` already exists. | M1 + M2, add "single source: the verdict's `unbound_bindings`" | Assert `assess.deployment.unbound_bindings` equals the script's `unbound_bindings` on the same project. |
| R1-S2 | Risks | high | M5: resolve OQ-7 in favor of subprocess and state it. Invoke `check_deploy_coherence.py --json`, map returncode (0/1/2/3) → verdict; do NOT call `deploy_coherence_verdict` in-process. | Subprocess inherits the script's fail-closed guarantees (every exception → `verdict=hard`, malformed app.yaml → exit 3) and matches cap-dev-pipe's returncode+JSON consumer contract; in-process re-creates that error wrapping by hand. | M5, replace "(subprocess) or `deploy_coherence_verdict`" with the subprocess contract | Malformed app.yaml → tool returns `verdict=hard` with non-zero returncode surfaced, not an unhandled exception. |
| R1-S3 | Validation | high | M2: implement OQ-6 readiness as a tri-state (`not-declared` / `declared-not-generated` / `generated`) rather than the boolean "whether the `deploy/` tree is present" in §3. Use `unbound_bindings is None` (no contract) as the "declared-not-generated" signal. | Presence-only misleads an operator who declared environments but never ran the cascade; the None/unknown semantic already exists in the script. | M2 + §3 Validation bullet | `assess` on declared-only vs generated projects yields distinct readiness; golden JSON for both. |
| R1-S4 | Ops | high | Add a staleness check between M1's live-app.yaml read and the generated `deploy/` snapshot. If declared environments (from app.yaml) ⊄ environments represented in `deploy/infra-contract.yaml`, mark readiness `stale` (advisory). | M1 reads the live manifest; bindings come from a generated artifact — drift (env added post-generation) silently reads as `generated`. Cheap set-diff keeps it $0 (FR-CDA-7). | New M1 sub-step or a §4 risk row + mitigation | Add an env without regenerating; assert readiness=`stale`. |
| R1-S5 | Architecture | medium | M3: specify the seed ORDER and conflict policy explicitly — (1) read declared `deployment.mode`; (2) if unset, seed from posture; (3) if set and it disagrees with the posture mapping, keep the declared value and emit an ADVISORY (never an error). Call out production-installed (a production desktop/CLI tool) as a legitimate non-conflict. | The plan says "seed only when mode unset" but the conflict path (posture=production, mode=installed) is only in the risk table; it belongs in the milestone with the production-installed exception named. | M3, add the 3-step ordering + the production-installed note | Seed `production`, pre-set `deployment.mode: installed`; assert value preserved + advisory (not error). |
| R1-S6 | Interfaces | medium | M4: add a grammar-coherence gate — every deployment key the templates teach must round-trip through `parse_app_manifest` (strict `_VALID_DEPLOY_KEYS`/`_VALID_DEPLOYMENT_MODES`) with zero errors. | The parser is strict with no LLM fallback; a template teaching a rejected key yields an unparseable manifest → fail-closed `hard`. Template/grammar drift is a named focus risk. | M4 + §3 M4 validation bullet | Extract every key example from the rendered templates; parse through `parse_app_manifest`; assert zero strict-key errors. |
| R1-S7 | Validation | medium | §3 M1: the assertion "byte-stable additions" / "installed project unaffected" needs a concrete idempotency + ordering test. Per-env items must be emitted in the manifest's already-sorted `deploy_environments` order so wireframe output is deterministic across runs. | `_deployment_section` will now emit variable-length per-env items; without a sort + idempotency assertion, the golden churns and "byte-stable" is unverified. | §3 M1 bullet | Run wireframe twice on the same deployed+multi-env project; assert byte-identical; assert installed-project section unchanged from current golden. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | Adversarial: M5 subprocess spawns a Python interpreter from inside an MCP tool. Specify which interpreter/venv and cwd are used, and that a missing script or import error degrades to `verdict=hard` with a reason (not a tool crash / not a silent pass). | A subprocess that can't start (wrong venv, script moved) must fail-closed like the script's own exception path, else the "deployable?" gate silently answers "unknown" as if safe. | M5 + §4 risk row | Rename the script; assert the tool returns a structured `hard`/error verdict, not an unhandled exception. |
| R1-S9 | Security | low | Adversarial on FR-CDA-6: confirm `assess`/the new tool never echo secret VALUES from the `deploy:` secrets backend or env bindings into JSON — only names/counts/status. The infra-contract may contain binding *targets*; ensure only `status` is surfaced. | Read-only is not the same as safe-to-print; surfacing binding values through an agent-callable tool would leak operator content (bucket 4). | §4 risk row + M2/M5 note | Seed an infra-contract with a secret-looking value; assert it never appears in `assess`/tool JSON. |

##### Endorsements
- (none — R1 is the first round; no prior untriaged items.)

---

## Requirements Coverage Matrix — R1

Analysis only (orchestrator triages). Maps each requirement to plan milestone(s) and coverage.

| Requirement | Plan Milestone(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-CDA-1 (assess surfaces deployment readiness) | M2 (+M1 data) | Partial | Boolean "deploy/ present" understates OQ-6 readiness (R1-S3/F3); unbound-binding source not unified with M5 (R1-S1/F2); no staleness state (R1-S4/F6). |
| FR-CDA-2 (wireframe section extension) | M1 | Partial | Per-env binding read duplicates M5's; sort/idempotency for new per-env items unspecified (R1-S7). |
| FR-CDA-3 (posture → mode DEFAULT not force) | M3 | Partial | Seed order + conflict policy + production-installed exception only in risk table, not the milestone (R1-S5/F5). |
| FR-CDA-4 (kickoff templates deployment inputs) | M4 | Partial | No grammar-coherence gate ensuring taught keys parse under strict `_VALID_DEPLOY_KEYS` (R1-S6/F7). |
| FR-CDA-5 (check_deploy_coherence MCP tool) | M5 | Partial | OQ-7 subprocess-vs-in-process unresolved; fail-closed/argv-safety on subprocess unspecified (R1-S2/S8/F4, R1-F1). |
| FR-CDA-6 (assist-not-operate preserved) | M5 §1 row, §3 | Partial | Read-only asserted by action verb but not at the subprocess invocation contract (R1-F1); no secret-value redaction clause (R1-S9). |
| FR-CDA-7 (deterministic, $0) | All (no LLM) | Full | Staleness/idempotency tests (R1-S4/S7) strengthen the determinism claim but no new gap. |
| OQ-6 (readiness vs presence) | M2 | Gap → recommend resolve | Recommend tri-state readiness (R1-S3/F3). |
| OQ-7 (subprocess vs in-process) | M5 | Gap → recommend resolve | Recommend subprocess, normative (R1-S2/F4). |
