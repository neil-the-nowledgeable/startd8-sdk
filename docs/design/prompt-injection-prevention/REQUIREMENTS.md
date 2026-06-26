# Prompt-Injection Prevention Requirements (startd8-sdk + apps built with it)

**Version:** 0.3 (Post-CRP triage)
**Date:** 2026-06-11 (v0.3: 2026-06-26)
**Status:** Draft
**Authors:** SDK team (drafted with the StartDate FR-MSG pilot as grounding)
**Scope:** Two audiences — (A) the SDK as a code generator, (B) apps the SDK generates.

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). A code
> tracing pass against `context_resolution.py`, `spec_builder.py`, `security.py`, and `ai_layer.py`
> revealed six corrections — several of which widen scope or fix an outright-wrong assumption.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| FR-A1: only `plan_context` + `requirements_text` are raw on the STANDALONE path | The STANDALONE strategy (`context_resolution.py` `StandaloneContextStrategy`) leaves **≥5 untrusted fields raw**: `project_objectives` (:840), `semantic_conventions` (:843), `architectural_context` (:847), `plan_context` (:861), `requirements_text` (:866). `prior_error_feedback` (:903) is raw in **both** modes. | FR-A1 widened to the enumerated set; FR-A1 now names a complete-coverage acceptance test. |
| Fencing can be applied at one uniform chokepoint | **Key-name divergence**: STANDALONE emits `requirements_text`; PIPELINE emits `requirements_context` — popped at two different sites in `spec_builder.py` (:1142 vs :1200). A naive single-point wrap would **double-wrap** PIPELINE content (already wrapped at `context_resolution.py:1067–1120`). | New **FR-A1a**: fencing is mode-scoped (wrap in STANDALONE only, PIPELINE already wraps) **and** the fence helper must be idempotent (detect an existing `<context` wrapper) as defense-in-depth. |
| FR-A2: `sanitize_prompt_content()` normalizes (clean-and-continue), just needs wiring in | The function **raises `ValidationError`** on empty/oversized/invalid-UTF8 — it is a *reject* validator, not a sanitizer. Its `MAX_PROMPT_LENGTH` (1 MB) **conflicts** with the already-present caps: `_PLAN_LOAD_MAX_BYTES`=16 KB (`prime_contractor.py:131`), requirements `[:2000]` (`derivation.py:782`), `_MAX_INPUT_ROWS`=200, Kaizen 2 MiB. | FR-A2 reframed: need a **non-throwing normalize** (strip null/control, validate UTF-8, **truncate** not reject) distinct from the throwing validator, plus a **cap-reconciliation** sub-requirement. OQ-3 resolved. |
| FR-B: the SDK's emitted AI passes have no fencing and the untrusted path isn't built yet | The **scoped/relational Shape C is already shippable** (`AiPass` has `scope`, `scope_relations`, `reads_confirmed`, `output_fk`; `_render_pass_scoped()` exists) and emits `full_prompt = prompt + json.dumps(context) + text` — **raw concatenation of untrusted text, no fence**. | FR-B1 is more urgent and applies to **all three** pass shapes (whole-model, source-bound, scoped). |
| OQ-5: unknown whether guards should be emitted inline or factored to a helper | Passes are **string-templated Python**; emitting 60+ lines of guard logic as string literals per pass is untenable and untestable. | OQ-5 resolved: **shared `app/ai/guards.py` helper module** (emitted once via `render_ai_layer()`, imported by every pass) for validation/cap logic; provenance stamp stays inline (already is). |
| FR-B2 input-size cap is new | `_MAX_INPUT_ROWS=200` (`ai_layer.py:956`) exists but caps **row count of context**, not the **char size of untrusted free-text**. No output validation exists at all. | FR-B2/FR-B3 confirmed genuinely new (not duplicative). |

**Resolved open questions:**
- **OQ-3 → Resolved.** `sanitize_prompt_content()` is a throwing validator with a 1 MB cap; it is **not** fit to wire in as-is. The plan adds a separate non-throwing `normalize_untrusted_text()` and reconciles the scattered caps into one declared policy. The throwing validator may remain for the outbound full-prompt total.
- **OQ-5 → Resolved.** FR-B guards live in a generated shared helper (`app/ai/guards.py`), not inline string literals.

