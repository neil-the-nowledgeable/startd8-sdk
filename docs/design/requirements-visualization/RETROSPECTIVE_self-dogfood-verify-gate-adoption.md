# Retrospective — Self-Dogfood the Verify Gate Adoption

> **Readable handle:** `retrospective/sdk-navigator-dogfoods-verify-liveness-on-own-corpus-20926abc`
> **Semantic name:** *Reflect on the shipped self-dogfood verify-gate adoption (REQ-27) to extract the standard, surface dormants, and feed yokoten*
> **Canonical ref:** `cc:intent:requirements-visualization:retrospective:req-27`

**Pilot:** REQ-27 — self-dogfood `verify.gate` adoption on the SDK's own requirements corpus
**Window:** 2026-08-17 → 2026-08-19 (feat `7e26e3ff` → RECORD `12a61f01` → HTH-1 `fdbe4f3b`)
**Artifacts:** `src/startd8/navigator/{det_req,govern,sources_requirements,sources_retrospective}.py`, `scripts/navigator_spec_delivery_loop.py`, `tests/unit/navigator/test_self_liveness.py`, corpus `Gate:`/`Manual:` labels on 7 REQ docs
**HTH-1 verdict:** stale stage-count labels only; no Critical/High; Phase 2 (python-code-refactor) SKIPPED

---

## Phase 1 — The pilot (raw material)

REQ-27 shipped the "adopt it on our own corpus, honestly" remedy for the self-study Thread 1
finding: 95.6% of the corpus's own verifies were present-but-dead prose, and `verify.gate`
adoption was 0/180. The delivery had three parts:

1. **Honesty split** — `classify_corpus_verifies` classifies each FR's verify via `verify_oracle`
   into mechanically-attestable (`command`) vs legitimately-manual (`assertion`/`manual`), resolving
   the single misleading "96% dead" figure into a real-gap count + an honest-manual count.
2. **Gate adoption** — 9 corpus FRs across 6 REQ docs gained a `Gate:` binding to the runnable
   check their verify already names, moving adoption from 0/180 to >0.
3. **Manual marker** — REQ-22's 8 ironic prose verifies (and any other legitimately-manual ones)
   gained an explicit `Manual:` marker so they are counted honest-manual, not false-mechanical.
4. **Self-liveness gate** — `check_self_dogfood_verify_gates` + `render_self_dogfood_text` stand up
   a standing advisory self-gate, integrable into the Spec Delivery Loop (`--self-dogfood`), that
   reports adoption and routes mechanical-but-gateless FRs to a human triage Lesson (REQ-20).

The delivery was compact: 3 commits (feat + RECORD + HTH-1 fix), no Critical/High findings.

---

## Phase 2 — Ground the actuals (Genchi Genbutsu)

### What the code actually does

| Module | Actual role (from code) |
|--------|------------------------|
| `det_req.py` | `_GATE` regex (line 156) is **case-sensitive** — `Gate:` matches, `gate:` does not. `_MANUAL` regex (line 176) is **case-sensitive** — `Manual:` matches, `manual:` does not. `parse_manual` extracted in `parse_fr_lines` BEFORE `split_fr_fields` (line 289). The `manual` field rides the FR dict, not the positional return tuple. |
| `govern.py` | `SelfDogfoodReport` (dataclass, 7 properties), `SelfDogfoodRow` (frozen dataclass, 4 properties). `classify_corpus_verifies` reads every `REQ-*.md` in the corpus, calls `verify_oracle.classify` + `parse_fr_lines`, builds one `SelfDogfoodRow` per FR. `check_self_dogfood_verify_gates` emits advisory-only findings. `_GateProbe` is a minimal duck-typed carrier so the self-gate reuses `_gate_liveness` without a full `nodes_from_requirements` projection. |
| `sources_requirements.py` | `Manual:` → `attrs["verify_kind"] = "manual"` + `attrs["verify_manual_why"]` (the REQ-08 Stage pattern — attributes, not a new Node field). |
| `sources_retrospective.py` | `build_lesson_from_mechanical_gateless` — one more Lesson builder in the regression/liveness/gateless family; same propose-don't-dispose structure. |
| `navigator_spec_delivery_loop.py` | `run_self_dogfood` callable from `--self-dogfood`; always exits 0. `--status` prints a one-line advisory adoption line (`classify_corpus_verifies`). |
| `test_self_liveness.py` | 16 tests covering FR-1 through FR-6; 4 tests run against the live CORPUS (not just fixtures). |

