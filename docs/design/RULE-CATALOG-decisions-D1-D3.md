# RULE_CATALOG — Decision Brief for D1–D3

**Project:** startd8-sdk + dev-os/det-req-kit · SARIF findings arc · Derivation increment 2
**Companion to:** `docs/design/RULE-CATALOG-derivation-linchpin.md` (the scope)
**Purpose:** the three gating decisions before building 2a, each with the *design choice it commits us
to* and how expensive it is to change later. Pick per row, or take the "recommended default set" at the end.

> **How to read the "locks in" column.** A `RULE_CATALOG` entry becomes the shared contract three
> consumers read — the SARIF renderer, the FR `verify` `Checks:` convention, and (increment 3) the
> tool-config generator. A choice here is cheap while it's one dict; it gets expensive once rule-ids are
> written into SARIF outputs, into REQ docs' `verify` clauses, and into generated configs. The brief flags
> which choices are additive-later (cheap) vs baked-into-artifacts (costly).

**Reversibility legend:** 🟢 cheap (additive / one-file refactor) · 🟡 medium (touches multiple modules or
existing fixtures) · 🔴 costly (rewrites data already emitted into SARIF / REQ docs).

---

## D1 — What fields does a `RuleSpec` carry?

**The decision.** Each catalog entry maps `rule_id → {…}`. What metadata is essential now vs speculative?

| Option | Fields | Designs for | Cost to add later |
|---|---|---|---|
| **A. Minimal** | `severity`, `domain` | just the de-duplication (kills smells D+F) | — |
| **B. Recommended** | `severity`, `domain`, `help_uri`, `description` | de-dup **+** richer SARIF (`rule.helpUri`, `shortDescription`) **+** IDE "learn more" | 🟢 |
| **C. Rich** | B + `fixable`, `cwe`/`owasp`, `owner`, `since`, `tags` | security mapping, ownership, autofix routing | 🟢 (all additive) |

**Recommendation: B** — `{severity, domain, help_uri, description}`.

**The design choices B commits us to:**
- **`severity` is a *default*, not a verdict.** The catalog says what level a rule *usually* emits; a
  finding may still override per instance (today `SemanticIssue.severity` is always set — the catalog
  becomes where the check *reads* its default instead of hard-coding it). This commits us to a
  "catalog-holds-defaults, finding-may-override" model — the opposite (catalog is authoritative, findings
  can't override) would be simpler but loses per-instance nuance (e.g. a normally-warning check escalated
  in a strict profile). Keep the override seam.
