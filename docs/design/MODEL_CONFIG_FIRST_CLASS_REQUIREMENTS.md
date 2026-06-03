# First-Class Model Configuration — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-03
**Status:** Draft

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass explored the agent-resolution, config, ingestion, and catalog
> code. It revised the shape of the fix substantially (>30% — the requirements
> were premature): the problem is **narrower and more surgical** than v0.1 implied.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Many roles silently default to Claude | Only **ingestion assessor+transformer** (always) and **micro-prime cloud-retry last-resort** (only when drafter unset) are real silent sources. Semantic-verifier is off by default (`None`→skipped); postmortem-judge is opt-in (`use_llm_judge`); security-gate + domain-preflight are **deterministic** (no LLM agent resolution found). | Role registry shrinks; FR-1 scope reduced |
| Ingestion needs a new config passthrough | `plan_ingestion_workflow` already reads `config["assessor_agent"]/["transformer_agent"]`; the runner already plumbs `config["lead_agent"]/["drafter_agent"]` (`run_contextcore_workflow.py:681`). It's a **key-name mismatch** — ingestion never sees the contractor's agents. | OQ-6 resolved; FR-8 cheaper (map keys / inheritance, no new object) |
| Defaults should not be provider-specific | Catalog defaults are provider-pinned **by design** (`PRIMARY_CONTRACTOR_LEAD=CLAUDE_OPUS_LATEST`, REQ-PCMR-100/101). The problem isn't the default — it's that **no single override propagates to all roles**. | FR-4 reframed: "a global override propagates" not "no provider defaults" |
| Need a bespoke resolver + role enum everywhere | `get_latest_model(provider, tier)` already exists (tiers flagship/balanced/fast/mini). A single **`--provider` / `models.default_provider`** knob + per-role tier makes "all-Gemini" trivial and propagates through one path. | FR-3/FR-7 simplified around provider+tier |

**Resolved open questions:**
- **OQ-1 → Judge/security not silent sources.** Postmortem judge is gated by
  `use_llm_judge` + explicit `judge_agent_spec` (None ⇒ rules-only). Security/Anzen
  resolves no LLM agent (deterministic `verify_file`). Drop from "silent" set;
  keep configurable *if* enabled.
- **OQ-2 → Domain-preflight is deterministic** (no `resolve_agent_spec`/`generate`).
  Remove from the role registry.
- **OQ-3 → No new file.** Thread per-role keys through the existing workflow
  `config` dict + CLI args (the contextcore runner already builds one). Pipe passes
  them as env/flags.
- **OQ-4 → Add one global `--provider` + a repeatable `--agent role=spec`;** keep
  `--lead/--drafter/--tier3` as aliases. The global knob is the highest-value piece.
- **OQ-5 → Inheritance:** reviewer←lead (exists), cloud_retry←drafter (exists);
  **add ingestion_assessor←lead, ingestion_transformer←lead** so contractor agents
  propagate to ingestion by default. *(Implementation correction: transformer
  inherits **lead**, not drafter — both ingestion roles were historically the
  balanced/capable Sonnet, and the heavy seed transform must not silently downgrade
  to the cheap drafter.)*
- **OQ-6 → Mechanism exists (key mismatch).** See table.
- **OQ-7 → Provider+tier.** Role default = `get_latest_model(default_provider,
  role_tier)`; a global provider override flips every unset role at once.

---

## 1. Problem Statement

Model/agent selection in the prime pipeline is **partial and leaky**. The CLI
flags `--lead-agent` / `--drafter-agent` / `--tier3-agent` reach only the prime
*contractor*. Every other LLM-calling role resolves its model independently, and
several **silently default to Claude** regardless of those flags. Evidence:
run-026 was launched all-Gemini, yet plan-ingestion ran on Claude Sonnet and the
generated app calls Claude directly.

| Role / site | Where | Current default | Honors `--lead/--drafter/--tier3`? |
|---|---|---|---|
| Lead (spec) | prime contractor | `--lead-agent`, else catalog | ✅ yes |
| Drafter (code) | prime contractor | `--drafter-agent`, else catalog | ✅ yes |
| Tier3 (COMPLEX escalation) | complexity routing | `--tier3-agent` | ✅ yes |
| Reviewer | `prime_contractor.py:578` | inherits lead | ✅ (via lead) |
| **Ingestion assessor** | `plan_ingestion_workflow.py:1391` | **`Models.CLAUDE_SONNET_LATEST`** | ❌ no |
| **Ingestion transformer** | `plan_ingestion_workflow.py:1405` | **`Models.CLAUDE_SONNET_LATEST`** | ❌ no |
| Micro-prime cloud-retry | `prime_adapter._resolve_cloud_agent_spec` | tier→`cloud_agent_spec`→drafter→**`DRAFT_MODEL_CLAUDE_HAIKU`** | ⚠️ partial (drafter if set) |
| Micro-prime local | `micro_prime/engine.py` | `ollama:startd8-coder` | n/a (local) |
| Semantic verifier | `micro_prime/engine.py:4822` | `None` → skipped | ⚠️ off by default |
| Postmortem judge | `contractors/postmortem.py:372` | `judge_agent_spec` (~claude-haiku) | ❌ no (TBD) |
| Security / Anzen gate | `security_prime/` | TBD | ❌ no (TBD) |
| Domain preflight | `workflows/builtin/domain_preflight*` | TBD (LLM?) | ❌ no (TBD) |
| Generated app `call_ai_service` | `backend_codegen` → app `service.py` | **`anthropic.Anthropic()` hardwired** | n/a (product runtime) |