### Case-sensitive label parse — the dogfood-surfaced invariant

The `_GATE` and `_MANUAL` regexes are case-sensitive (no `re.IGNORECASE`). The det-req labels
`Gate:` and `Manual:` are capitalised by convention. A case-insensitive match would invent a gate
from ordinary prose — REQ-04 FR-6 ("the top acceptance **gate:** if it fails, …") was the exact
false-mechanical read the self-dogfood surfaced. The fix: the parser treats `gate:` (lowercase) as
prose, `Gate:` (capitalised) as a label. Same for `Manual:`.

This is a general invariant for all det-req plain-field labels: **a label whose name is also a
common English word MUST be case-sensitive**, or it will be invented from prose. `Lives:`, `Verify:`,
`Serves:` tolerate case-insensitivity because they are not common English words; `Gate:` and
`Manual:` cannot.

---

## Phase 2.5 — Dormant inventory

Scanned 18 public symbols across the shipped surface. Evidence is `src/` + `scripts/` call sites
(tests excluded — a test-only consumer is the dormant this probe exists to catch).

| Touch | Grep / evidence | Status |
|-------|-----------------|--------|
| `SelfDogfoodReport` (govern.py) | `scripts/navigator_spec_delivery_loop.py` (import + `run_self_dogfood`) | **wired** |
| `SelfDogfoodRow` (govern.py) | `scripts/navigator_spec_delivery_loop.py` (import) | **wired** |
| `classify_corpus_verifies` (govern.py) | `scripts/navigator_spec_delivery_loop.py` (import + `run_self_dogfood` + `--status` line) | **wired** |
| `check_self_dogfood_verify_gates` (govern.py) | `scripts/navigator_spec_delivery_loop.py` (import + `run_self_dogfood`) | **wired** |
| `lessons_from_self_dogfood` (govern.py) | `scripts/navigator_spec_delivery_loop.py` (import + `run_self_dogfood`) | **wired** |
| `render_self_dogfood_text` (govern.py) | `scripts/navigator_spec_delivery_loop.py` (import + `run_self_dogfood`) | **wired** |
| `build_lesson_from_mechanical_gateless` (sources_retrospective.py) | `govern.py:lessons_from_self_dogfood` | **wired** |
| `parse_manual` (det_req.py) | `det_req.py:parse_fr_lines` (line 289) | **wired** |
| `_MANUAL` regex (det_req.py) | `det_req.py:parse_manual` | **wired** (internal) |
| `_GATE` regex (det_req.py) | `det_req.py:parse_gate` | **wired** (internal, pre-existing REQ-22) |
| `_GateProbe` (govern.py) | `govern.py:classify_corpus_verifies` (line 1331) | **wired** (internal) |
| `run_self_dogfood` (loop script) | `navigator_spec_delivery_loop.py:main` (`--self-dogfood` branch) | **wired** |
| `adoption_rate` (SelfDogfoodReport) | `govern.py:check_self_dogfood_verify_gates`, `scripts/...loop.py:--status` | **wired** |
| `mechanical_gateless` (SelfDogfoodReport) | `govern.py:check_self_dogfood_verify_gates`, `render_self_dogfood_text`, `sources_retrospective.py` | **wired** |
| `honest_manual` (SelfDogfoodReport) | `govern.py:render_self_dogfood_text`, `scripts/...loop.py:--status` | **wired** |
| `dead_gates` (SelfDogfoodReport) | `govern.py:check_self_dogfood_verify_gates`, `render_self_dogfood_text` | **wired** |
| `marked_manual` (SelfDogfoodReport) | `govern.py:render_self_dogfood_text`, `check_self_dogfood_verify_gates` | **wired** |
| `attrs["verify_kind"]` / `attrs["verify_manual_why"]` (sources_requirements.py) | Set in `sources_requirements.py:331-332`; **NO consumer in any renderer** (view.py / render_a11y / render_index) — only test assertions read it | **dormant** (soft-only) |

### Summary: 17 wired, 1 dormant

**`verify_kind` / `verify_manual_why` attributes** — set on the Node by `sources_requirements.py`
when an FR carries `Manual:`, but no renderer or downstream consumer reads them. The test proves
the attribute exists (`test_fr3_marker_rides_attributes_not_a_new_node_field`) but no view renders
it. This is **soft-only**: the attribute is present in the IR but invisible to the user. It is
not a bug — the attribute is the typed-attributes seam for a future renderer to consume — but it
is dormant by the strict definition (no production consumer reads it today).

