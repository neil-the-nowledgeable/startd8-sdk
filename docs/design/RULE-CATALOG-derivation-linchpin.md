# RULE_CATALOG — the Derivation linchpin (scope)

**Project:** startd8-sdk + dev-os/det-req-kit · SARIF findings arc · Derivation increment 2
**Status:** scope (pre-build)   **Date:** 2026-08-15
**Parent:** `docs/design/SARIF-FINDINGS-REUSABILITY.md` · **Prereq:** increment 1 = `det-req-kit/req_coverage.py` (location join, shipped on `feat/det-req-sarif`)

> **Semantic name:** *Make the set of rule-ids a tool can emit an enumerable, typed authority — the
> one new artifact the FINDING↔REQ↔Derivation loop needs, which also deletes two existing smells.*

---

## 0. Why this is the linchpin (and not accidental complexity)

The audit found the loop's essential complexity is four things: the **FR set** (have it — `extract.parse`),
the **set-ops** (have them — the `dangling_touches` idiom, now reused by `req_coverage`), the **join key**
(location now via `touches`; rule-id later via the open `verify` field — **no new schema field needed**),
and **the enumerable rule catalog** — which *does not exist*.

Today the set of rule-ids a tool can emit exists only as **~40 scattered `check="..."` string literals**
across `src/startd8/validators/{,go_,java_,nodejs_,csharp_}semantic_checks.py`, plus the kit's own
`collect_findings` check names. There is no `RULE_CATALOG`/`ALL_RULES` constant anywhere. Both directions
of Derivation need this set:
- **FR → tool-config** (requirements drive tooling): to generate "which checks to run" from the FRs'
  declared rule-ids, you must know the legal rule-ids and their metadata.
- **finding → new-FR**: to decide a finding has *no owning requirement*, you join on rule-id — which must
  be a stable, enumerable identity, not an ad-hoc literal.

**The distillation win:** creating the catalog is not new accidental complexity — it *removes* two
pre-existing smells the audit named:
- **Smell D (shadow taxonomy):** rule-ids as scattered literals + the hard/advisory severity split
  hand-maintained as a per-check list (`det-req-kit/extract.py::collect_findings`).
- **Smell F (duplicated severity maps):** `_SEVERITY_TO_LEVEL` is byte-identical in
  `coverage_map/findings_sarif.py` and the kit's `sarif.py`; `SARIF_SCHEMA_URI` is defined 3×.

So the artifact Derivation needs is the same artifact that de-duplicates what's already there. That is the
test for essential complexity: it pays for itself in deletions.

---

## 1. The artifact

A **plain dict** (not a class hierarchy — see §5), one per rule-producing domain:

```python
# rule_id → its fixed metadata. The single authority for "what can this tool emit".
RULE_CATALOG: dict[str, RuleSpec] = {
    "bare_except_pass":  {"severity": "warning", "domain": "python",  "help_uri": "..."},
    "sql_injection_risk":{"severity": "error",   "domain": "security","help_uri": "..."},
    "unchecked_error":   {"severity": "warning", "domain": "go",      "help_uri": "..."},
    # … seeded from the ~40 existing check= literals …
}
```

`RuleSpec` is a `TypedDict` (typed, zero runtime cost, no ABC). `severity` is the *default* level a rule
emits; a finding may still override per-instance. `domain` groups rules (python/go/security/requirement…)
and is the namespace root.

### Namespacing (avoids cross-producer collisions)
Rule-ids are namespaced by producing tool: `startd8-semantic/bare_except_pass`,
`det-req/dangling_touches`. This is the join key's stable form. Bare ids stay backward-compatible inside a
single producer; the namespaced form is what crosses the SARIF boundary and the FR `verify` convention.

### Two catalogs, not one (the repos can't share a module)
The SDK owns `RULE_CATALOG` for its validators; det-req-kit owns one for `extract`'s requirement-doc
checks — **same reason the SARIF renderer is vendored**: the kit must not import startd8-sdk. They are
kept honest by the *namespace* (disjoint by construction) and, if useful later, a golden parity fixture —
not a shared import.

---

## 2. What reads it (the migration — behaviour-preserving)

