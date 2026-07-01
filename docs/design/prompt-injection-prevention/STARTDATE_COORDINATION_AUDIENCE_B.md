# SDK → StartDate: Audience-B AI-pass guards are coming — coordination + the default-on go/no-go gate

**From:** startd8-sdk team
**To:** StartDate (strtd8) app team
**Date:** 2026-06-26
**Re:** Prompt-injection prevention, Audience B (SDK-emitted AI-pass guards, FR-B0–B7)
**Status:** Heads-up + action request. **No SDK behavior has changed yet.**
**Source docs:** `docs/design/prompt-injection-prevention/{REQUIREMENTS.md,PLAN.md}` (v0.3, CRP-hardened);
grounded in your `SDK_FR_MSG_SCOPED_PASS_CAPABILITY_BRIEF_2026-06-11.md`.

---

## BLUF

The SDK is about to make **prompt-injection resistance a default property of generated AI passes** —
the generic guards your FR-MSG brief asked us to own (input cap / output validation / single-in-flight /
provenance), plus instruction/data fencing. Most of this is additive. **One part changes the *rendered
output* of your 7 shipping passes, and one part can *refuse to render* a pass** — so before those land
we need a **regenerate-diff go/no-go** with you. This doc says exactly what's coming, what's safe vs.
behavior-changing, and the two questions we need answered.

---

## 1. What's landing (FR-B0–B7), split by blast radius

| Capability | What it does | Blast radius for your 7 passes |
|---|---|---|
| **FR-B0** shared `app/ai/guards.py` | One generated helper (fence/normalize/validate/verify); passes import it | **Additive** — a new emitted file + imports |
| **FR-B1** instruction/data fencing (all 3 pass shapes) | Wraps untrusted request text + untrusted resolved-relation text in a `<context>` DATA-not-instructions fence | **Changes rendered prompt** (additive wrapping) — needs a regenerate-diff, low risk |
| **FR-B2** `guards.max_untrusted_chars` | Truncate oversized untrusted free-text before the prompt | **Behavior-changing if default-on** |
| **FR-B3** `guards.validate_output` | Pre-persist: length caps, control-char strip, degenerate check, **no-verbatim-input-dump**, `on_violation: drop\|reject\|flag` | **Behavior-changing if default-on** |
| **FR-B4** `guards.single_in_flight_by` | Reject concurrent dup runs (DB-backed, cross-process, TTL stale-lock recovery) | Declaration-driven (opt-in) |
| **FR-B5** `verify_provenance` | Drop fabricated `drew_on` entries (PK-keyed supplied-set, per pass shape) | Declaration-driven (opt-in) |
| **FR-B6** proportionate threat model | Default = output-corruption model, **human curation = the trust boundary** | See §3 — **auto-send refusal** |
| **FR-B7** app-side guard logging | Every guard action logs in *your app's* runtime logger | Additive (new log lines) |

## 2. The rollout decision (OQ-8) — hybrid by guard nature

- **Default-on** (safe, generous defaults): **fencing (FR-B1)**, **input-size cap (FR-B2)**, **output
  validation (FR-B3)**.
- **Declaration-driven** (you opt in per pass): **single-in-flight (FR-B4)**, **provenance (FR-B5)** —
  these need parameters (keys / a `drew_on` field), so there's no sensible universal default.

## 3. The two things that need YOUR sign-off

### (a) The default-on flip — regenerate-diff go/no-go *(the gate)*
Before we flip FR-B2/FR-B3 default-on, we will: **regenerate your 7 passes, diff the rendered output,
and hand you the diff for an explicit go/no-go.** Generous defaults mean we don't expect truncation of
legitimate content, but you own the call. **We will not flip defaults until you sign off.**

### (b) Auto-send refusal — FR-B6 *(potential build break)*
The default threat model's trust boundary **is** the human-curation step. Fencing only *reduces* (does
not eliminate) semantic injection. So a pass that **auto-sends** (no human curation between AI output and
an outbound action) will be **refused at build time** unless it explicitly opts into *stricter mode*
(adds an output-side verbatim/exfil scan + a no-auto-send-without-ack acknowledgment).

> **Question 1:** Do any of your 7 passes — or the planned FR-MSG outreach pass — **auto-send** (vs.
> persist a `confirmed:false` draft for human review)? If yes, we need to design stricter mode with you
> before it can ship; if no (all are curated drafts), you're unaffected by (b).

> **Question 2:** Any pass that today relies on **un-truncated** output or input (i.e., would a generous
> per-field cap change its behavior)? If so, name it and we'll set its cap explicitly rather than default.

---

## 4. Sequencing (what we're doing now vs. gated)

1. **Now (no coordination needed):** SDK-internal Audience-A follow-up (FR-A8 — fence the draft/review/
   micro_prime/query_prime generation prompts). Does not touch your generated apps.
2. **Increment 2a (additive, heads-up):** FR-B0 + FR-B1 (guards.py + fencing). We'll send a regenerate-diff.
3. **Increment 2b (gated on your sign-off):** FR-B2/B3 default-on flip + FR-B6 auto-send gating + FR-B4/B5
   declarative guards. **Blocked on Questions 1–2 and the go/no-go.**

## 5. What stays yours

The pass **prompt** content (CoM framing) and the `ai_passes.yaml` declarations. The SDK emits the
*enforcement scaffolding* around them; it does not author your prompts.

---

*Reply with answers to Questions 1–2 (and any pass that needs an explicit cap) and we'll schedule the
regenerate-diff. Until then, only the additive/SDK-internal pieces proceed.*
