# Concierge Deployment-Awareness (items 4–6) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-21
**Status:** Ready for CRP / implementation
**Owner:** StartD8 SDK / concierge + wireframe + mcp
**Extends:** `CONCIERGE_MCP_REQUIREMENTS.md` (v0.3); builds on `cloud-native-deploy`,
`deploy-environments`, `deployment-mode`.

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

- **FR-CDA-1 (assess surfaces deployment readiness).** `concierge assess` SHALL include a
  `deployment` block: declared mode, `deploy:` posture (target cloud, secrets backend, trust_gateway),
  declared environments, whether the `deploy/` tree is present, per-env unbound operator-binding
  count (from the infra-contract), and the deploy-coherence verdict.
- **FR-CDA-2 (wireframe deployment section extended — narrowed v0.2).** The EXISTING
  `_deployment_section` (already surfaces mode/persistence/bind/schema-init/secrets/observability/
  identity + coherence) SHALL be extended with: declared environments, the emitted `deploy/` artifact
  set, and per-env unbound bindings (from the infra-contract). Its 3 pre-existing-broken golden tests
  SHALL be fixed in passing.
- **FR-CDA-3 (posture → deployment DEFAULT, not force — clarified v0.2).** Posture currently drives
  *convention provenance* only (`writes.py`). `instantiate-kickoff --posture prototype|production`
  SHALL additionally **seed a default** `deployment.mode` (prototype→installed, production→deployed) +
  minimal `deploy:` block — seeded ONLY when mode is unset; an explicit `deployment.mode` always wins
  (mirrors deployment-mode OQ-5). Mode/deploy stay independent declared fields; an advisory flags conflicts.
- **FR-CDA-4 (kickoff templates deployment inputs).** The concierge kickoff templates SHALL explain
  the deployment-posture inputs (mode, `deploy:` block, environments, secrets backend, trust_gateway)
  in commissioner-friendly terms.
- **FR-CDA-5 (check_deploy_coherence MCP tool).** Add an agent-callable, read-only
  `check_deploy_coherence` MCP tool returning the fail-closed verdict (verdict/findings/unbound
  bindings), delegating to the existing SDK check — no reimplementation.
- **FR-CDA-6 (assist-not-operate preserved).** All additions SHALL be read-only over MCP (Concierge
  never runs the deploy, applies manifests, or records a gate).
- **FR-CDA-7 (deterministic, $0).** No LLM; all surfaces derive from the manifest + the deterministic
  cascade + the coherence verdict.

## 3. Non-Requirements

- NOT running/applying the deploy (operator + Kestra/Argo); NOT the cap-dev-pipe gate (orchestrator).
- NOT auto-forcing `deployment.mode` from posture — only seeding a default.
- NOT a new MCP server — extend the existing concierge FastMCP wrapper.
- NOT authoring real per-env values (operator/company content, bucket 4).

## 4. Open Questions

> OQ-1..OQ-5 resolved by the planning pass — see §0. Remaining for CRP:

- **OQ-6 (new).** Should `assess` distinguish "declared but not yet generated" (deploy block declared,
  no `deploy/` tree on disk) from "generated" — i.e., surface a *readiness* state, not just presence?
- **OQ-7 (new).** Should the `check_deploy_coherence` MCP tool shell out to the script (process
  isolation, matches cap-dev-pipe's consumer contract) or call `deploy_coherence_verdict` in-process
  (faster, but couples the tool to SDK internals)?

---

*v0.2 — Post-planning self-reflective update. FR-CDA-2 narrowed to an extension of the existing
wireframe section, FR-CDA-1 reframed as inherited-via-delegation (FR-C10), FR-CDA-3 clarified to
default-not-force, 5 OQs resolved, 2 new for CRP. Headline: the deployment-surfacing substrate already
exists — this is a small extension + posture default-seed + one read-only MCP tool, not new machinery.*

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
