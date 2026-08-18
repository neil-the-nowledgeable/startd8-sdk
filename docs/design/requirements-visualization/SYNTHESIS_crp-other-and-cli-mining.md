# Synthesis: mining the two CRP blind spots — the "other" bucket (52%) + the CLI/flags theme (#2 by reach)

**Date:** 2026-08-18 · **Type:** discovery-investigation synthesis (the blind-spot sweep) · **Status:** corrects the commonality picture + extends the grammar backlog
**Grounds in:** `dev-os/CRP-INDEX.md` + `.cache/crp_index.json` + `scripts/render_crp_index.py` (`REVIEW_THEME_RULES`/`_review_theme`) · the actual re-extracted Appendix-A rows · `REQ-25` (fact/judgment split) · `REQ-32` (the firing seam) · `SYNTHESIS_crp-theme-metabolization-four-investigations.md` (the method)
**Predecessor:** the four-investigation SYNTHESIS mined the *top themes* (~1,700 rows); this mines the two it skipped — the uncharacterized **"other"** (3,772 rows) and **CLI/flags/config** (315 rows), the #2-by-reach theme the earlier table dropped.

---

## 0. The headline

The 14-keyword theme taxonomy is a **floor, not a census** — it materially undercounts. Two agents re-extracted the actual rows (reproducing the index counts exactly) and found:

- **The "other" bucket (52% of all accepted rows) is ~55% real signal, ~45% genuine noise.** The signal splits into **4 keyword-blind leakage gaps** (existing themes undercounted 30–150 rows each) + **3 genuinely-new metabolizable themes** (89–192-doc reach each) the taxonomy has no keyword for.
- **CLI/flags/config is ~74% metabolizable** into a clean new `Config:` field + fact-rungs, led by a cross-repo **precedence-resolution** sub-pattern.

Every metabolizable finding fits the **same REQ-25 fact-rung → `extract.py` advisory-lint** pattern the four-investigation sweep validated, and fires through the **same REQ-32 seam**. This is not new machinery — it is more predicates on the proven path.

---

## 1. CLI / flags / config precedence (315 rows / 175 docs) — the missed #2

**~74% metabolizable** (234/315 genuine; ~26% is keyword-collision noise — `client`/`click` substrings, and `flag`/`override` used as *code* concepts not CLI). Sub-patterns ranked by reach:

| Sub-pattern | rows | docs | Metabolization |
|---|---:|---:|---|
| **precedence-resolution** (env/CLI/file/default ordering) 🥇 | 44 | 35 | **new FR field `Config: sources=[…] precedence=<order>`** + fact-rung (config-shaped FR naming ≥2 sources with no declared precedence → GAP). Cross-repo (startd8 + ContextCore + the 7-home `REQ-CDP-INT-005`). |
| mode-flag-semantics (`--check`/dry-run/apply) | 36 | 33 | mostly review-only (cross-command design judgment, no lexical tell) |
| undeclared-underspecified | 18 | 13 | folds into ambiguity fact-rung |
| output-contract (missing `--json`/exit-code) | 15 | 14 | fact-rung reusing the `exit-class` Touches kind |
| flag-no-default | 14 | 12 | fact-rung (mode switch, no default landing → GAP) |
| override-governance | 11 | 11 | fact-rung (`--force`/`--override`/`unattended` with no guard vocab → GAP) — the 7-repo `REQ-CDP-INT-005` class |
| flag-no-validation | 6 | 6 | **reuses `query_prime/security verify_file`** (option-injection: `--end-of-options`, `^-` ref) |