| Consumer | Today | After |
|---|---|---|
| `coverage_map/findings_sarif.py::_SEVERITY_TO_LEVEL` | local dict | rule's default from the catalog; keep the string→level map as the *vocabulary* only |
| kit `sarif.py::_SEVERITY_TO_LEVEL` | byte-identical dup | same (its own catalog) |
| the 5 `*_semantic_checks.py` | `SemanticIssue(check="bare_except_pass", severity="warning", …)` | `severity` sourced from `RULE_CATALOG["bare_except_pass"]` — the literal stops being authored twice |
| kit `collect_findings` | hard/advisory split as a manual per-check list | `severity` = catalog lookup; the error/advisory partition is *derived*, not enumerated |
| `render_sarif_from_findings` | duck-types `check`/`check_type` | unchanged; optionally stamps `rule.helpUri`/`shortDescription` from the catalog |

Each change is a characterization-test-guarded swap (the finding output must be byte-identical before/after
for the existing fixtures). No behaviour change — only the *source of truth* moves.

---

## 3. What it unlocks (the next increments)

- **Increment 2a (this scope):** ship the two catalogs + point the severity maps / validators at them.
  Deliverable is the authority + the de-duplication. No new user-facing behaviour.
- **Increment 2b (rule-id join):** extend `req_coverage` to also join on rule-id — an FR declares the
  rule(s) it is responsible for via a `Checks: <namespaced-rule-id>` convention **on the open `verify`
  field** (no schema change). Join `FR.verify-declared rule-ids ⋈ catalog` → *declared-but-unknown* (typo)
  and *emitted-but-undeclared* (a real check no FR claims). This is the `not_evidenced` set-difference at
  the rule tier.
- **Increment 3 (Derivation):** generate each tool's active-check config *from* the FR set's declared
  rule-ids, validated against the catalog. The catalog is the contract both ends read.

---

## 4. Scope boundaries

**In:** the two `RULE_CATALOG` dicts (SDK + kit), seeded from existing literals; the migration of the
severity maps + validator severities + `collect_findings` split to read from them; `RuleSpec` TypedDict;
characterization tests proving byte-identical finding output.

**Out (deferred):** the rule-id join (2b), the `Checks:` verify-convention parser, tool-config generation
(3), consolidating the SDK/kit catalogs (they stay separate by charter), the two untyped `List[dict]`
finding producers (disk-compliance, o11y) — type them only when Derivation actually routes them.

---

## 5. Anti-accidental-complexity guardrails (explicit)

- **Plain dict + TypedDict, not a class hierarchy.** No `BaseFinding` ABC, no `RuleRegistry` object, no
  `JoinEngine`. The codebase's own `coverage_map/engine.py` docstring rejects exactly this kind of
  over-abstraction (it refused to reuse the 30-member `LanguageProfile` for 4 fields). Follow that.
- **Seed, don't re-derive.** The catalog's initial content IS the existing literals, lifted to one place —
  a move, not a new taxonomy. If a validator emits a rule not in the catalog, that's a loud test failure,
  not a silent add.
- **No new schema field.** The rule-id rides the open `verify` string via a `Checks:` convention.
- **No cross-repo import.** Two catalogs, namespaced; parity by fixture if ever needed, never by import.
- **Migration is byte-identical-guarded.** Every consumer swap is proven behaviour-preserving on existing
  fixtures before it lands.

---

## 6. Decisions needed before building 2a

- **D1 — RuleSpec fields.** Minimal is `{severity, domain, help_uri}`. Add `description`/`shortText` now
  (richer SARIF rules) or defer? (Recommend: add `description`, it's near-free and improves SARIF.)
- **D2 — namespace separator.** `startd8-semantic/bare_except_pass` (slash) vs `startd8-semantic.bare_…`
  (dot) vs `:` — pick one that survives SARIF `ruleId` + the `verify` convention + is filename-safe.
- **D3 — where the SDK catalog lives.** `validators/rule_catalog.py` (near the producers) vs
  `coverage_map/` (near the SARIF sink). Recommend `validators/` — the producers are the authority; the
  sink is a consumer.

---

### Appendix — audit provenance
Reuse census + accidental-complexity audit (this session): `dangling_touches` is the join template;
`forward_manifest.contract_id` is a red herring (no FR link); the fragmented finding shapes already
converge at the `render_sarif_from_findings` boundary (no base class needed); the catalog gap + smells
D/F are the collapsible core.
