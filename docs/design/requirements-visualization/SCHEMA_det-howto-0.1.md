# det-howto v0.1 — the field specification

**Date:** 2026-08-17 · **Type:** format grammar (a det-doc-kit member) · **Status:** proposed
**Governed by:** `CHARTER_det-doc-kit-family.md` · **Mirrors:** `SCHEMA_det-plan-0.1.md` / `SCHEMA_det-handoff-0.1.md`
**Formalizes:** the latent HOWTO format on disk (~12 `HOWTO_*.md` instances) — the operator usage guide.
**Projector target:** the format the **third projector** (`howto_codegen`) targets — the *independent-replication* test of `STANDARD_det-doc-kit-projector-pattern.md`.

> A **det-howto is a `$0` projection of a REQ's declared command surface** — the always-current **command
> reference** for what a feature ships. It is a **degenerate-edge projector** (charter: "terminal, lower
> value"): only the mechanical skeleton (commands · flags · invocation order · prerequisites) is projected;
> **most of a real HOWTO is human-residue** (the *when* · *why* · *troubleshooting* narrative). The projector
> emits the skeleton + large human-residue placeholders; it does not author guidance. Generator cited (§6).

## 0. Provenance — the format already exists; this names it

Measured across ≥2 instances (charter §3): `HOWTO_ENABLE_WHOLE_PROJECT_TSC_GATE.md`,
`HOWTO-PRIME-DELIVERY-LEDGER.md`, `HOWTO_COMPARE_LIVE.md`, `DEPLOY_HARNESS_HOWTO.md`, and ~8 more. Every one
carries a command/flag reference (the projectable skeleton) wrapped in operator prose (the human-residue).

## 0.1 The source — a REQ's declared command surface (authored → `$0`-eligible)

The projector reads the REQ's **`## Contract projection`** table plus any FR that declares a CLI verb. That surface
is **authored in the REQ** (not generated), so the projection is `$0`. A REQ with **no** command surface owes no
HOWTO (§5 solo-vs-gap) — this doc-type fires narrowly, which is why the charter calls it "lower value."

**The source table's column contract (pinned — independent-replication finding: the adopter had to reverse-engineer
it from one example).** The `## Contract projection` table is `| Entry (name) | Kind | Words/Structure | Notes |`
with a header row + separator row to skip; the projector reads rows whose `Kind ∈ {command, option}`, taking `Entry`
as the command `name` and `Notes` as the `note`.

**The CLI-verb extraction rule (pinned — the fuzziest derivation).** A "CLI-declaring FR" contributes a command iff
it contains an inline-code `` `startd8 …` `` span **whose tokens contain no placeholder** from the closed set
`… · <…> · ${…}/$WORD · {…} · […]` (reusing REQ-08's own placeholder grammar). A span with a placeholder (e.g.
`` `startd8 navigator …` ``) is **prose, not a runnable command** — it is NOT emitted (never-inferred: a placeholder
span is not a real command surface).

## 1. Document header **[core]** (mirrors det-plan-0.1 §1)

| Field | Type | Req'd | Meaning | Derivation |
|-------|------|-------|---------|------------|
| `version` | semver | yes | doc lineage | authored |
| `formatVersion` | const `det-howto/0.1` | yes | which kit schema this obeys | this doc |
| `pairsWith` | path | yes | the REQ whose surface this documents — **MUST resolve LIVE** (§3) | the source REQ |
| `companionKind` | enum `HOWTO` | yes | emitted **only** for a REQ with a command surface (§5 solo-vs-gap) | §5 |
| `maturity` | enum `0.1 · 0.2 · 0.3[.n] · 0.4-post-CRP · 0.5 · v1.x` | yes | a projected howto starts at `0.1` (§4) | §4 |
| **DIDL** `name`/`handle`/`ref` | strings | yes | semantic name + `{kind}/{slug}-{8hex}` + `cc:intent:…` | `naming.name_forms` (`kind="howto"`) |

## 2. The command reference **[core] — the projected skeleton**

`reference = { commands[], prerequisites[] }` — derived from the REQ's command surface; none authored.

| Field | Derivation from the REQ |
|-------|-------------------------|
| `commands[]` | the `## Contract projection` rows with `Kind ∈ {command, option}` (+ FR-declared CLI verbs): each `{ name, kind, note }` |
| `prerequisites[]` | the reuse/phantom audit — each authored `Touches`/code-`Lives` ref resolved on disk `LIVE`/`PHANTOM` (det-plan §4 lifted; a `PHANTOM` prereq ⇒ the how-to references something absent) |

## 3. Liveness **[core]** (mirrors det-plan-0.1 §6)

`pairsWith` MUST resolve **LIVE** — a HOWTO documenting a `PHANTOM`/`ABSENT` REQ is a survivorship lie. Same
`LIVE / PHANTOM / LEGACY / ABSENT` classes; **count LIVE only**. A `PHANTOM` prerequisite (§2) is this invariant
per reference.

## 4. Maturity — the anti-inflation ladder (mirrors det-plan-0.1 §7)

A projected howto is `maturity: 0.1`. It climbs only by earning evidence; never claims post-CRP unearned.

## 5. Honesty rules **[core]**

- **Solo-vs-gap:** a HOWTO is projected **only** for a REQ that declares a command surface; a REQ with **no**
  commands/options gets none — do not manufacture a usage guide for a feature with no invocation surface
  (charter §6.4). *(The gate signal is the presence of `## Contract projection` command rows — a third
  doc-type-specific signal, after det-plan's REQ marker and det-handoff's ledger state.)*
- **Never-inferred:** the command reference derives from the REQ's authored surface; the projector invents no
  command, no flag, and **no guidance**. The **when / why / troubleshooting narrative is HUMAN-RESIDUE** — the
  projector emits a placeholder, never invented prose. *(This doc-type is mostly residue — the honest split.)*
- **Anti-inflation:** §4 — a projected howto starts at `0.1`.

## 6. The projector — CITE, don't define (Mottainai; charter §2)

The `$0` REQ→HOWTO projector is **not specified here** (the kit owns the format). It reuses:
`navigator.req_header` (header + the `## Contract projection` locate), `det_req.parse_fr_lines` (CLI-declaring
FRs), the on-disk reuse resolver (→ `prerequisites`), `naming.name_forms` (DIDL). Registered SDK-side under
`startd8.contractors.deterministic_providers`, like `plan_codegen`/`handoff_codegen`.

## 7. Conformance (the lint gate — what a validator checks)

A det-howto/0.1 doc is conformant iff: `formatVersion == det-howto/0.1`; `companionKind == HOWTO`; `pairsWith`
resolves **LIVE** (§3); every `commands[]` entry traces to a `## Contract projection` row or a CLI-declaring FR
in the paired REQ (no invented command); `prerequisites[]` marks each ref `LIVE`/`PHANTOM` honestly; `maturity`
is not inflated (§4); and the narrative sections (when/why/troubleshooting) are **not** machine-asserted as
derived. A `.bad` fixture (phantom `pairsWith` · an invented command · a `PHANTOM` prereq claimed present ·
inflated maturity) must fail the gate `exit 1`. Findings emit as **SARIF 2.1.0** via the ONE
`coverage_map/findings_sarif` (imported, not vendored — charter §5/§6).

*v0.1 — formalizes the latent HOWTO format, mirroring det-plan/handoff-0.1. **A degenerate-edge projector:** the
command-reference skeleton is `$0`-projected from the REQ's declared surface; the operator narrative is
human-residue. The projector is the next artifact (cited) — and the **independent-replication** test of the
projector standard (a third doc-type, built cold from the standard).*
