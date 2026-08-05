# NEXT STEPS — EC-2: A "Summary-Latency" Descriptor Mode

**Status:** proposed · **Effort:** M–L · **Owner axis:** `observability/metric_descriptor` + 3 consumers
**Grounds:** all file:line references are against `startd8-sdk` `main` (this session's shipped code).

> **One line:** bind the RED **Duration (D)** leg to a Prometheus **SUMMARY**'s
> `{quantile="0.99"}` child series instead of leaving Duration cleanly-absent when a subject
> has no histogram `_bucket`. This is the SDK-side *fix* for the Harbor Duration gap that this
> session's TF-1 (`_red_gap_reasons`) currently only *explains* — and it directly raises the
> ContextCore Harbor pilot's `metric_cov`.

---

## 1. Problem & value

Harbor's `core` component exposes real request-latency data, but as a Prometheus **Summary**
(`harbor_core_http_request_duration_seconds` with a `quantile` label, **no `_bucket`**), not a
histogram. Every descriptor-RED seam in the SDK assumes latency == a histogram `_bucket`:

- The **profile** `harbor-core-http` sets `latency_bucket_metric=""` on purpose
  (`metric_descriptor.py:218`) — "summary, not histogram — no bucket to bind".
- `classify_red_role`'s DURATION rule keys on `latency_bucket_metric`; empty ⇒ never bound via
  the descriptor tier (`red_taxonomy.py:158-166`, `195`).
- `canonical_red_exprs` **omits** DURATION when `latency_bucket_metric` is empty
  (`convention.py:52-55`).
- The validator's gap note calls this leg "**latency is a summary (no histogram bucket to
  bind)**" (`observability_artifact_checks.py:227-228`).

Net effect: for Harbor `core` (and any summary-latency subject) the SDK emits **no Duration
panel and no Duration SLI**, so RED coverage is capped at 2/3 for a subject that legitimately
has p99 data. That under-counts the pilot's `metric_cov`.

**Value:** real Duration observability (a working p99 panel/SLI) for summary-latency subjects,
turning a "legitimately unbindable" gap into a bound leg → the Harbor pilot RED coverage rises
from 2/3 to 3/3 on `core`, and any Prometheus-classic summary service benefits identically.

**The live series (grounded):** `harbor_core_http_request_duration_seconds{quantile="0.99"}`
— the real child series from the full-topology run 2026-08-03 (goharbor/harbor v2.15.2),
per the `harbor-core-http` profile comment (`metric_descriptor.py:204-212`).

---

## 2. Grounded current state

### The histogram-only assumption, in three consumers + one profile

| Seam | file:line | Histogram-only behaviour today |
|---|---|---|
| Profile | `metric_descriptor.py:213-220` (`harbor-core-http`), `227-234` (`harbor-jobservice-task`) | both set `latency_bucket_metric=""` (the only two empty-bucket profiles — confirmed by grep) |
| Classify | `red_taxonomy.py:158-166` `_grounded_is_duration` | binds D iff an expr references the (non-empty) `latency_bucket_metric`; empty lb ⇒ title-only, no synthesis identity |
| Convention | `convention.py:52-55` | `out[RedRole.DURATION] = histogram_quantile(0.99, rate(<lb>[...]))` only `if lb:` |
| Generator (panel) | `artifact_generator_generators.py:546-552, 588-611` | `latency_base = descriptor.latency_bucket_metric`; the `_INSTRUMENT_TO_QUERY["histogram"]` template is `histogram_quantile(0.99, rate({metric}_bucket{selector}[…]))` (`96-100`); p50/p95 also `_bucket` |
| Generator (RED backfill) | `artifact_generator_generators.py:991-1139` `_ensure_red_coverage` | synthesizes **Rate / Error / Availability** only — it has **no Duration branch at all**; Duration is expected to come from the histogram panel path above |
| Validator (gap note) | `observability_artifact_checks.py:227-228` | says D is "a summary (no histogram bucket to bind)" — i.e. *not bindable* |

### The half that already exists (leverage, don't rebuild)

The **declared-functional-series** path *already* knows how to bind a summary p99 — but it is a
**separate code path** from the descriptor RED path:

- `_resolve_declared_shape` maps a declared `type: summary` covering `latency` to the shape
  `"summary_quantile"` (`artifact_generator_generators.py:1229-1244`).