---

## Phase 3 — Retrospective insights (belief → actual)

| Kind | What I believed about what I built | What the actuals revealed | So the standard is… |
|------|-----------------------------------|---------------------------|---------------------|
| process | The honesty-split is novel; the corpus had no prior classification of its verifies | The split is a thin composition over `verify_oracle.classify` (already built for REQ-22) + `_gate_liveness` (already built for REQ-22). The novelty is the *direction* — pointing the machinery inward — not the machinery itself | **Self-dogfood is a direction, not a build.** The reuse-not-build constraint (NR-3) is the reason this shipped in one commit. When the tool already exists, the self-application is cheap |
| process | The `Manual:` marker would need changes across the parse pipeline | `parse_manual` is extracted BEFORE `split_fr_fields` (avoiding widening the positional return tuple), and the marker rides `fr["manual"]` + `attrs["verify_kind"]` (the REQ-08 Stage pattern). Zero new Node fields. The constraint on no new field was the design forcing function | **The REQ-08 Stage pattern (typed attributes, not new fields) is the safe extension seam for det-req labels.** It kept NODE_FIELD_MANIFEST at 20 |
| artifact | `verify_kind` / `verify_manual_why` attributes are consumed by renderers | **No renderer reads them.** The attribute is set (line 331) but no view/render_a11y/render_index consumer exists. It is a **dormant seam** — planted, tested, but not yet producing visible output | Dormant seam: declare it, file it, don't pretend it renders. A future renderer enhancement (CEP seed) should wire it |
| process | Case-insensitive label parsing is fine because the other labels use it | REQ-04 FR-6 ("the top acceptance **gate:** if it fails, …") parsed as a present-but-DEAD gate under case-insensitive `_GATE`. The dogfood itself surfaced this — `Gate:` and `Manual:` are common English words; `Lives:` and `Verify:` are not. Case-sensitivity is the invariant | **A det-req label whose name is also a common English word MUST be case-sensitive.** This is the general rule; `Gate:` and `Manual:` are the first instances |
| artifact | `--status` already shows adoption on every sweep | It does — line 251-255 prints a one-line advisory. But the advisory line runs `classify_corpus_verifies` a second time (once for the `--status` loop, once for the advisory). A minor perf cost on the current 10-doc corpus, but it is double-work | The double-call is technical debt, not a bug. A memo or a report-pass-through would fix it. Not worth a commit today |

---

## Phase 4 — Extract the standard

### The standard REQ-27 proved: Loop-within-a-loop / Honesty-split / Case-sensitive label

REQ-27 proved a three-part standard for self-dogfooding a verification system on its own corpus:

**1. Loop-within-a-loop.** A verification system (the liveness layer, REQ-22/23) that checks
*other people's* artifacts gains its strongest validation when pointed at the *author's own*
artifacts. The self-application is not a new build — it is a direction change (inward) over the
existing machinery. The cost is low (one composition) and the yield is high (every false-fire
is a real bug in the checker, because the author knows the corpus intimately). The pilot proved
this: the `_GATE` case-sensitivity bug was surfaced by the self-application, not by any external
use.

**2. Honesty-split (mechanical vs manual).** A binary "dead/alive" metric on a mixed-kind
population (some verifies are *meant* to be human-checked) produces a misleading single number.
The honest response is a **three-way split**: (a) mechanically-attestable + gated (genuinely
alive), (b) mechanically-attestable + gateless (the real gap), (c) legitimately manual (honestly
human). The split resolves "96% dead" into an actionable figure (the gap) and a non-actionable
one (the honest manual count). This pattern generalises: any verify/check/gate population with
mixed kinds needs the split before the metric.

**3. Case-sensitive label parse for common-word labels.** A det-req plain-field label (`Gate:`,
`Manual:`, `Was:`, `Name:`) that is also a common English word must be parsed case-sensitively,
or the parser invents labels from prose. `Lives:`, `Verify:`, `Serves:`, `Touches:` tolerate
case-insensitivity because they are not common words. The invariant: **the parser must not invent
a label the author did not write.** Case-sensitivity is the cheapest structural guard for this
class.

### Grounding

