# RED Panel Classification Unification — Requirements

**Status:** Draft (spec only — no implementation)
**Version:** 0.3.1 (post reflective-loop: planning + lessons + design-principle hardening)
**Date:** 2026-08-04
**Owner:** observability
**Scope:** `src/startd8/observability/`, `src/startd8/validators/observability_artifact_checks.py`
**Related:** OBS-200a RED scorer; AffordanceMap consume (WP-B2/FR-B4 shrink); `MetricDescriptor` (`REQ_TARGET_METRIC_BINDING.md`, #226 FR-12/FR-13)

---

## 0. Planning Insights (Self-Reflective Update)

> Built an implementation plan against the real code (`observability_artifact_checks.py`,
> `artifact_generator_generators.py`, `affordance_map_consume.py`, `metric_descriptor.py`).
> The plan corrected the v0.1 draft in nine places; the load-bearing ones are D1 and D4.

| # | v0.1 assumption | Planning discovery (evidence) | Impact |
|---|-----------------|-------------------------------|--------|
| **D1** | Fixing B3 (unify the DURATION rule) trades off against NG2/FR-5 byte-parity — R4/OQ-2 treat it as a live tension. | **No golden has a `histogram_quantile` panel lacking a `duration`/`latency` token** (`grep histogram_quantile tests/.../http_golden/*.yaml \| grep -vi 'duration\|latency'` → empty). The B3 divergence is **theoretical, absent from the corpus**. | **OQ-2 resolved → stricter rule**, at **zero** golden-coverage change. R4 downgraded from "intentionally not byte-preserving" to "no observed panel affected; guard still asserts it." |
| **D2** | `_pick_red_families` can be re-expressed to return `Mapping[RedRole, str]` (FR-8). | It returns a **positional `Tuple[Optional[str], Optional[str], Optional[str]]`** (rate/err/dur), with other call sites. | FR-8 reframed: **wrap** with a tuple→`Mapping[RedRole,str]` adapter; do **not** change the function signature. |
| **D3** | classify keys on "the panel expr". | Panels carry exprs in **both `panel["expr"]` and `panel["targets"][].expr`**; the existing helpers use targets-aware extraction (`_panel_has_expr`/`get_all_panel_exprs`, `:1240`/`:1250`). | classify_red_role **must** read the full expr set (reuse `get_all_panel_exprs`), else it mis-classifies target-based panels as NONE. |
| **D4** | FR-13 grep-guard ("RED substring logic in exactly one file") coexists with NG4 (keep `_pick_red_families` regexes). | **Direct contradiction:** `_RED_RATE_RE`/`_RED_ERR_RE`/`_RED_DUR_*_RE` (`affordance_map_consume.py:329`–`:340`) **are** RED substring classification outside `red_taxonomy`. | **Resolved by unifying, not exempting:** move the `_RED_*_RE` name→role regexes **into** `red_taxonomy` as the descriptor-free *name* classifier; `_pick_red_families` becomes a thin consumer. NG4 rewritten; FR-8/FR-13 reconciled. |
| **D5** | G2: deriving all three questions from one classifier means they "can no longer disagree." | The scorer/shrink use the **descriptor-free** tier; the generator uses the **descriptor-grounded** tier — **different tiers by design** (broad coverage vs precise presence). | G2 refined: the invariant is **per-tier** consistency (FR-7 within the descriptor-free scorer↔shrink tier). B1 is killed by **decoupling the shared function into tiers**, not by forcing global agreement. |
| **D6** | `metric_identity` dedup key = `throughput_metric \| error_selector \| latency_bucket_metric`. | `error_selector` is a **selector string** (`status=~"5.."`), not a metric name; the error leg **rides `throughput_metric`** (`rate(tm{err})/rate(tm)`, `:1058`). | Dedup identity defined **per role**: RATE→`throughput_metric`, ERROR→`throughput_metric` (the E leg is the same series), DURATION→`latency_bucket_metric`. §3.4 + OQ-4 updated. |
| **D7** | — | `_compute_red_coverage` is genuinely descriptor-free (`has_*_panel`, `:1335`); FR-5 parity is well-posed **and** (via D1) empirically clean. | FR-5 kept, strengthened with the D1 receipt. |
| **D8** | FR-3 (ERROR vs RATE) needs a rule. | Confirmed: error expr = `descriptor.selector(id, error=True)` appends `error_selector` (`:1056`) → carries `throughput_metric` **and** `error_selector`; rate expr carries only `throughput_metric`. | FR-3 implementable exactly as specced (RATE = tm ∧ ¬error_selector; ERROR = tm ∧ error_selector). |
| **D9** | Spec line numbers are exact. | All cited **symbols exist**, but line numbers run **~10 off** (`_panel_is_red_protected` at `:1435` not `:1426`; shrink helpers `:1459/:1483/:1502`). | Phantom-reference note added; **anchor tests/guards on symbol names, not line numbers.** |

**Resolved open questions:**
- **OQ-2 → stricter DURATION rule** (`histogram_quantile` **AND** duration/latency). D1 proves no existing golden loses coverage. This is the unified rule everywhere.
- **OQ-1 → keep public shims** (default retained; honors the `__all__` rule). Unchanged, now explicit.
- **OQ-4 → metric-name identity suffices** for the current single-service-per-spec dashboards (D6); the label selector is *not* part of the key. Re-open only if multi-service dashboards land.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK design-doc lessons before external review. Each changed the draft:

- **Phantom-reference audit** — every cited symbol was grepped (D2, D8, D9): all exist, but line numbers drift ~10 and `_pick_red_families`'s return type was mis-stated → FR-8 corrected, D9 note added, guards re-anchored on symbols.
- **Single-source vocabulary ownership** — this refactor *is* the lesson: `RedRole` + `classify_red_role` become the one owner; every other module cites/consumes it (FR-13). The D4 fix pulls the last stray owner (`_RED_*_RE`) into that home rather than exempting it.
- **Overloaded-term co-location** — `RedRole` lands in a **new** `red_taxonomy.py`, not bolted onto the validator or the affordance module (no second meaning stacked on an existing owner).

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked against `docs/design-princples/`. Each changed the draft:

- **Genchi Genbutsu (go and see)** — the classifier binds to the descriptor's **real** `throughput_metric`/`error_selector`/`latency_bucket_metric`, not a `_count`/`_total` suffix proxy (the core of the spec). Reinforced R1: match the **full** metric name, never a suffix.
- **Accidental-Complexity anti-principle** — the D4 resolution replaces an *exemption list* (FR-13 carve-out for `_pick_red_families`) with **one general rule** (all name→role logic lives in `red_taxonomy`). Deleting the special case beats documenting it. Also guarded the inverse: the **two-tier** classifier is justified by G4 (descriptor-free dashboards are real), not gratuitous abstraction.
- **Mottainai (don't regenerate)** — the deduping synthesizer *forwards* an already-present RED role instead of re-emitting it; the dedup key is the anti-double-emit mechanism, not a rebuild-then-restore.

---

## 1. Problem

"Is this panel a RED signal?" (RED = **R**ate / **E**rrors / **D**uration) is currently
answered by roughly **five independent substring-heuristic implementations** that were written
against different assumptions, guess at metric shape from name substrings (`_count` / `_total` /
`histogram_quantile`), and **quietly disagree**. Each copy tangles two orthogonal concerns into
one predicate, and the drift between copies has produced real bugs.

### 1.1 The five duplicates

1. **Scorer (broad, title+expr).** `has_rate_panel`
   (`src/startd8/validators/observability_artifact_checks.py:1266`), `has_error_panel` (`:1294`),
   `has_duration_panel` (`:1316`). Drive `_compute_red_coverage` (`:1335`) and the OBS-200a check
   (`:311`–`:324`). All three are exported in `__all__` (`:44`–`:46`) and reused by other modules.

2. **AffordanceMap shrink-protection (unified, title+group+expr).** `_panel_is_red_protected`
   (`src/startd8/observability/affordance_map_consume.py:1426`) — one predicate answering "would
   dropping this panel risk RED?", plus `_red_coverage_ok` (`:1450`), which prefers the scorer's
   `_compute_red_coverage` (imported at `:1452`) but falls back to counting
   `_panel_is_red_protected` panels (`:1462`).

3. **Generator gate (broad rate/error via the scorer + a narrow inline fallback).**
   `_ensure_red_coverage` (`src/startd8/observability/artifact_generator_generators.py:991`)
   imports and calls the scorer's `has_rate_panel` / `has_error_panel` (`:1016`–`:1020`) to decide
   whether to synthesize; on `ImportError` it drops to a **narrow inline** fallback
   (`rate(...)` **`_count`-only**, `status` excluded — `:1024`) for rate but a **broad** substring
   fallback (`"error" in e or "status_code" in e` — `:1025`) for error. So the fallback path's
   rate detector and error detector are asymmetric.

4. **AffordanceMap RED family picker (regex, locus-driven).** `_pick_red_families`
   (`affordance_map_consume.py:430`) with `_RED_RATE_RE` (`:329`), `_RED_ERR_RE` (`:333`),
   `_RED_DUR_STRONG_RE`/`_RED_DUR_WEAK_RE`/`_RED_TIMESTAMP_RE` (`:338`–`:340`) — a *fourth*
   independent set of rate/error/duration substring rules, used to assign metric families to RED
   roles when synthesizing from cited loci.

5. **Two synthesizers that both emit "Request Rate" / "Error Rate" / "Duration" panels.**
   - `_ensure_red_coverage` (`artifact_generator_generators.py:991`) — descriptor-sourced;
     appends `Request Rate` (`:1056`–`:1062`), `Error Rate` (`:1064`–`:1083`), and an
     `Availability (1h)` gauge (`:1105`–`:1115`).
   - `_locus_red_dashboard_yaml` (`affordance_map_consume.py:2098`) — locus-sourced; appends
     `Request Rate` (`:2107`–`:2116`), `Error Rate` (`:2117`–`:2127`), `Duration`
     (`:2128`–`:2138`).

   Neither knows about the other, so both can write a `dashboards/{svc}-dashboard-spec.yaml`
   for the same service (the emit path in `_apply_emit_red`, `affordance_map_consume.py:2154`,
   chooses one or the other per-call but there is no shared identity/dedup across the two writers).

The RED metric identities they *should* be keying on already live, typed, on **`MetricDescriptor`**
(`src/startd8/observability/metric_descriptor.py:38`): `throughput_metric` (`:66`),
`error_selector` (`:61`), `latency_bucket_metric` (`:68`). Critically, the profiles disagree on
throughput suffix: **four profiles use a `_total` throughput** — `span-metrics-connector`
`calls_total` (`:164`), `tempo-spanmetrics` `traces_spanmetrics_calls_total` (`:175`),
`harbor-core-http` `harbor_core_http_request_total` (`:217`), `harbor-jobservice-task`
`harbor_task_scheduled_total` (`:231`) — while the semconv/messaging profiles use histogram
`_count` (`:147`, `:154`, `:193`). Any classifier that keys on the `_count` substring is therefore
**structurally wrong for exactly those four profiles**.

### 1.2 The four bugs this drift caused (motivating evidence)

- **B1 — scorer widening silently broke generation.** Commit `5f6fe5f9` ("Credit Thanos
  AffordanceMap RED panels in OBS-200a scorer") widened the shared `has_rate_panel` to accept
  `_total` counters and titled panels (diff touched only the validator). Because
  `_ensure_red_coverage` calls that *same* `has_rate_panel` as its "do I already have a rate panel?"
  gate (`artifact_generator_generators.py:1019`), widening the scorer changed generation behavior:
  a panel the scorer now counts as Rate makes the generator believe rate coverage exists and it
  **stops synthesizing Request Rate**. One function serves two questions (score vs. generate), so a
  change made for scoring leaked into generation.

- **B2 — `_count`-only detection duplicates Request Rate for `_total`-throughput services.** The
  generator's fallback rate detector (`artifact_generator_generators.py:1024`) recognizes only
  `_count`. For the four `_total`-throughput profiles above, an *existing* descriptor-sourced
  Request Rate panel (whose expr contains `calls_total` / `..._total`) is **not** recognized by
  that `_count`-only gate, so a second Request Rate can be appended — a double-emit driven purely
  by the suffix guess disagreeing with the descriptor's real `throughput_metric`.

- **B3 — `has_duration_panel` disagrees with `_panel_is_red_protected`.** The scorer's
  `has_duration_panel` returns true on **any** `histogram_quantile` expr
  (`observability_artifact_checks.py:1326`). Shrink-protection requires `histogram_quantile`
  **AND** (`duration` OR `latency`) in the expr (`affordance_map_consume.py:1443`–`:1446`). A panel
  the scorer counts as Duration (a bare `histogram_quantile` with no "duration"/"latency" token)
  is therefore **not protected**, so shrink can drop a panel OBS-200a is still crediting — the RED
  coverage the two subsystems believe in diverges silently.

- **B4 — the generation gate is asymmetric.** In the inline fallback, rate detection is *narrow*
  (`_count`-only, `status` excluded — `:1024`) while error detection is *broad*
  (any `error`/`status_code` — `:1025`). The two legs of the same gate answer "present?" with
  different strictness, so a service can be judged to lack Rate but have Error (or vice-versa) for
  reasons unrelated to what it actually exposes.

**Root observation.** Two orthogonal axes are tangled into every copy:
- **(A) RED ROLE** of a panel: `{ RATE, ERROR, DURATION, NONE }`.
- **(B) the QUESTION** being asked: *covered?* (scoring — do we have ≥ the RED set), *present?*
  (generation — is THIS role already present, should I synthesize), *protected?* (shrink — would
  dropping this lose a RED role).

Every duplicate re-implements axis (A) inline in order to answer its one flavor of (B), and keys
axis (A) on name substrings instead of the descriptor's real metric identities.

---

## 2. Goals / Non-goals

### Goals
- **G1.** One canonical answer to "what RED role does this panel play?", keyed on the resolved
  `MetricDescriptor`'s **real** metric identities (`throughput_metric`, `error_selector`,
  `latency_bucket_metric`), not on `_count` / `_total` / `histogram_quantile` substring guessing.
- **G2.** Derive all three questions (covered? / present? / protected?) from that one role
  classification. **Per-tier consistency is the guarantee** (D5): the scorer and shrink both run the
  *descriptor-free* tier so they cannot disagree (FR-7 kills B3); the generator runs the
  *descriptor-grounded* tier. B1 is killed by **decoupling the shared function into two tiers of one
  classifier** — a scoring-tier change can no longer leak into the generation tier — not by forcing
  the broad and precise tiers to agree (they intentionally differ: coverage is broad, presence is
  precise).
- **G3.** One synthesizer that both the descriptor path and the locus path call, deduping by
  `(RedRole, metric_identity)` — structurally preventing the double-emit (kills B2 and the
  two-writers risk in §1.1.5).
- **G4.** Keep a title/expr-only fallback for panels with **no** descriptor context (the scorer and
  shrink run over arbitrary on-disk dashboards, including ones the SDK did not generate), so
  descriptor-free classification stays possible.

### Non-goals
- **NG1.** Do **not** change OBS-200a scoring **semantics** for correctly-classified panels. The
  coverage fraction and the `red >= 2.0/3.0` threshold (`observability_artifact_checks.py:323`) are
  preserved. This is behavior-preserving for correct cases; it only fixes the *disagreements*.
- **NG2.** Do **not** change the **byte output** of either synthesizer for the cases they handle
  correctly today (panel titles, exprs, units, groups, ordering, YAML shape). Existing golden
  fixtures must stay byte-identical where current behavior is correct.
- **NG3.** No new RED roles, no new descriptor axes, no change to the `MetricDescriptor` profile
  table (`metric_descriptor.py:142`–`:235`).
- **NG4.** *(Revised per D4.)* Not a change to *which families* `_pick_red_families` selects for a
  given locus set — its selection outcomes stay identical for existing fixtures (FR-8). But its
  name→role regexes (`_RED_RATE_RE`/`_RED_ERR_RE`/`_RED_DUR_*_RE`) **do move into `red_taxonomy`** as
  the canonical descriptor-free *name* classifier (so FR-13's "one file" guard holds without an
  exemption); `_pick_red_families` becomes a thin consumer of that classifier.

---

## 3. Proposed design

A single new module, `src/startd8/observability/red_taxonomy.py` (does **not** exist today —
verified), owning the RED-role vocabulary, one classifier, three derived question-helpers, and one
deduping synthesizer.

### 3.1 The role enum

```python
class RedRole(str, Enum):
    RATE = "rate"        # R — throughput
    ERROR = "error"      # E — errors / availability
    DURATION = "duration"  # D — latency / duration
    NONE = "none"        # not a RED panel
```

`RED_ROLES = frozenset({RedRole.RATE, RedRole.ERROR, RedRole.DURATION})` — the canonical triple,
the single source the coverage math keys on (mirrors the intent of
`metric_descriptor.BASE_RED_KINDS`, `:280`, which is the SLI-kind counterpart).

### 3.2 The one classifier

```python
def classify_red_role(
    panel: Mapping[str, Any],
    descriptor: MetricDescriptor | None = None,
) -> RedRole:
    ...
```

**Descriptor-grounded tier (preferred).** When `descriptor` is provided, classify by the
descriptor's *real* identities rather than substrings:
- **RATE** iff the panel expr references `descriptor.throughput_metric` **and** is not an error
  ratio (does not additionally carry `descriptor.error_selector`).
- **ERROR** iff the panel expr references `descriptor.error_selector` (or `throughput_metric`
  filtered by it — the error-ratio shape emitted at `artifact_generator_generators.py:1048`).
- **DURATION** iff the panel expr references `descriptor.latency_bucket_metric` (the
  `histogram_quantile(... _bucket ...)` shape). Descriptors whose `latency_bucket_metric` is empty
  (summary-latency subjects — `harbor-core-http` `:218`) yield DURATION only via the fallback
  title tier, never a false bucket match.
- else **NONE**.

This tier is correct for all four `_total`-throughput profiles by construction, because it reads
`throughput_metric` verbatim instead of guessing a suffix.

Both tiers read the panel's **full** expr set — `panel["expr"]` **and** `panel["targets"][].expr` —
via the existing `get_all_panel_exprs` semantics (D3); keying on `panel["expr"]` alone mis-classifies
target-based panels as NONE.

**Descriptor-free fallback tier (title/expr, for G4).** When `descriptor is None` (arbitrary
on-disk dashboards), fall back to the *union* of the today-correct title/expr heuristics **plus** the
migrated `_RED_*_RE` name rules (D4), so no currently-passing case regresses. This fallback is defined
**once** here and reused by every caller, replacing the divergent copies at
`observability_artifact_checks.py` (`has_*_panel`), `affordance_map_consume.py`
(`_panel_is_red_protected`), and the inline block in `_ensure_red_coverage`. *(Symbol names, not line
numbers — the draft's line refs run ~10 stale; see D9.)* The fallback resolves B3 with the **stricter**
DURATION rule everywhere — `histogram_quantile` **AND** (`duration`|`latency`) — which **OQ-2 resolves
and D1 proves costs zero golden coverage** (no golden carries a bare-`histogram_quantile` Duration
panel).

### 3.3 The three derived questions

All three are thin derivations over `classify_red_role`, so they cannot disagree:

```python
def red_roles_present(
    panels: Sequence[Mapping[str, Any]],
    descriptor: MetricDescriptor | None = None,
) -> frozenset[RedRole]:
    return frozenset(
        r for p in panels if (r := classify_red_role(p, descriptor)) is not RedRole.NONE
    )

# covered? (scoring)   — used by _compute_red_coverage / OBS-200a
def red_coverage(panels, descriptor=None) -> float:
    return len(red_roles_present(panels, descriptor) & RED_ROLES) / 3.0

# present? (generation) — used by _ensure_red_coverage's synth gate
def has_red_role(role: RedRole, panels, descriptor=None) -> bool:
    return role in red_roles_present(panels, descriptor)

# protected? (shrink)   — used by _panel_is_red_protected / _drop_priority
def is_red_protected(panel, descriptor=None) -> bool:
    return classify_red_role(panel, descriptor) is not RedRole.NONE
```

- **coverage** = `roles ⊇ each of {RATE, ERROR, DURATION}` (fraction thereof) — exactly OBS-200a's
  `_compute_red_coverage` math (`observability_artifact_checks.py:1335`).
- **presence** = `ROLE ∈ roles` — replaces the per-leg `has_rate`/`has_error` calls in the
  generator gate (`artifact_generator_generators.py:1019`–`:1020`) and the inline fallback
  (`:1023`–`:1025`), fixing B1/B4.
- **protection** = `role != NONE` — replaces `_panel_is_red_protected`
  (`affordance_map_consume.py:1426`) and is what `_drop_priority` (`:1474`) and `_red_coverage_ok`
  (`:1450`) call, fixing B3.

### 3.4 The one deduping synthesizer

```python
@dataclass(frozen=True)
class RedPanel:
    role: RedRole
    metric_identity: str   # per-role identity (D6): RATE→throughput_metric,
                           # ERROR→throughput_metric (the E leg rides the SAME series,
                           # discriminated by error_selector — the selector is NOT the identity),
                           # DURATION→latency_bucket_metric; or the locus family name (descriptor-free).
    title: str
    expr: str
    unit: str
    group: str

def synthesize_red_panels(
    existing: Sequence[Mapping[str, Any]],
    *,
    descriptor: MetricDescriptor | None,
    want_roles: frozenset[RedRole],
    locus_families: Mapping[RedRole, str] | None = None,
) -> list[RedPanel]:
    ...
```

- Emits at most one panel per `RedRole` in `want_roles`, **skipping any role already present** in
  `existing` (via `red_roles_present`).
- **Dedup key = `(RedRole, metric_identity)`** — two would-be panels with the same role and the same
  underlying metric identity collapse to one. This is the structural kill for B2 and the
  two-writers double-emit: whether the panel originates from the descriptor path
  (`_ensure_red_coverage`) or the locus path (`_locus_red_dashboard_yaml`), the identity is the
  same, so it cannot be written twice.
- Both existing synthesizers become thin adapters that build `want_roles` from their gate and call
  `synthesize_red_panels`:
  - `_ensure_red_coverage` supplies `descriptor` + `want_roles` from `sli_kinds`
    (`throughput`→RATE, `availability`→ERROR — `artifact_generator_generators.py:1032`–`:1033`) and
    keeps its `Availability (1h)` gauge as a *separate*, availability-kind artifact (it is not a
    RED-triple leg — `:1085`–`:1088`), so NG2 holds.
  - `_locus_red_dashboard_yaml` supplies `locus_families` from `_pick_red_families`
    (`affordance_map_consume.py:2103`) with `descriptor=None`.

---

## 4. Functional requirements

Each is independently testable.

- **FR-1.** A `RedRole` enum with exactly `{RATE, ERROR, DURATION, NONE}` and a `RED_ROLES`
  frozenset of the first three exists in `red_taxonomy.py`.
- **FR-2.** `classify_red_role(panel, descriptor)` returns RATE for a panel whose expr references
  `descriptor.throughput_metric` for **each** of the four `_total`-throughput profiles
  (`span-metrics-connector`, `tempo-spanmetrics`, `harbor-core-http`, `harbor-jobservice-task`) —
  proving it does not depend on a `_count` suffix. (Guards B2.)
- **FR-3.** `classify_red_role` returns ERROR (not RATE) for the error-ratio expr shape emitted at
  `artifact_generator_generators.py:1048` (throughput metric filtered by `error_selector`).
- **FR-4.** `classify_red_role` returns DURATION only for a `histogram_quantile` expr that also
  carries a duration/latency signal (descriptor `latency_bucket_metric` match, or the fallback
  duration rule); a bare `histogram_quantile` with no duration/latency token classifies
  **identically** for the scorer and the shrink path. (Guards B3.)
- **FR-5.** `red_coverage(panels)` (descriptor-free) returns the **same fraction** as the current
  `_compute_red_coverage` (`observability_artifact_checks.py:1335`) for a corpus of existing OBS-200a
  golden dashboards. (Enforces NG1.)
- **FR-6.** `has_red_role(RATE, panels, descriptor)` is **true** when a descriptor-sourced Request
  Rate panel is present, so `_ensure_red_coverage` does not re-synthesize it — for all four
  `_total`-throughput profiles. (Guards B2/B1.)
- **FR-7.** `is_red_protected(panel)` returns true for **exactly** the set of panels that
  `red_coverage` counts toward RED, i.e. `is_red_protected(p) == (classify_red_role(p) != NONE)`
  for all `p`. A property test asserts no panel is scored-but-unprotected. (Guards B3.)
- **FR-8.** *(Revised per D2/D4.)* `_pick_red_families` keeps its `Tuple[Optional[str], ...]`
  signature (other callers depend on it) but (a) sources its rate/error/duration **name** rules from
  `red_taxonomy` (the migrated `_RED_*_RE`), and (b) gains a thin `tuple → Mapping[RedRole, str]`
  adapter so the locus synthesizer speaks the `RedRole` vocabulary. Its selected families are
  **byte-unchanged** for existing fixtures (parity test).
- **FR-9.** `synthesize_red_panels` emits **at most one** panel per `RedRole` and **zero** for a
  role already present in `existing`.
- **FR-10.** Calling `synthesize_red_panels` twice for the same service+descriptor (simulating the
  descriptor path and the locus path both firing) yields **no duplicate** `(RedRole,
  metric_identity)` panel. (Guards B2 / two-writers.)
- **FR-11.** For inputs where today's behavior is correct, `_ensure_red_coverage` and
  `_locus_red_dashboard_yaml` produce **byte-identical** output (panel titles/exprs/units/groups,
  ordering, YAML) after migration. (Enforces NG2 — parity-guarded.)
- **FR-12.** The three exported scorer symbols `has_rate_panel` / `has_error_panel` /
  `has_duration_panel` (`observability_artifact_checks.py:44`–`:46`) either remain as thin
  `red_taxonomy`-backed shims (preserving `__all__` and external importers, per the SDK "don't
  modify `__all__` without updating tests" rule) **or** are removed with all call sites migrated —
  the choice is recorded in Open Questions OQ-1.
- **FR-13.** *(Reconciled with NG4 per D4.)* No module outside `red_taxonomy.py` re-implements RED
  role classification — substring **or regex** (`_count`/`_total`/`histogram_quantile` **and** the
  `_RED_*_RE` name rules). A grep guard asserts this logic lives in exactly one file after migration;
  because the `_RED_*_RE` regexes move into `red_taxonomy` (not exempted), the guard needs **no
  carve-out** for `_pick_red_families`.

---

## 5. Migration plan

Each step is behavior-preserving and lands behind a **parity guard** (a test asserting the old and
new predicates return identical results over the existing golden corpus before the old copy is
deleted).

1. **Introduce the module.** Add `red_taxonomy.py` with `RedRole`, `classify_red_role` (both tiers),
   the three derived questions, and `synthesize_red_panels`. No call sites change yet. Ship its own
   unit tests (FR-1..FR-4, FR-9, FR-10). *Guard:* new tests only; zero behavior change elsewhere.

2. **Migrate the scorer.** Re-express `has_rate_panel`/`has_error_panel`/`has_duration_panel` and
   `_compute_red_coverage` (`observability_artifact_checks.py:1266`–`:1344`) as thin wrappers over
   `red_taxonomy` (descriptor-free tier). *Guard:* FR-5 parity test over the OBS-200a golden
   dashboards — coverage fraction and OBS-200a verdict byte-identical.

3. **Migrate the generator gate + synthesizer.** Replace the `has_rate_panel`/`has_error_panel`
   calls and the inline fallback (`artifact_generator_generators.py:1015`–`:1025`) with
   `has_red_role`, and route panel emission (`:1055`–`:1083`) through `synthesize_red_panels`
   (descriptor tier). Keep the `Availability (1h)` gauge (`:1105`) as its own path. *Guard:* FR-6,
   FR-11 byte-parity on generated `dashboard-spec.yaml` goldens; FR-2 across the four `_total`
   profiles.

4. **Migrate shrink / AffordanceMap.** Replace `_panel_is_red_protected`
   (`affordance_map_consume.py:1426`) with `is_red_protected`, point `_red_coverage_ok` (`:1450`)
   and `_drop_priority` (`:1474`) at it, and route `_locus_red_dashboard_yaml` (`:2098`) through
   `synthesize_red_panels` with `_pick_red_families` (FR-8) feeding `locus_families`. *Guard:* FR-7
   scored-⟺-protected property test; FR-11 byte-parity on `_locus_red_dashboard_yaml` output; the
   existing shrink refusal-ladder tests stay green.

5. **Delete the duplicates + add the drift guard.** Remove any now-dead inline heuristics; add the
   FR-13 grep guard so a future copy cannot silently reappear. Resolve OQ-1 (shim vs. remove) and
   update the `__all__` / logger-acquisition-policy test allowlists for the new module per the SDK
   "Must Do" rules.

---

## 6. Risks

- **R1 — the `_count` / `_total` identity edge.** The whole point is that four profiles use
  `_total`. If `classify_red_role`'s descriptor tier is subtly still substring-biased (e.g. matches
  `throughput_metric` by suffix instead of by the full name), it re-opens B2. Mitigation: match the
  **full** `throughput_metric` string; FR-2 tests all four profiles explicitly.
- **R2 — name-scoped Harbor selectors.** `harbor-core-http` and `harbor-jobservice-task` set
  `service_label_key=""` (`metric_descriptor.py:215`, `:229`) — the component is in the metric
  *name*, not a label, so `descriptor.selector(...)` yields no identity matcher
  (`metric_descriptor.py:105`–`:108`). The classifier must key on `throughput_metric` /
  `latency_bucket_metric` names, not on the presence of a `{service=...}` selector, or it
  mis-classifies name-scoped panels as NONE. Also: `harbor-core-http.latency_bucket_metric` is
  empty (`:218`, a summary not a histogram) — DURATION for it can only come from the title fallback,
  never a bucket match (FR-4 must not false-negative here).
- **R3 — byte-parity of existing goldens (NG2).** The union-fallback in the descriptor-free tier
  must be a true superset of each old copy's accept set, or a currently-passing OBS-200a golden
  flips. Mitigation: FR-5/FR-11 parity tests over the full golden corpus are the gate for steps 2–4;
  no old copy is deleted until its parity test is green.
- **R4 — the two DURATION rules were genuinely different (B3).** *(Downgraded per D1.)* The scorer
  accepted bare `histogram_quantile`; shrink required a duration/latency token. Unifying picks the
  **stricter** rule (OQ-2). **D1 proves no existing golden carries a bare-`histogram_quantile`
  Duration panel**, so this changes classification for **zero** panels in the corpus — the parity
  guard (FR-5/FR-11) stays green without an exception. The FR-4 test still *asserts* the unified rule
  so a future such panel is handled consistently, not silently.

---

## 7. Open questions

- **OQ-1 — RESOLVED (keep shims).** `has_rate_panel`/`has_error_panel`/`has_duration_panel` stay as
  public `red_taxonomy`-backed shims (external importers exist; they are in `__all__`) — lower blast
  radius, honors the `__all__` rule.
- **OQ-2 — RESOLVED (stricter).** The unified DURATION rule is `histogram_quantile` **AND**
  (`duration`|`latency`) everywhere. D1 quantified it against the golden corpus: **zero** panels
  affected, so no coverage regression. (See R4.)
- **OQ-3 — OPEN (defer).** Should `is_red_protected` accept a `descriptor` in the shrink path? Shrink
  runs descriptor-free (`_panel_is_red_protected` takes only a panel). Threading the resolved
  descriptor through `shrink_dashboard_lines` (`affordance_map_consume.py:~1502`) would make
  protection descriptor-grounded, but FR-7's scored-⟺-protected invariant already holds *within* the
  descriptor-free tier (D5), so this is not required for correctness. Defer unless a bug demands it.
- **OQ-4 — RESOLVED (metric name suffices).** Per D6, `RedPanel.metric_identity` is the per-role
  metric **name**, not the label selector; today's dashboards are single-service-per-spec
  (`_apply_emit_red` scopes per service), so the name is a sufficient dedup key. Re-open only if
  multi-service-per-dashboard specs land.

---

*v0.3.1 — Post reflective-loop hardening. Planning pass corrected 9 assumptions (2 load-bearing: D1
theoretical-not-actual B3 tension; D4 FR-13⟺NG4 contradiction), resolved OQ-1/2/4, refined G2, and
re-anchored guards on symbols not line numbers. 3 lessons + 3 principles applied. Ready for CRP review.*