- `_functional_sli_query` renders `"summary_quantile"` to `<metric>{quantile="0.99", <selectors>}`
  — merging the quantile matcher **into** the existing selector braces, "**NOT a `_bucket`
  (which a Summary lacks)**" (`artifact_generator_generators.py:1979-1988`).

**This is the exact expr shape EC-2 needs** — it is already grounded and tested for the
functional path. EC-2's job is to give the **descriptor RED path** the same capability, via a
descriptor *identity* (not a re-derived shape), so `harbor-core-http`'s D leg binds through
`classify_red_role` / `canonical_red_exprs` / `_ensure_red_coverage` the same way Rate/Error do.

---

## 3. Proposed design

### 3.1 A new descriptor axis (identities, not substrings)

Respect this session's **identities-not-substrings** principle (`red_taxonomy.py:13-23`): add a
real identity to `MetricDescriptor`, don't sniff `_bucket`-absence.

```python
# metric_descriptor.py — new axis 3b
#: Prometheus SUMMARY series exposing latency as a `{quantile}` child series
#: (NO `_bucket`). Mutually-alternative to `latency_bucket_metric`: a descriptor
#: has AT MOST one latency identity. Empty ⇒ no summary-latency (byte-parity).
latency_summary_metric: str = ""
#: Label key on the summary carrying the quantile (Prometheus canonical = "quantile").
latency_quantile_label: str = "quantile"
```

`harbor-core-http` then becomes (the *only* profile edit for the core case):

```python
latency_bucket_metric="",                                        # unchanged
latency_summary_metric="harbor_core_http_request_duration_seconds",  # NEW — binds D
# latency_quantile_label defaults to "quantile"
```

**Invariant (assert in a drift test):** a descriptor sets at most one of
`latency_bucket_metric` / `latency_summary_metric`. This keeps `classify_red_role`'s
DURATION-single-role and the panel path unambiguous.

**Precedence / overrides:** both new fields fall out of `_OVERRIDABLE_AXES` automatically —
that set is derived from `fields(MetricDescriptor)` (`metric_descriptor.py:480-482`), so
ContextCore's FR-7 override ladder (`resolve_descriptor`, `485-539`) picks them up with **zero
extra code**. A manifest can thus override `latency_summary_metric` per-target.

### 3.2 A helper so the four seams agree on ONE expr shape

To avoid a fourth divergent copy of the summary shape, add a single canonical builder next to
the existing `summary_quantile` renderer, and have both the functional path and the new
descriptor path call it:

```python
# reuse the shape already proven at _functional_sli_query:1979-1988
def summary_quantile_expr(metric: str, selector: str, *,
                          quantile: float = 0.99, label: str = "quantile") -> str:
    q = f'{label}="{quantile}"'
    if selector.startswith("{") and selector.endswith("}") and len(selector) > 2:
        return f'{metric}{{{q},{selector[1:]}'   # merge into existing braces
    return f'{metric}{{{q}}}'
```

### 3.3 Each consumer gains a summary branch (additive)

**`convention.py::canonical_red_exprs`** (`52-55`) — add an `elif` *after* the histogram branch:

```python
if lb:
    out[RedRole.DURATION] = f"histogram_quantile(0.99, rate({lb}{total}[{rate_window}]))"
elif sm := getattr(descriptor, "latency_summary_metric", "") or "":
    label = getattr(descriptor, "latency_quantile_label", "") or "quantile"
    out[RedRole.DURATION] = summary_quantile_expr(sm, total, quantile=descriptor.quantile, label=label)
# else: still omitted (true no-latency subject — e.g. harbor-jobservice-task)
```

**`red_taxonomy.py::_grounded_is_duration`** (`158-166`) — the DURATION identity becomes
"references `latency_bucket_metric` **or** `latency_summary_metric`". Pass the summary identity
through `_role_membership` (`195`) so the descriptor tier binds D on a summary expr. Keep the
FR-4a null-safety: empty summary identity ⇒ still title-only, no false `"" in expr` match.

**`artifact_generator_generators.py`** — two touch points:
1. In `_ensure_red_coverage` (`991-1139`), add a Duration backfill branch **when
   `latency_summary_metric` is set and D is not already present** (gated on `"latency" in
   sli_kinds`, mirroring `want_rate`/`want_error` at `1033-1034`), emitting a `timeseries`
   panel with `summary_quantile_expr(...)`, `unit = descriptor.latency_unit`, group
   `"Latency"`, and a `DerivationTrace(tier="descriptor", source="descriptor.latency_summary_metric")`.
