# RED Panel Classification Unification — Requirements

**Status:** Draft (spec only — no implementation)
**Date:** 2026-08-04
**Owner:** observability
**Scope:** `src/startd8/observability/`, `src/startd8/validators/observability_artifact_checks.py`
**Related:** OBS-200a RED scorer; AffordanceMap consume (WP-B2/FR-B4 shrink); `MetricDescriptor` (`REQ_TARGET_METRIC_BINDING.md`, #226 FR-12/FR-13)

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
  classification, so they can no longer disagree (kills B1, B3, B4 by construction).
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
- **NG4.** Not a rewrite of the locus family picker's regex heuristics (`_pick_red_families`); those
  remain the descriptor-free path but are re-expressed as producing a `RedRole` so they share the
  vocabulary (see FR-8).

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

**Descriptor-free fallback tier (title/expr, for G4).** When `descriptor is None` (arbitrary
on-disk dashboards), fall back to the *union* of the today-correct title/expr heuristics, so no
currently-passing case regresses. This fallback is defined **once** here and reused by every caller,
replacing the divergent copies at `observability_artifact_checks.py:1266/1294/1316`,
`affordance_map_consume.py:1426`, and the inline block at `artifact_generator_generators.py:1023`.
The fallback must resolve B3 by making DURATION require `histogram_quantile` **with** a
duration/latency signal *consistently* across scorer and shrink (choose one rule, apply everywhere).

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
    metric_identity: str   # descriptor.throughput_metric | error_selector | latency_bucket_metric,
                           # or the locus family name on the descriptor-free path
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
- **FR-8.** `_pick_red_families` is re-expressed to return a `Mapping[RedRole, str]` (or is wrapped
  by an adapter that does), so the locus path speaks the same `RedRole` vocabulary; its selected
  families are unchanged for existing fixtures. (Enforces NG4.)
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
- **FR-13.** No module outside `red_taxonomy.py` re-implements RED substring classification: a grep
  guard asserts `_count`/`_total`/`histogram_quantile`-based RED role logic exists in exactly one
  file after migration.

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
- **R4 — the two DURATION rules were genuinely different (B3), so "preserve behavior" is
  ambiguous.** The scorer accepted bare `histogram_quantile`; shrink required a duration/latency
  token. Unifying them **must change one of the two** — this is the one place the refactor is
  intentionally *not* byte-preserving. OQ-2 records which rule wins and why; the change is scoped to
  the disagreeing panels only.

---

## 7. Open questions

- **OQ-1.** Keep `has_rate_panel`/`has_error_panel`/`has_duration_panel` as public
  `red_taxonomy`-backed shims (external importers exist; they are in `__all__`), or remove and
  migrate all callers? Default: **keep as shims** (lower blast radius, honors the `__all__` rule).
- **OQ-2.** For the unified DURATION rule (R4/B3): adopt the **stricter** shrink rule
  (`histogram_quantile` **AND** duration/latency) everywhere, or the **looser** scorer rule
  (bare `histogram_quantile`)? Stricter is safer (a bare `histogram_quantile` on a non-latency
  metric is not really Duration), but it may lower coverage on some existing dashboards — quantify
  against the golden corpus before deciding.
- **OQ-3.** Should `is_red_protected` accept a `descriptor` in the shrink path? Shrink currently runs
  descriptor-free (`_panel_is_red_protected` takes only a panel). Threading the resolved descriptor
  through shrink would make protection descriptor-grounded too (closing the last substring gap), but
  requires plumbing the descriptor into `shrink_dashboard_lines`
  (`affordance_map_consume.py:1493`). Defer unless a bug demands it.
- **OQ-4.** Does the `RedPanel.metric_identity` dedup key need to include the label selector (two
  Request-Rate panels for the same metric but different `{service=...}` selectors)? For single-service
  dashboards the metric name suffices; for multi-service dashboards it may not. Confirm against how
  `_apply_emit_red` (`affordance_map_consume.py:2154`) scopes per service.