**Existing infra (underused):** `ConfigManager` (`~/.startd8/config.json`) has a
`models` section, but only TUI presets (`claude`, `gpt4`) and an `artisan` block
(ON HOLD). The active Prime/ingestion/micro-prime paths do **not** read it for
model selection.

**Consequences:**
1. A "Gemini run" is not all-Gemini — the (expensive) plan→seed transformation
   silently runs on Claude Sonnet.
2. Cross-model comparisons are never clean — ingestion (Claude) + micro-prime
   local (Ollama) are held constant while only codegen lead/drafter vary.
3. Silent provider fallbacks hide cost and break reproducibility/billing intent.

## 2. Requirements

- **FR-1 Canonical role registry.** Define a single enumerated set of LLM *roles*
  spanning the pipeline (lead, drafter, tier3, reviewer, ingestion_assessor,
  ingestion_transformer, semantic_verifier, micro_prime_cloud_retry,
  micro_prime_local, postmortem_judge, security_gate, domain_preflight). One
  authoritative list, referenced everywhere.

- **FR-2 Single resolver.** All LLM-calling sites resolve their agent through one
  function `resolve_role_agent(role, ...)`. No site instantiates an agent from a
  hardcoded provider string.

- **FR-3 Explicit precedence.** Resolution order is deterministic and documented:
  per-call/CLI override → run config → `~/.startd8/config.json` `models.<role>` →
  role inheritance (e.g. reviewer←lead) → **catalog default**. Catalog defaults
  live in `model_catalog.py`, never inline.

- **FR-4 A single override propagates to every role (no leaks).** Provider-pinned
  catalog defaults may stay (they are intentional, quality-tuned — REQ-PCMR), but a
  **global `default_provider` / per-role override must reach *all* LLM roles**,
  including ingestion. Role defaults resolve as `get_latest_model(default_provider,
  role_tier)`, so setting the provider once flips every unset role. The current
  `or Models.CLAUDE_SONNET_LATEST` ingestion fallbacks are replaced by this path.
  *Acceptance:* an all-Gemini run shows **zero** Anthropic calls in plan-ingestion
  (the run-026 failure), verifiable from per-role provenance (FR-7).

- **FR-5 Config surface (SDK).** A `models.<role>` block in `~/.startd8/config.json`
  (extending the existing `ConfigManager`) sets per-role agent spec + max_tokens.
  A run-level config object/file can override it per run.

- **FR-6 CLI surface.** The CLI exposes per-role overrides without a flag
  explosion — e.g. a repeatable `--agent <role>=<spec>` and/or `--models <file>`,
  in addition to keeping the existing `--lead/--drafter/--tier3` as aliases.

- **FR-7 Observability.** Each run records the **resolved** agent spec per role
  (provenance/postmortem), so "what ran where" is answerable from artifacts (the
  L3 metadata fix already does this for lead/drafter — extend to all roles).

- **FR-8 Cap-dev-pipe wiring (Phase 2).** `pipeline.env` / pipe flags pass a model
  config through to every stage (ingestion + contractor), so a single setting makes
  a run truly single-provider. Removes the silent Claude in plan-ingestion.

- **FR-9 Backward compatibility.** Existing `--lead/--drafter/--tier3` flags, the
  `artisan` config block, and current default behavior keep working (defaults
  unchanged unless explicitly overridden).

- **FR-10 Migration/lint.** A guard (test or check) asserts no new hardcoded
  provider-specific agent string is introduced in the pipeline path; existing ones
  are migrated to the resolver.

## 3. Non-Requirements

- Changing *which* model is best for any role (this is about configurability, not
  defaults tuning).
- Making the **generated app's** `call_ai_service` provider-parameterized — that is
  the Mechanical-Assembly FR-MA-1 concern (generated product code), tracked
  separately; noted here only as adjacent.
- Multi-provider load-balancing, fallback-on-error chains, or routing policies
  beyond explicit per-role selection.
- Artisan pipeline (ON HOLD) — its config block stays as-is.
- Cost/budget enforcement changes (separate subsystem).

## 4. Open Questions

- **OQ-1** Does the security/Anzen gate and the postmortem judge actually call an
  LLM in the standard prime run, and what do they default to? (Inventory completeness.)