**Grounding that makes this real, not hypothetical:** config precedence is a *shipped SDK bug class* — the embedded cap-dev-pipe resolves **`env > CLI`** (the opposite of the naive "CLI wins" several accepted rows presume), and a missing `pipeline.yaml` is valid 3-tier resolution ([[reference_capdevpipe_config_resolution]], issue #220). The `precedence-undeclared` fact-rung would have forced that ordering to be declared up front. Most rungs **reuse the existing `option`/`exit-class` `Touches:` kinds** (`SCHEMA.md:185-193`) — only `Config: precedence=` is genuinely new.

---

## 2. The "other" bucket (3,772 rows / 461 docs) — discovery

### 2a. Four keyword-blind LEAKAGE gaps (existing themes undercounted — a $0 census fix)

The classifier keys on a lexeme; these rows recur by *meaning* while never using it (proven: clusters have **0-row keyword overlap** with the theme they belong to):

| Leakage cluster | rows | docs | Belongs to | Fix (add keywords to `REVIEW_THEME_RULES`) |
|---|---:|---:|---|---|
| parity / golden / drift / round-trip | ~150 | 110 | **determinism** (true reach ~2.5× its reported 96) | `golden`, `characterization`, `parity`, `drift`, `round-trip` |
| make-explicit / implicit-assumption | 157 | 100 | **ambiguity** (raises 542 → ~700) | `explicit`, `implicit`, `unstated` |
| contract / interface / protocol / signature | ~157 | 111 | **schema-types** | `protocol`, `interface`, `signature` |
| threat-model / trust-boundary / egress | 66 | 56 | **security** | `threat model`, `trust boundary`, `attack surface`, `egress`, `allowlist` |

**This quantifies the "concept-embedding mining" research thread** (was #2 research-now): the keyword bias is real and measurable — ~530 rows are misfiled into "other." Adding these keywords is a **$0, one-file edit to `render_crp_index.py`** that reclassifies them (cross-repo, the CRP-INDEX owner's tool).

### 2b. Three genuinely-NEW metabolizable themes (no keyword exists for them)

| New theme | rows | docs | Grammar sketch (fact-rung → `extract.py`) | Convergence |
|---|---:|---:|---|---|
| **Dependency-ordering** (highest new reach) | 388 | 192 | `Depends:`-shaped fact-rung — a multi-phase/artifact FR with build-ordering language but no declared dependency → GAP; acyclicity check parked (LLM dep-graphs are unreliable) | **IS the demand for the open `Depends:` field (G-1)** + REQ-29's `dependsOn` — the corpus's biggest new theme validates a backlog item we already have |
| **Provenance / source-of-truth** | 159 | 114 | new `Provenance: source=<ref> canonical=<yes>` — an FR that *derives* a value (infer/enrich/fingerprint) with no named source → GAP | extends REQ-25's binding/`source_id` discipline + `ai_layer.py` |
| **Cost / budget** | 134 | 89 | new `Budget: tokens=<cap>|cost=<ceiling>` — an FR invoking an LLM pass with no budget named → GAP (astonishingly stereotyped, low-FP) | ties to the SDK cost-tracking core |

### 2c. The honest noise floor (the disciplined stop)

**~45% of "other" (1,550 rows, ~21% of ALL accepted) is genuine one-off/meta noise** that must NOT be forced into a theme: 498 rows are FR-doc bookkeeping ("split FR-4", "resolve FR-2a-vs-FR-9"), the rest irreducible project heterogeneity ("kit z-bands for decor", "cap line length for minified files"). A forced 15th "misc" theme would be the discovery-analog of manufacturing a finding.

---

## 3. The corrected commonality picture + the grammar-field batch it feeds

- **The taxonomy undercounts by design.** True classified signal is ~**55% of "other" + the 14 themes**, not 48%. Four existing themes are 30–150 rows light; three real themes were invisible. The commonality analysis was directionally right but quantitatively low.
- **The det-req-kit grammar-field batch just grew.** The open `Depends:` (G-1) + REQ-30 `Emits:` + REQ-31 `Lifecycle:` now gain **`Config:` (CLI precedence), `Provenance:`, `Budget:`** — and the 388-row dependency-ordering theme is the strongest single justification for `Depends:`. Batch them as one cross-repo det-req-kit grammar addition, all firing through REQ-32's seam, all fact/judgment-split per REQ-25.
- **A cheap immediate win exists** — the 4-keyword census fix (§2a) reclassifies ~530 rows for a one-file dev-os edit, sharpening every future theme count.

## 4. One-line conclusion

*Mining the two blind spots proved the theme census is a floor: the "other" bucket hid 4 keyword-blind undercounts of existing themes and 3 real new metabolizable themes (dependency-ordering, provenance, cost/budget — 89–192-doc reach), while the missed CLI theme is 74% metabolizable into a `Config: precedence=` field grounded in a shipped `env > CLI` bug. All extend the REQ-25/REQ-32 fact-rung path and the det-req-kit grammar-field batch; ~45% of "other" is correctly-absent one-off noise.*