**Heuristic check:** ~4 of 13 requirements changed materially (FR-A1, FR-A2, FR-B1, plus new FR-A1a) and 2 OQs resolved — above the 30% revision line. The requirements were premature on the SDK-internals specifics; the planning pass corrected them at document cost.

---

## 1. Problem Statement

The SDK threads **untrusted document and source text into LLM prompts** at multiple points, and it
emits apps that do the same. Today neither path has a coherent prompt-injection defense. The existing
security modules (`security_prime/`, `query_prime/security/`) defend the **generated code's** runtime
(SQL injection, credential leakage, lifecycle) — they say nothing about malicious *instructions* riding
into a prompt and hijacking generation or an app's AI feature.

This is now concrete: **FR-MSG** (StartDate's interviewer-message generator) is the app's *first*
LLM feature that consumes untrusted text (`JobDescription.rawText` from a job board, interviewer
`priorities`, `relationshipNotes`). The StartDate team has already worked out a right-sized threat
model for it (output-corruption, not exfil; human curation as the trust boundary) and is asking the
SDK to **own the generic guards** that implement it (capability brief
`SDK_FR_MSG_SCOPED_PASS_CAPABILITY_BRIEF_2026-06-11.md`, capabilities C2b/C2c/C2d/C4). Those guards
*are* the prompt-injection defense — they're just framed as cost/DoS/dedup. We should name them as
such and make injection-resistance a **default property of SDK-emitted AI passes**, not app-owned
prompt hygiene.

### Trust model (decided)

Requirements/plan/seed documents **and** AI-extraction source content are treated as **untrusted
injection carriers**. This holds even when the commissioning user is benign, because in real pilots
(StartDate, navig8) the *content inside* those artifacts can originate from a true end-user or a third
party (a job board, an intake form, an uploaded document) — bucket-4 content per CLAUDE.md.

### Gap table — Audience A (SDK as generator)

| Surface | Current State | Gap |
|---|---|---|
| `wrap_user_content()` fencing (`context_formatters.py:34`) — wraps content in `<context>` tags + "DATA, not instructions" | Exists and is correct | Called **only on the PIPELINE-mode path** (`context_resolution.py:1067–1120`). The STANDALONE path passes `plan_context`/`requirements_text` **raw** — the default path has no fence. |
| `sanitize_prompt_content()` (`security.py:656`) — null-byte/UTF-8/length normalization | Defined | **Never called anywhere in `src/`.** A security primitive that was never wired in. |
| `_INJECTION_PATTERNS` denylist (`context_resolution.py:177`) | Exists; catches "ignore previous instructions"-style markers | Its own code comment says it is a denylist and "inherently incomplete." It is being relied on as if it were a boundary; it can only be telemetry. |
| Plan-ingestion PARSE prompt (`plan_ingestion_workflow.py`) | Loads `plan_text` from disk, interpolates into a prompt (inside `<plan>` tags but unescaped) | Untrusted plan text reaches the parser prompt with no `sanitize → fence` step. |
| `ai_layer.py` source-bound extraction (`:612-620`) | Server-stamps a provenance `binding` for traceability | Provenance is a *traceability* signal, not a *trust* signal — a fenced/validated read boundary is absent. |
| Generation-output gates (`security_prime`, `query_prime`) | Score generated code | An injected instruction that says "skip the security note / mark this pass" has no defense distinct from the (incomplete) denylist. |

### Gap table — Audience B (apps built with the SDK)

| Surface | Current State | Gap |
|---|---|---|
| AI passes generated from `ai_passes.yaml` (`ai_layer.py`) | Two pass shapes: whole-model and source-bound | Neither shape fences untrusted input as "data, not instructions" by default; the fencing is left to the app-authored prompt. |
| Untrusted free-text into a prompt (`JobDescription.rawText`, `priorities`, `relationshipNotes`) | App must hand-author a char cap | No declarative input-size cap (cost/DoS surface). [pilot C2b] |
| AI output before persist | App must hand-author validation | No declarative output gate (length cap, strip control chars, no verbatim input dump). [pilot C2c, FR-MSG-11] |
| Re-run / button-mash storms | App must hand-author | No declarative single-in-flight guard. [pilot C2d] |
| Fabricated grounding (`drew_on` lists rows it never saw) | App must hand-author | No declarative provenance verification. [pilot C4, FR-MSG-6] |

---

## 2. Requirements

### Audience A — the SDK as a code generator (FR-A)

**FR-A1 (Universal fencing on every prompt-assembly path).** Every point where untrusted document,
requirement, plan, seed, or extraction-source text is interpolated into a generation prompt MUST route
through `wrap_user_content()` (or an equivalent fence) before reaching the model. The STANDALONE-mode
gap MUST be closed so PIPELINE and STANDALONE are equivalent in fencing coverage. The complete set of
currently-raw untrusted fields that MUST be fenced (verified in the planning pass): `project_objectives`,
`semantic_conventions`, `architectural_context`, `plan_context`, `requirements_text` (STANDALONE
strategy), and `prior_error_feedback` (raw in both modes).
- *Acceptance:* an injection string placed in **each** of those fields appears inside a `<context …>`
  fence in the final spec/draft prompt; a coverage test enumerates the field set so a newly-added
  untrusted field fails the test until fenced.

**FR-A1a (Mode-scoped, idempotent fencing — no double-wrap).** Because STANDALONE and PIPELINE use
**different context keys** for the same data (`requirements_text` vs `requirements_context`) and PIPELINE
already fences at `context_resolution.py:1067–1120`, fencing MUST be applied **in the STANDALONE strategy
only**, OR the fence helper MUST be **idempotent** (a no-op when the value already begins with a
`<context` wrapper). The implementation MUST NOT produce nested `<context>` fences on the PIPELINE path.

**FR-A2 (Normalize before fence; reconcile caps).** Untrusted text MUST be passed through a
**non-throwing** normalization step (strip null/control characters, validate/repair UTF-8, **truncate**
to a declared bound — never raise on oversize) at the ingestion boundary, before fencing. The existing
`security.py:656` `sanitize_prompt_content()` is a *throwing reject-validator* with a 1 MB cap and is
**not** fit for this path as-is; it MUST either be split (validate vs. normalize) or a new
`normalize_untrusted_text()` added, and the dead primitive then wired in or removed (no security
function may sit defined-but-uncalled).
- **FR-A2a (Cap reconciliation).** The scattered, inconsistent caps — `_PLAN_LOAD_MAX_BYTES`=16 KB,
  requirements `[:2000]`, `_MAX_INPUT_ROWS`=200, `MAX_PROMPT_LENGTH`=1 MB, Kaizen 2 MiB — MUST be
  reconciled into a single documented cap policy (per-field input caps + one outbound full-prompt
  total), so truncation behavior is predictable and not silently duplicated.
  Reconciliation MUST first **classify each cap as security vs functional** in a documented table:
  `[:2000]` (derivation *summarization*) and `_MAX_INPUT_ROWS` (context *budget*) are **functional** caps
  that encode generation-quality decisions, and MUST be **excluded** from the security cap policy —
  folding them under it could silently change generation output. Only security-purpose truncations belong
  to the unified policy; generation output MUST be unchanged after reconciliation. [R1-F5]

**FR-A3 (Denylist is telemetry, never a boundary).** `_INJECTION_PATTERNS` matches MUST NOT be the
sole control. Matches SHOULD be **logged/counted** (injection-attempt telemetry) and MAY raise the
content's risk tier, but fencing + normalization (FR-A1/A2) are the boundary. No path may depend on
the denylist returning clean to be safe.

**FR-A4 (Plan-ingestion parity).** The plan-ingestion PARSE prompt MUST apply the same
`sanitize → fence` discipline to `plan_text` before interpolation, with the "data not instructions"
instruction present in the parser's framing.

**FR-A5 (Extraction-source trust boundary).** `ai_layer.py` source-bound and (future) scoped/relational
reads MUST fence the source content they feed the model. The provenance `binding` MUST be treated as a
*post-hoc traceability* record, distinct from the *input-time* trust fence — both are required.

**FR-A6 (Gates are not bypassable by content).** No instruction embedded in untrusted content may
cause the generation pipeline to skip or downgrade a security/quality gate (`security_prime`,
`query_prime`, validators). Gate invocation MUST be control-plane, not derivable from model output that
untrusted input can steer.
- *Status (planning trace, 2026-06-11):* **largely confirmed.** `_run_anzen_gate()` is called
  unconditionally in the integration sequence (`integration_engine.py:3114`); the only skip path is an
  `ImportError` (the `query_prime`/security extra not installed — an install-state condition) which
  writes a `"skipped"` sentinel so "clean" ≠ "never ran". The gate runs **after** repair and **before**
  advisory downgrade by design, so verdicts are not silently demoted.

**FR-A6a (Security-gate allowlist is a trust-sensitive control file).** The false-positive allowlist
loaded by the Anzen gate (`security_prime/allowlist.py:load_allowlist`, read from `project_root`) is a
finding-suppression control. It MUST NOT be writable by the generation process from untrusted content,
and every allowlist-driven suppression MUST be logged/auditable (which entry suppressed which finding),
so an attacker cannot quietly grow the allowlist to mask injected-code findings.
- *Audit (2026-06-26):* **Logging clause ✅ done** — each suppression is logged (now at WARNING with a
  `security_finding_suppressed` event: check type + file + authorizing justification, `integration_engine`)
  **and** tracked in `allowlist_hit_tracker` → gate-report metrics. **Writability clause ◻ open** — no
  protected-path guard exists; nothing prevents the generation/integration write path from emitting a
  `security_allowlist.yaml` at project root. **Follow-up:** add a protected-path write guard (refuse to
  create/overwrite `security_allowlist.yaml` + other operator control files from generated content) at the
  file-write chokepoint. Tracked — not a quick item; do not rush into the spec-fencing PR.

**FR-A7 (Observability — operational-only).** Injection-attempt detections, truncations, and fence
applications MUST be logged via `get_logger` (OTel/Loki-visible) with enough context to audit which
artifact/source carried the attempt — without logging the full payload. This telemetry is
**operational only** (alerting/dashboards); it MUST NOT feed the Kaizen improvement loop or any
automated self-correction path, because that would route attacker-controlled signal into generation
(feedback-poisoning). A read-only, non-driving cross-run count for human review MAY be added later. *(OQ-6.)*

**FR-A8 (Fencing coverage beyond the spec prompt — follow-up).** FR-A1's *shipped* coverage test
enumerates the **spec-prompt** (`spec_builder`) fields only; its "every prompt-assembly path" intent is
**not yet met** for the other untrusted-text→prompt paths and they MUST be brought under the same
`normalize → fence` discipline: the **draft** prompt (`drafter.py`, including `prior_error_feedback` — a
*second-order* carrier whose error text can echo untrusted source), the **review** path (`reviewer.py`),
**`micro_prime`** (whose generic prompt path bypasses spec-path fencing), and **`query_prime`**
generation prompts. The coverage test SHOULD become **discovery/inventory-based** — failing when a *new*
prompt-assembly site interpolates an unfenced untrusted field — rather than a hardcoded field list, so
the universality claim is actually enforceable. [R1-F4, R1-S5]

### Audience B — apps built with the SDK (FR-B), lifting the FR-MSG guards to SDK-generic

**FR-B1 (Default instruction/data separation in generated passes — all three shapes).** Every
SDK-emitted AI pass that reads any field flagged untrusted MUST wrap that field as a clearly
**delimited data block**, with the generated harness stating that text inside data blocks is content
to describe, never commands to follow. This is emitted by the harness — the app prompt does not have to
hand-roll it. *(Generalizes FR-MSG-11's "instruction/data separation.")* This MUST cover **all three**
emitted pass shapes — whole-model (`_render_pass_read`), source-bound (`_render_pass_text_bound`), and
**scoped/relational (`_render_pass_scoped`)** — the last of which is already shippable and today emits
`prompt + json.dumps(context) + text` with **no fence**. The free-text request field and any resolved
untrusted relation text (e.g. a `JobDescription.rawText` reached via `scope_relations`) MUST be fenced;
trusted confirmed value-model context need not be.

**FR-B0 (Guard logic lives in a generated shared helper).** The FR-B2/B3/B5 guard logic MUST be emitted
**once** as a generated shared module (`app/ai/guards.py`, added via `render_ai_layer()`) and imported
by each pass — NOT inlined as per-pass string-templated Python. Simple one-line steps already inline in
the persist helpers (the provenance stamp) may stay inline. *(Resolves OQ-5.)*

**FR-B2 (Declarative input-size cap — C2b).** `ai_passes.yaml` MUST support a `guards.max_untrusted_chars`
(or equivalent) that truncates oversized untrusted free-text before the prompt, with a logged
truncation event. Applies to all passes, not just FR-MSG.

**FR-B3 (Declarative output-validation gate — C2c / FR-MSG-11).** `ai_passes.yaml` MUST support a
`guards.validate_output` block enforced **before persist**, covering: per-field length caps,
control-char stripping, a degenerate-output check, **and a no-verbatim-input-dump check** — the
persisted/sent output MUST NOT contain a verbatim untrusted-input span longer than a configured
threshold. This is the echo/exfil control named in the Audience-B gap table; without it the gate cannot
catch the model echoing injected input into the body. Partial-failure behavior MUST be declarable via
`guards.on_violation: drop|reject|flag` (drop the offending field / reject the whole pass / persist with
a flag), and the chosen mode applies to multi-field passes uniformly; default `reject`. [R1-F1]

**FR-B4 (Declarative single-in-flight guard — C2d).** `ai_passes.yaml` MUST support
`guards.single_in_flight_by: [keys]` so the generated harness rejects concurrent duplicate runs (one
AI call per logical draft) — closing the re-run-storm cost/DoS surface.

**FR-B5 (Declarative provenance verification — C4 / FR-MSG-6).** `ai_passes.yaml` MUST support
`verify_provenance: {field, against:[...]}` so the harness drops AI-authored "what I used" entries that
are not a subset of the rows actually supplied, before persist. This is a **generic** guard across all
three pass shapes (independent of the scoped shape — it ships without it). The "supplied set" MUST be
assembled **per-shape from what the pass actually fed the prompt**: whole-model `input_entities` **plus
resolved `scope_relations`** when a `scope` is present — so the check neither false-flags a legitimate
relation citation nor misses fabrication against a resolved relation. *(OQ-7.)* For the **source-bound**
shape (`_render_pass_text_bound`, which feeds bound source rows, not `input_entities`), the supplied set
is **the bound source row(s) actually fed to the prompt**. The subset check MUST key on a **stable
identity (primary key), not the title/headline** — two rows sharing a title must remain distinguishable,
or a fabricated `drew_on` entry false-matches a same-title row. [R1-F2]

**FR-B6 (Proportionate threat model, surfaced not hidden).** The generated guards MUST default to the
*output-corruption* threat model (a single-user/curated app), with the **human curation step as the
documented trust boundary** — not a claim of exfil-proofing. Apps with a stronger threat model (multi-
tenant, auto-send) MUST be able to opt into stricter guards declaratively. "Stricter mode" is **not a
bare flag**: it MUST enable a concrete, enumerated set of additional controls — at minimum (a) an
**output-side verbatim/exfil scan** that rejects output embedding a confirmed-row value not in the pass's
own output fields, and (b) **no-auto-send-without-acknowledgment**. Because fencing only *reduces* (does
not eliminate) semantic-injection success (NR-1) and the default model's trust boundary *is* the human
curation step, a pass declaring **auto-send** (no human curation) MUST be **refused at build time**
unless it explicitly opts into stricter mode — the safe-sounding default must not silently permit an
unsafe auto-send configuration. [R1-F3, R1-S8]

**FR-B7 (Emitted guards are observable in the generated app).** Every guard action the SDK emits —
input truncation (FR-B2), output rejection/flag (FR-B3), single-in-flight rejection (FR-B4), and dropped
provenance entry (FR-B5) — MUST emit a structured log line in the **generated app's own runtime logger**,
not only as SDK-side build-time telemetry (FR-A7). A silently-dropped exfil attempt in a deployed
auto-send app is precisely what an operator must be able to audit. [R1-F6]

---

## 3. Non-Requirements

- **NR-1.** We do **not** claim to defeat semantic/adversarial prompt injection via a denylist or any
  pattern set. Fencing + normalization + output validation + human curation are the controls; the
  denylist is telemetry only.
- **NR-2.** We do **not** re-implement generated-code vulnerability scanning (SQLi, credential leak,
  lifecycle) — that is already `security_prime` / `query_prime`'s job. This work is strictly about
  *instructions injected into prompts*, on both the generator and generated-app sides.
- **NR-3.** We do **not** build a bespoke exfiltration scanner for Audience B by default (the pilot's
  CRP explicitly right-sized this away for a single-user local app). Stricter modes (FR-B6) are opt-in.
- **NR-4.** We do **not** author app prompts. The prompt (CoM framing, the actual instruction/data
  copy) stays app-owned; the SDK emits the *enforcement scaffolding* around it.
- **NR-5.** We do **not** change the `security_prime`/`query_prime` scoring contracts; FR-A6 is about
  *invocation* not being content-steerable, not about new scorers.

---

## 4. Open Questions

- **OQ-1.** ~~Per-field flag, inferred default, or provenance-origin?~~ **RESOLVED (2026-06-11):**
  **deny-by-default with a `trusted:` allowlist** — every free-text field is untrusted/fenced unless
  explicitly marked trusted. Secure-by-default; prevents a repeat of the STANDALONE-gap bug class.
  Affects FR-B1 surface and the FR-A1 coverage test (the test enumerates the *trusted* exceptions; any
  unlisted field is expected-fenced).
- **OQ-2.** ~~Unconditional fencing vs. tiered by a risk signal?~~ **RESOLVED (2026-06-11):**
  **always-fence unconditionally.** Tiering would couple the trust boundary to the incomplete denylist
  (rejected by FR-A3/NR-1). Token cost is trivial; fencing is idempotent (FR-A1a). The only residual
  concern — prompt-quality regression — is validated via a small A/B before locking (plan note), not a
  reason to weaken the boundary.
- **OQ-3.** ~~Is `sanitize_prompt_content()` fit to wire in as-is?~~ **RESOLVED (§0):** no — it's a
  throwing reject-validator with a mismatched 1 MB cap. FR-A2 now calls for a separate non-throwing
  normalizer + cap reconciliation.
- **OQ-4.** ~~Is gate invocation control-plane or content-steerable?~~ **RESOLVED (2026-06-11):**
  control-plane — `_run_anzen_gate` is called unconditionally (`integration_engine.py:3114`); only skip
  is install-state (`ImportError` → sentinel); runs before advisory downgrade. One residual surface
  found and specified: **FR-A6a** (the gate allowlist is a trust-sensitive control file).
- **OQ-5.** ~~Emit guards inline vs. shared helper?~~ **RESOLVED (§0 / FR-B0):** shared generated
  `app/ai/guards.py` helper module.
- **OQ-6.** ~~Injection telemetry → Kaizen or operational-only?~~ **RESOLVED (2026-06-11):**
  **operational-only** (Loki/OTel metrics/alerts), NOT in Kaizen. A fenced injection is a successful
  defense, not a quality defect; and routing attacker-controlled signal into an automated improvement
  loop is a **feedback-poisoning** risk. A read-only, non-driving cross-run count (hybrid) may be added
  later for human review, but must never steer generation. (FR-A7 updated accordingly.)
- **OQ-7.** ~~Does FR-B5 provenance compose with the C1 scoped shape?~~ **RESOLVED (2026-06-11):**
  **independent guard, shape-aware supplied-set.** Provenance ships as a generic guard for all 3 shapes
  (independent to *build*, per the brief), but the generated pass MUST compute the `supplied` set from
  what it actually fed the prompt — confirmed `input_entities` **plus resolved `scope_relations`** for
  scoped passes — so it neither false-flags a legitimate relation citation nor misses fabrication
  against it. (FR-B5 updated.)
- **OQ-8.** ~~Opt-in vs default-on for the 7 shipping passes?~~ **RESOLVED (2026-06-11):**
  **hybrid by guard nature.** Default-on (safe/generous defaults) for guards with universal defaults —
  fencing (FR-B1, already default-on for untrusted fields), input-size cap (FR-B2), output validation
  (FR-B3). **Declaration-driven** for parameterized guards that have no sensible default — single-in-flight
  (FR-B4, needs keys) and provenance (FR-B5, needs a field). The default-on flip MUST be coordinated with
  the StartDate team (they track the live editable SDK), validating the 7 passes on regenerate. (FR-B6
  threat-model opt-out still governs the stricter modes.)

---

*v0.2.1 — Post-planning self-reflective update + all 8 open questions resolved. v0.2 changes: FR-A1
widened (5+ fields enumerated), FR-A1a added (mode-scoped/idempotent fencing), FR-A2 reframed
(non-throwing normalize + cap reconciliation), FR-B1 extended to all 3 pass shapes, FR-B0 added (shared
guard helper). v0.2.1 changes: OQ-1 (deny-by-default + trusted allowlist), OQ-2 (always-fence), OQ-4
(gate invocation confirmed control-plane; FR-A6a allowlist-integrity added), OQ-6 (telemetry
operational-only, FR-A7 updated), OQ-7 (provenance shape-aware supplied-set, FR-B5 updated), OQ-8
(hybrid guard rollout) — OQ-3/OQ-5 resolved in v0.2. Grounded in: verified SDK attack surface
(`context_formatters.py`, `context_resolution.py`, `security.py`, `ai_layer.py`, `plan_ingestion_workflow.py`)
and the StartDate FR-MSG pilot (`SDK_FR_MSG_SCOPED_PASS_CAPABILITY_BRIEF_2026-06-11.md`,
`FR_MSG_INTERVIEWER_MESSAGE_REQUIREMENTS_v0.2-draft.md` FR-MSG-6/8/11 + CRP R1 appendix).*

*v0.3 — Post-CRP-R1 triage (all 6 F-suggestions accepted; see Appendix A). FR-B3 (no-verbatim-dump +
`on_violation`), FR-B5 (source-bound supplied-set + PK key), FR-B6 (concrete stricter mode + auto-send
refusal), FR-A2a (security-vs-functional cap classification) strengthened; FR-B7 (emitted-guard app-side
logging) and FR-A8 (fencing coverage for draft/review/micro_prime/query_prime paths) added. Audience A
remains implemented/merged (PR #58); FR-A8 is the next Audience-A follow-up, FR-B* the Audience-B increment.*

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
| R1-F1 | Restore "no verbatim input dump" to FR-B3 + declare partial-failure `on_violation` | CRP R1 | ACCEPTED — merged into **FR-B3**: added no-verbatim-input-dump check + `guards.on_violation: drop\|reject\|flag` (default reject), uniform across multi-field passes. | 2026-06-26 |
| R1-F2 | FR-B5 source-bound supplied-set + PK (not title) identity key | CRP R1 | ACCEPTED — merged into **FR-B5**: source-bound supplied set = bound source rows; subset check keys on stable PK, not title. | 2026-06-26 |
| R1-F3 | FR-B6 specify "stricter mode" + warn/refuse auto-send | CRP R1 | ACCEPTED — merged into **FR-B6**: enumerated stricter-mode controls (exfil scan + no-auto-send-without-ack); auto-send refused at build time unless stricter mode opted in. | 2026-06-26 |
| R1-F4 | FR-A1 universality vs enumerated set; cover review/micro_prime/query_prime; discovery-based test | CRP R1 | ACCEPTED — added **FR-A8** (follow-up) scoping shipped FR-A1 to the spec path and requiring the draft/review/micro_prime/query_prime paths + a discovery-based coverage test. Not a reopen of merged FR-A1. | 2026-06-26 |
| R1-F5 | FR-A2a classify caps security vs functional before unifying | CRP R1 | ACCEPTED — merged into **FR-A2a**: classification table required; `[:2000]`/`_MAX_INPUT_ROWS` excluded as functional; generation output unchanged after reconciliation. | 2026-06-26 |
| R1-F6 | Emitted guards must log in the generated app's runtime | CRP R1 | ACCEPTED — added **FR-B7**: every emitted guard action logs a structured line in the generated app's own logger (not just SDK-side FR-A7). | 2026-06-26 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — all R1 F-suggestions accepted; they were anchored, correct spec gaps) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-06-26

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-06-26 00:00:00 UTC
- **Scope**: Requirements quality for unbuilt Audience B (FR-B0–B6) + deferred follow-ups (FR-A2a, FR-A6a) + missing-security hunt. Merged Audience A design treated as built context. (Companion plan suggestions R1-S* in PLAN.md.)

##### Executive summary

- FR-B3 requirement text drops the "no verbatim input dump" clause its own gap table requires — the actual exfil/echo control (R1-F1).
- FR-B5 leaves the source-bound shape's supplied-set and the subset identity key undefined (R1-F2).
- FR-B6 "stricter mode" is a named flag with no specified behavior; the default can mislead auto-send operators (R1-F3).
- FR-A1's "every point" universality is not matched by its enumerated field set — review/`micro_prime`/`query_prime` paths escape (R1-F4).
- FR-A2a unifies security caps with functional truncations, risking silent generation-behavior change (R1-F5).
- Emitted-guard actions (truncate/drop) are not required to be logged in the generated app — an audit gap, especially for auto-send (R1-F6).

##### Requirements suggestions (F-prefix)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Restore the "no verbatim input dump" check to FR-B3, whose text only lists "per-field length caps, control-char stripping, and a degenerate-output check" — the Audience-B gap table row already names "no verbatim input dump" as a required output control. Also specify partial-failure semantics (one field fails: drop-field vs reject-pass vs persist-flag). | FR-B3 is the output gate; without the verbatim-dump check it cannot catch echo/exfil of untrusted input into the persisted/sent body. The clause exists in the gap table but was dropped from the normative requirement. | §2 FR-B3 | Output containing a verbatim untrusted span > N chars is flagged; multi-field pass with one failing field behaves per declared `on_violation`. |
| R1-F2 | Interfaces | high | In FR-B5, define the supplied-set for the **source-bound** shape (it feeds bound source rows via `_render_pass_text_bound`, not `input_entities`) and specify the **identity key** for the subset check (stable PK, not title). | FR-B5 says "all three pass shapes" but only specifies the supplied-set for whole-model + scoped ("`input_entities` plus resolved `scope_relations`"); source-bound is omitted, and a title-based subset check false-matches two same-title rows. | §2 FR-B5 ("The 'supplied set' MUST be assembled per-shape…") | Fabricated `drew_on` against a source-bound pass is dropped; two rows sharing a title are distinguished by PK. |
| R1-F3 | Security | high | FR-B6 names "opt into stricter guards declaratively" but does not say what stricter mode *does*. Enumerate its concrete additions (output-side verbatim/exfil scan, no-auto-send-without-ack) and require the SDK to **warn or refuse** when a pass declares auto-send under the curation-default model. | The default's trust boundary *is* the human-curation step; auto-send removes it. A flag with undefined behavior cannot be engaged, so the safe-sounding default silently permits an unsafe configuration (false sense of safety). | §2 FR-B6 | Declaring an auto-send pass without stricter-mode acknowledgment emits a build-time warning/refusal; stricter mode enables the enumerated extra checks. |
| R1-F4 | Architecture | medium | FR-A1 says "Every point where untrusted … text is interpolated into a generation prompt MUST route through `wrap_user_content()`," but its enumerated set + acceptance test cover only `spec_builder` fields. Either make the coverage test **discovery-based** (inventory all prompt-assembly sites) or explicitly scope FR-A1 and add a follow-up FR for the review (`reviewer.py`), `micro_prime`, and `query_prime` generation prompts. | A hardcoded field list cannot enforce a universal claim; `micro_prime`'s generic prompt path (per project memory) and the review path interpolate untrusted text and would escape the test. | §2 FR-A1 *Acceptance* bullet | A grep/AST-based site-inventory test fails when a new prompt-assembly site interpolates an unfenced untrusted field. |
| R1-F5 | Data | medium | FR-A2a unifies `_PLAN_LOAD_MAX_BYTES`=16 KB, requirements `[:2000]`, `_MAX_INPUT_ROWS`=200, `MAX_PROMPT_LENGTH`=1 MB, Kaizen 2 MiB into "one documented cap policy." First **classify** each cap as security vs functional: `[:2000]` (derivation summarization) and `_MAX_INPUT_ROWS` (context budget) are functional — folding them under the security policy could silently change generation output. | "Reconciled into a single documented cap policy" risks conflating field-level security truncation with functional content budgets that encode generation-quality decisions. | §2 FR-A2a | Doc carries a cap-classification table; functional caps are explicitly excluded from the security cap policy; derivation output unchanged after reconciliation. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F6 | Ops | medium | Require the **emitted** Audience-B guards to log their actions (truncation, output rejection, dropped provenance entry) in the *generated app's* logger. FR-B2 mentions "a logged truncation event," but FR-B3 and FR-B5 specify silent drops; FR-A7's observability is SDK-side only and does not reach the app runtime. | A silently-dropped provenance entry or silently-rejected output in a deployed app leaves no audit trail — acute for auto-send, where a dropped exfil attempt is exactly what an operator must see. | §2 FR-B3 / FR-B5 (add a logging clause; cross-ref FR-A7) | Each guard action emits a structured log line in the generated app; an injected output that trips FR-B3/B5 leaves an auditable record. |

**Disagreements** (none — this is the first round; Appendix A/B empty, no prior untriaged items to react to).