- **OQ-2** Is domain-preflight LLM-backed, and if so where does it get its model?
- **OQ-3** Should the run-level model config be a new file (e.g. `models.yaml`),
  a block in the existing provenance/seed, or CLI-only? What does the pipe find
  easiest to pass through?
- **OQ-4** Best CLI ergonomics: repeatable `--agent role=spec`, a `--models` file,
  or both? How do these compose with the legacy `--lead/--drafter/--tier3`?
- **OQ-5** Inheritance graph: which roles sensibly inherit from which (reviewer←lead
  confirmed; should ingestion_transformer←lead? cloud_retry←drafter is current)?
- **OQ-6** Does `plan_ingestion_workflow` receive any config object today through
  which assessor/transformer could be threaded, or must the CLI/pipe plumb a new one?
- **OQ-7** Where should the catalog "role default" live — extend `model_catalog.py`
  with a role→ModelInfo map, or a tier alias ("balanced"/"cheap")?

---

## 5. Implementation Plan (Phase 1 = SDK, Phase 2 = pipe)

> **Status (2026-06-03):** Step 3 + 4(SDK half) **DONE** (`216a6996` — ingestion
> resolver honors explicit/lead/default_provider). Step 6 `--provider` **DONE**
> (`d245d1fd` — contractor fills unset lead/drafter/tier3 from provider tiers).
> **Surface 3 drift-hash fix DONE** (this commit): `render_ai_service`/`render_ai_layer`
> take `ai_agent_spec`, bake `DEFAULT_AGENT_SPEC`, self-describe it in a
> `# ai-agent-spec:` header line; `drift._check_ai_drift` recovers + re-renders with
> that spec so a custom-provider service.py reads `in_sync` (not false drift).
> Remaining: surface-3 CLI (`generate backend --ai-agent-spec` + assembler thread),
> step 2 shared `resolve_role_agent`, step 5 other-site migration, step 7 full
> per-role provenance, step 8 guard, Phase 2 pipe wiring (all 3 surfaces).

**Phase 1 — SDK (smallest correct surface first):**

1. **Catalog role-default helper.** Add `model_catalog.role_default(role, provider=None, tier=None)` returning a spec from `get_latest_model(provider or default_provider, role_tier)`. Define the role→tier map (lead/reviewer=balanced-or-flagship, drafter/cloud_retry=fast, ingestion_assessor=balanced, ingestion_transformer=fast/balanced, semantic_verifier=fast).
2. **Single resolver.** `utils/agent_resolution.resolve_role_agent(role, *, override=None, run_config=None, **kw)` applying precedence: `override` → `run_config[role]` → `~/.startd8 models.<role>` → inheritance → `role_default(role)`. All sites call this.
3. **Fix the ingestion leak (highest value).** In `plan_ingestion_workflow._resolve_assessor_agent`/`_resolve_transformer_agent`, replace `or Models.CLAUDE_SONNET_LATEST` with `resolve_role_agent("ingestion_assessor"/"ingestion_transformer", override=config.get(...), run_config=...)`; inherit lead/drafter when unset.
4. **Plumb the keys.** In `run_contextcore_workflow.py` / `run_plan_ingestion`, map the run's `lead_agent`/`drafter_agent` (and a new `default_provider`) into the ingestion config keys so the contractor's agents reach ingestion.
5. **Migrate the other sites** to `resolve_role_agent` (micro-prime cloud-retry last-resort, reviewer, judge-when-enabled).
6. **CLI.** Add `--provider <name>` (global default) and repeatable `--agent <role>=<spec>` to `run_prime_workflow.py`; keep `--lead/--drafter/--tier3` as aliases that set the corresponding role.
7. **Provenance (FR-7).** Extend the L3 metadata writer to record the resolved spec for every role used in the run.
8. **Guard (FR-10).** A test asserts no `or Models.CLAUDE_*` / hardcoded `anthropic:`/`gemini:` agent literal remains on the pipeline path (allowlist the catalog).

**Phase 2 — cap-dev-pipe:**

9. `pipeline.env`: add `MODEL_PROVIDER` / per-role vars; `startd8-cap-dlv-pipe.sh` forwards them as `--provider`/`--agent` to both plan-ingestion and the contractor.
10. Reconcile with the existing `PRIME_CONTRACTOR_EXTRA_ARGS` and the M4 plan/landmines (L2/L13).

Each step traces to a requirement: 1–2→FR-1/2/3; 3–4→FR-4/8; 5→FR-2; 6→FR-6/9; 7→FR-7; 8→FR-10; 9–10→FR-8.

---

*v0.2 — Post-planning self-reflective update. Role registry narrowed (3 roles
dropped as non-LLM/opt-in), FR-4 reframed, FR-8 simplified (mechanism already
exists — key mismatch), 7 open questions resolved, implementation plan added.*