| Clause | File:line |
|--------|-----------|
| Loop-within-a-loop (self-gate reuses liveness) | `govern.py:1299-1335` (`classify_corpus_verifies` imports `verify_oracle` + `_gate_liveness`) |
| Honesty-split (three-way) | `govern.py:1228-1287` (`SelfDogfoodReport` properties: `mechanical`, `honest_manual`, `mechanical_gateless`) |
| Case-sensitive `_GATE` | `det_req.py:156` (no `re.IGNORECASE`), docstring lines 152-155 |
| Case-sensitive `_MANUAL` | `det_req.py:176` (no `re.IGNORECASE`), docstring lines 170-175 |
| REQ-08 Stage pattern (attrs, not field) | `sources_requirements.py:329-332` (`attrs["verify_kind"]`), `test_self_liveness.py:159` (`node_field_names() == 20`) |

---

## Phase 5 — Lessons + yokoten

### Surprises (lessons)

1. **The parser-invents-a-label class.** The most valuable find was the case-sensitivity bug on
   `_GATE`. It is a **class**, not an instance: any future plain-field label whose name is a common
   English word will hit the same failure. The class is now hardened by the case-sensitive regex,
   but the general rule ("label-name ∩ common-word → case-sensitive") should be checked
   prospectively whenever a new label is added.

2. **Dormant seam is an acceptable ship state.** `verify_kind` / `verify_manual_why` are
   deliberately planted as typed-attribute seams for a future renderer. They are not a bug — they
   are an honest dormant, documented here. The lesson: a dormant seam is fine if it is *declared*
   dormant (not silently assumed consumed).

3. **Double-classify on `--status`.** `classify_corpus_verifies` is called once for the status
   loop and once for the advisory line. Cheap today (10 docs), but it is double-work that should
   be collapsed if the corpus grows.

### Yokoten (spread)

- **To other det-req labels.** The case-sensitive invariant applies to `Was:`, `Name:`,
  `Approve?:` — verify each is case-sensitive (they already are; this is confirmation, not a fix).
- **To other corpora.** Any project that adopts det-req and has a verification layer should run
  the self-dogfood gate (`--self-dogfood`) over its own corpus.
- **To the renderer.** The `verify_kind` / `verify_manual_why` dormant seam is a natural CEP
  seed: a card/view could show a "manual" badge on legitimately-manual FRs, so the honesty-split
  is visible in the rendered view, not just the CLI report.

### CEP seeds (recommended for Phase 4)

| Seed | Kind | Source |
|------|------|--------|
| Wire `verify_kind` → a visible "manual" badge in the rendered FR card | enhancement (dormant→wired) | Phase 2.5 dormant inventory |
| Collapse the double `classify_corpus_verifies` call in `--status` | tech-debt (perf) | Phase 3 insight |
| Prospective case-sensitivity audit for future det-req labels | guard (metabolize the label-invents-from-prose class) | Phase 3 / Phase 4 lesson |
| `--self-dogfood --json` machine-readable output for CI | enhancement (dual-surface) | natural extension of FR-4 |

---

## Phase 6 — Yokoten + feed the forward loop

### Convergence sweep (rung 2)

The honesty-split pattern (mechanical vs manual vs gap) independently converged with:
- REQ-22's verify-liveness (structural death vs provenance-unrunnable — the absence-vs-error move)
- REQ-25's fact-rung vs judgment-rung (deterministic-checkable vs precision-gated-semantic)

All three are instances of the same move: a binary metric on a mixed population is resolved by
splitting the population into homogeneous buckets before measuring. The three splits compose
cleanly (they operate on orthogonal axes: claim-kind × structural-death × semantic-confidence).

### Feed the forward loop

The extracted standard (§4) is an input to the next `/reflective-requirements` for any
det-req-family feature that adds a new plain-field label. Specifically: the case-sensitive
invariant should be checked at spec time (the forward loop's stress-test), not discovered at
dogfood time (the reverse loop's surprise).

---

## HTH Phase 4 recommendation: **light CEP or skip**

HTH-1 found only stale stage-count labels (no Critical/High), and Phase 2 (python-code-refactor)
was SKIPPED. The dormant inventory found **1 dormant** (the `verify_kind` renderer seam) — an
honest, declared dormant, not a silent green.

**Recommendation: skip full CEP.** The 4 CEP seeds above are filed; a full diverge→cumulate→
converge pass on a 3-file, 1-dormant surface would be low-yield. If the renderer enhancement
(wire `verify_kind`) is desired, it is a standalone task, not a CEP-scale effort.