2. In the main `generate_dashboard` metric loop (`562-611`), a metric of `type == "summary"`
   whose name contains `duration` renders via `summary_quantile_expr` instead of the histogram
   template (which appends `_bucket`). (Only needed if the subject *declares* a summary
   convention_metric; the `_ensure_red_coverage` backfill covers the profile-only case.)

The expr EC-2 emits for Harbor core:
`harbor_core_http_request_duration_seconds{quantile="0.99"}` (name-scoped ⇒ empty base selector,
so no service matcher merged — see §4).

---

## 4. The subtle bits

- **Summary exposes `_sum`/`_count` too.** A Summary also publishes `_sum` and `_count`, so a
  computed **avg** `rate(<m>_sum[w]) / rate(<m>_count[w])` is *always* available even when no
  `{quantile}` objectives are configured — the documented always-valid fallback already noted
  at `artifact_generator_generators.py:1233-1235`. But when objectives ARE configured
  (Harbor's are — the live `{quantile="0.99"}` series exists), the child series gives p99
  **directly**, which is the RED Duration leg. **Recommendation:** bind p99 from `{quantile}`
  as the primary D leg; treat avg-from-`_sum/_count` as an optional secondary (see §6, OQ-3).

- **Name-scoped Harbor (`service_label_key=""`).** `harbor-core-http` has no service label
  (`metric_descriptor.py:215`), so `descriptor.selector("core")` returns `"{}"`
  (`service_matcher` → empty, `selector` drops empty parts, `metric_descriptor.py:94-123`).
  `summary_quantile_expr` must therefore handle the **empty-selector** case: `len(selector) > 2`
  is False for `"{}"`, so it falls to the `{quantile="0.99"}`-only branch — correct, and already
  the behaviour of the existing `_functional_sli_query` renderer (`1983-1986`). No stray comma,
  no phantom `service="core"` matcher that would select nothing.

- **EC-201-style validator awareness.** `_repair_bucket_suffix` (`observability_artifact_checks.py:197-210`)
  and the OBS-203c check (`1140-1151`) **auto-append `_bucket`** to any
  `histogram_quantile(rate(<m>{…}))`. A summary p99 expr is NOT a `histogram_quantile`, so it
  is *not* matched by that regex — good, no false repair. But confirm no *other* check flags a
  bare `<m>{quantile="…"}` as "missing rate()". Add a positive test that a summary D expr
  passes `validate_dashboard` untouched (no repair, no OBS-203 issue).

---

## 5. Byte-parity + test strategy

**MUST be additive.** The two new fields default to empty/`"quantile"`, so:

- Every existing profile (semconv-http/grpc, span-metrics, tempo-spanmetrics, messaging-semconv,
  and **harbor-jobservice-task** — which has *no* latency at all) has
  `latency_summary_metric=""` ⇒ the `elif` branches never fire ⇒ **byte-identical** output. The
  histogram path (`lb:`) is completely unchanged.
- `harbor-jobservice-task` stays Duration-absent (correct — its latency is *gauges*, not a
  summary; `metric_descriptor.py:221-234`).

**Tests to add:**
1. **Parity guard:** for every profile with `latency_summary_metric==""`, assert
   `canonical_red_exprs` output is byte-identical to `main` (snapshot). The semconv fixtures are
   the guard.
2. **Harbor D now binds:** `canonical_red_exprs(profile_for("harbor-core-http"), "core")`
   contains `RedRole.DURATION == 'harbor_core_http_request_duration_seconds{quantile="0.99"}'`.
3. **classify:** a panel carrying that expr classifies as `RedRole.DURATION` under the
   `harbor-core-http` descriptor (`classify_red_role`), and `red_coverage` on the Harbor
   dashboard is now `1.0`.
4. **Generator:** `_ensure_red_coverage` emits a Latency panel for a summary-latency service
   with `"latency" ∈ sli_kinds`; emits **nothing** for `harbor-jobservice-task`.
5. **Invariant:** drift test — no profile sets both latency identities.
6. **Validator message flip (this is a REQUIRED edit):** update
   `_red_gap_reasons` (`observability_artifact_checks.py:227-228`) so the "latency is a summary
   (no histogram bucket to bind)" note fires **only when neither** `latency_bucket_metric` **nor**
   `latency_summary_metric` is set. When a summary IS bindable, D is no longer in `missing`, so
   the note must not appear. Test both branches.
7. **Validator no-op:** a summary D expr survives `validate_dashboard(autofix=True)` unchanged
   (§4 EC-201 awareness).

---

## 6. Risks / open questions

- **OQ-1 — summary p99 trustworthiness (HONEST product caveat, not a bug).** Prometheus Summary
  quantiles are **client-computed per-instance** and are **NOT aggregatable across
  instances/replicas** — you cannot average or sum `{quantile="0.99"}` across pods and get a
  meaningful p99. For single-instance Harbor `core` this is fine; for a replicated summary
  service the p99 panel is *per-instance* and should be labelled as such (or the avg-from-
  `_sum/_count` used for a fleet view). **Surface this in the DerivationTrace / panel
  description**, don't hide it. This is the one genuine product honesty item.
- **OQ-2 — default quantile.** Default to `0.99` (matches `descriptor.quantile`,
  `metric_descriptor.py:78`, and the histogram D leg). A subject whose summary only defines
  `{quantile="0.95"}` needs the label value overridable — `descriptor.quantile` already carries
  it; confirm the summary child series for that quantile actually exists (config data gap, per
  `1233-1235`).
- **OQ-3 — also emit avg-latency from `_sum/_count`?** Optional secondary panel; always-valid,
  aggregatable, complements the per-instance p99. Recommend **defer to a follow-up** (keep EC-2
  focused on the D-leg binding); note it so it isn't lost.
- **OQ-4 — p50/p95 companions.** The histogram path emits p50/p95 panels
  (`artifact_generator_generators.py:603-611`). A summary can too *iff* those quantile
  objectives are configured — but they often aren't. Emit them only if the child series is known
  to exist; otherwise skip (don't emit a dead `{quantile="0.5"}` panel). Defer.

---

## 7. Effort (M–L) + recommended process

**Effort: M–L.** The expr shape is already built and tested (`summary_quantile` at
`1979-1988`), which de-risks the core. The work is (a) one new descriptor axis + profile edit,
(b) a summary `elif` in three consumers, (c) one validator-message flip, (d) the parity/adversarial
test suite. L-ward pressure comes from the cross-consumer surface (touches the descriptor model +
its 3 RED consumers + the validator — the same arc as this session's name-scoped-identity work)
and the byte-parity guarantee.

**Recommended process (mirrors this session's arc):**
1. **`/reflective-requirements`** — this touches the descriptor *model* + 3 consumers + a
   validator; draft FRs (FR: new axis; FR: canonical expr; FR: classify; FR: generator backfill;
   FR: validator flip; FR: byte-parity) and let the planning pass surface the name-scoped /
   empty-selector edge before coding.
2. **CRP (`/new-cnvrg-rvw-prmpt`)** on the reqs — the identities-not-substrings and
   at-most-one-latency-identity invariants are exactly the kind of cross-consumer contract CRP
   catches drifting.
3. **Byte-parity gate** in CI: snapshot `canonical_red_exprs` for all non-summary profiles;
   any diff fails.
4. **Adversarial fixtures:** name-scoped empty selector (`{}`), a summary with a non-default
   quantile label, a replicated-summary case (assert the per-instance caveat is present), and a
   profile that (wrongly) sets both latency identities (assert the drift test fires).

---

### Appendix — grounding index (file:line)

- Empty-bucket profiles: `metric_descriptor.py:213-220` (harbor-core-http), `227-234` (harbor-jobservice-task); grep confirms these are the **only** two.
- Real summary series named in-profile: `metric_descriptor.py:204-212`.
- Override ladder auto-picks new fields: `metric_descriptor.py:480-482`, `485-539`.
- DURATION classify rule: `red_taxonomy.py:158-166`, `195`.
- DURATION expr omission: `convention.py:52-55`.
- Histogram query template: `artifact_generator_generators.py:96-100`; panel loop `546-611`.
- RED backfill (no Duration branch today): `artifact_generator_generators.py:991-1139`.
- **Existing** summary_quantile shape (leverage): `_resolve_declared_shape` `1229-1244`; `_functional_sli_query` `1979-1988`.
- Validator gap note to flip: `observability_artifact_checks.py:218-233` (note at `227-228`).
- EC-201 bucket-repair (must not false-fire): `observability_artifact_checks.py:197-210`, OBS-203c `1140-1151`.