- **`domain` is dual-purpose: the namespace root *and* a grouping axis** (python/go/security/requirement).
  This commits `domain` to being stable and enumerable — it becomes the coarse filter in reports ("show me
  the security-domain findings") and the top of the rule-id namespace (see D2). Renaming a domain later is
  🟡 (touches every rule in it + any grouping consumers).
- **`help_uri` per rule** commits each rule to *having a canonical explanation URL*. Cheap now (can be a
  shared doc anchor); pays off in SARIF/IDE. Absent → SARIF falls back to a generic tool URI (what the
  renderers do today).
- **`description`** feeds SARIF `rule.shortDescription`. Near-free and the single biggest SARIF-quality
  win. Excluding it (Option A) leaves SARIF rules as bare ids.

**What B deliberately excludes (and why):** `fixable`/`cwe`/`owner`/`since` are all **additive later** (🟢)
— adding them is a non-breaking dict-key addition. Per YAGNI, don't design them in until a consumer
(autofix routing, a security dashboard) actually needs them. Designing them now is speculative structure —
the accidental complexity the whole exercise is avoiding.

**Downstream:** the FR `verify` `Checks:` convention (increment 2b) only ever references the **id** — none
of these fields. They *decorate* the rule at the SARIF/report boundary. So D1 is low-stakes and reversible;
it's safe to start at B and grow.

---

## D2 — What separates the producer namespace from the rule-id?

**The decision.** Rule-ids must be unique across producers and survive **three carriers**: a SARIF
`ruleId` (any string), the FR `verify` `Checks: <id>` convention (parsed from prose), and be
filename/log-safe. The qualified form is `‹producer›‹SEP›‹rule›`, e.g. `startd8-semantic‹SEP›bare_except_pass`.

| Sep | Example | What it designs for | The hazard it creates |
|---|---|---|---|
| `/` | `startd8-semantic/bare_except_pass` | reads like a namespaced path | **Collides with location semantics** — det-req `touches`/SARIF uris tokenize on `/` (`req_coverage._path_head`). A `/`-qualified ruleId *looks like a file path*; invites confusion in exactly the module that joins on paths. |
| `:` | `startd8-semantic:bare_except_pass` | common in scanner tooling | **Collides with det-req `:`** — branded touches (`cui-kind:...`) and `lives` (`git:sha:path`) already use `:`. The `verify` `Checks:` parser would have to disambiguate. |
| `.` | `startd8-semantic.bare_except_pass` | module-path feel; filename/log/SARIF-safe | none of the above — `.` is unused by det-req's touch/lives grammar and by paths |
| `-`/`__` | `startd8-semantic__bare_except_pass` | avoids all punctuation collisions | visually merges with the hyphens/underscores *already inside* both halves → unreadable, un-splittable |

**Recommendation: `.` (dot)** → `startd8-semantic.bare_except_pass`, `det-req.dangling_touches`.

**The design choice `.` commits us to:**
- **Producer names contain no dots; rule-ids contain no dots.** Then the qualified id has exactly one dot,
  so the `Checks:` parser is a bare `id.split(".", 1)` — unambiguous. This must be **enforced in catalog
  validation** (a rule-id or producer name containing `.` is a loud catalog error). That enforcement is the
  small price of the clean split.
- **The namespace is flat (producer.rule), not hierarchical.** We are *not* committing to
  `org.tool.category.rule` dotted trees — that would reintroduce the "how many dots?" ambiguity. One dot,
  two parts, forever. If sub-grouping is ever needed, it rides `domain` (D1), not more dots.
- **Avoids the location-join footgun.** Because rule-ids never contain `/`, nothing in `req_coverage`'s
  path matching can ever mistake a ruleId for a uri. This keeps increments 1 and 2b cleanly separable
  (location join on uris; rule join on dotted ids).

**Reversibility: 🔴.** Once rule-ids are written into emitted SARIF *and* into REQ docs' `verify` clauses,
changing the separator means migrating both. This is the one D to get right up front — hence choosing the
collision-free option now rather than the familiar-looking `/`.

---

## D3 — Where does the SDK catalog live?

**The decision.** `validators/rule_catalog.py` vs inside `coverage_map/` vs a new top-level module.
(The kit gets its own `det-req-kit/rule_catalog.py` regardless — two catalogs, no cross-repo import.)

| Option | Dependency direction it creates | Designs for |
|---|---|---|
| **A. `validators/rule_catalog.py`** | `coverage_map` (SARIF sink) → `validators` (rule authority); the 5 `*_semantic_checks.py` read their own catalog in-package | authority lives with the producers; the sink is a consumer |
| B. `coverage_map/rule_catalog.py` | `validators` (producers) → `coverage_map` (sink) | co-locates catalog with the SARIF renderer |
| C. new `startd8/rules/` | both import a neutral third | maximal decoupling |

**Recommendation: A — `validators/rule_catalog.py`.**

**The design choice A commits us to:**
- **`validators/` becomes the rule *authority*; everything that renders or reasons about rules depends on
  it.** This is the correct dependency direction: a **sink depends on producers, never the reverse**.
  Option B inverts that (the semantic checkers would import `coverage_map` just to learn their own
  severities) — a producer→sink dependency that reads backwards and risks a cycle as the SARIF layer grows.
- **Verified safe today:** `coverage_map` does not currently import `validators` and `validators` does not
  import `coverage_map` (checked) — so adding `coverage_map → validators` introduces **no cycle**, and A is
  a clean new edge in the right direction. B would add the wrong edge.
- **The 5 checkers read the catalog from their own package** (`from .rule_catalog import RULE_CATALOG`) —
  no new cross-package coupling for the producers at all; only the sink gains one import.
- Rejecting C: a neutral `startd8/rules/` package is decoupling nobody needs yet (one authority, one sink)
  — speculative structure = the accidental complexity we're avoiding. Promote to C only if a *third*
  independent consumer appears.

**Reversibility: 🟢** — moving the module later is a mechanical import refactor. Low stakes; A is simply the
right default.

---

## Recommended default set (if you just want to proceed)

| D | Decision | Locks in | Reversibility |
|---|---|---|---|
| **D1** | `RuleSpec = {severity, domain, help_uri, description}`; severity is a *default*, findings may override | catalog-holds-defaults model; `domain` as namespace root + grouping | 🟢 grow later |
| **D2** | `.` separator; `producer.rule`, exactly one dot, enforced in validation; flat namespace | dotted qualified ids in SARIF + `verify Checks:`; producers/rules may not contain `.` | 🔴 pick now |
| **D3** | `validators/rule_catalog.py` (SDK) + `det-req-kit/rule_catalog.py` (kit) | `validators` = SDK rule authority; sink→authority dep direction | 🟢 movable |

**The one that actually matters is D2** (🔴) — it's baked into emitted artifacts. D1 and D3 are safe to take
as recommended and adjust in flight.

**On "go with the recommendations":** that yields a byte-identical-guarded 2a — seed both catalogs from the
existing `check=` literals, point the two `_SEVERITY_TO_LEVEL` maps + the 5 validators + `collect_findings`
at them, prove finding output unchanged on existing fixtures. No user-facing behaviour change; the win is
the deletion of smells D+F and a single enumerable authority the rule-id join (2b) and Derivation (3) build on.
