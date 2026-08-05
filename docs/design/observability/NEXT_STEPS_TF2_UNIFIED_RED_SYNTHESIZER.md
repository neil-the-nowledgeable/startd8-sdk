# NEXT STEPS — TF-2: Route Both RED-Panel Synthesizers Through `synthesize_red_panels`

**Status:** Scoped / not started
**Depends on:** `RED_TAXONOMY_UNIFICATION_REQUIREMENTS.md` v0.4 (§3.4 synthesizer, §4 FR-8/FR-9/FR-10/FR-10a/FR-11, §5 migration step 4)
**Effort:** M (see §7)
**Date:** 2026-08-05

> All file:line references were read against the working tree on branch `docs/red-next-steps`
> (a checkout of the just-shipped red_taxonomy unification). Line numbers may drift ~a few lines
> as edits land; symbols are stable.

---

## 1. Problem & Value

The red_taxonomy unification shipped a **single, deduping RED-panel synthesizer** —
`synthesize_red_panels(...)` in `src/startd8/observability/red_taxonomy.py:300` — whose dedup key is
`(RedRole, metric_identity)` (`red_taxonomy.py:321`). It was landed with its own unit tests
(`tests/unit/observability/test_red_taxonomy.py::test_fr9_*`, `::test_fr10_dedup_by_role_and_identity`)
**but no production call site**.

**Verified: `synthesize_red_panels` has ZERO callers outside its own module.**
`grep -rn synthesize_red_panels src/` returns exactly one hit — the definition at
`red_taxonomy.py:300`. It is dead code today.

Meanwhile the two RED-panel synthesizers it was built to unify are both still live and independent:

1. **Descriptor path** — `_ensure_red_coverage` (`artifact_generator_generators.py:991`) appends
   `Request Rate` / `Error Rate` / `Availability (1h)` panels **inline** (`panels.append(...)` at
   `:1060`, `:1093`, `:1121`).
2. **Locus path** — `_locus_red_dashboard_yaml` (`affordance_map_consume.py:2098`) synthesizes
   `Request Rate` / `Error Rate` / `Duration` panels inline from cited loci (`panels.append(...)` at
   `:2107`, `:2118`, `:2129`).

And the seam where those two paths' outputs meet — `_apply_affordance_red_bind_panels`
(`artifact_generator.py:1195`) — dedups the locus panels against the already-generated (descriptor)
panels **by normalized metric-family NAME** (`artifact_generator.py:1330`:
`if _normalize_metric_name(fam) in already_named: continue`), NOT by the structural
`(RedRole, metric_identity)` key.

**What the unwiring costs:**

- **Dead code.** The one artifact the unification exists to deliver — a *structural* two-writer
  dedup — is unreachable. The dedup story is currently carried by a NAME-string comparison that the
  spec itself flagged as fragile.
- **The latent duplicate-panel risk (R1-F4).** Because the two writers derive `metric_identity` from
  *different sources* (descriptor metric name vs locus family name), a descriptor-path RATE keyed on
  `calls_total` and a locus-path RATE keyed on `calls` can carry **different** identity strings and
  escape the name-based dedup at `artifact_generator.py:1330` → a **duplicate RED panel** on one
  dashboard. This was raised as CRP finding **R1-F4** and is, per the spec's own triage, an
  **unverified hypothesis** — reachability is an open question (§6).

**End-user value of closing it:**

- One RED panel per role per dashboard, *guaranteed by construction* rather than by a name string
  that can drift — no operator ever sees two "Request Rate" panels on the same service dashboard.
- The name→role classification and the panel-emission dedup collapse to one authority
  (`red_taxonomy`), so a future edit to metric naming cannot silently re-open the double-emit
  (the FR-13 grep guard already enforces "one file" for classification; TF-2 extends that to
  emission).

---

## 2. Grounded Current State

### 2.1 Synthesizer #1 — descriptor path (inline)

`_ensure_red_coverage(panels, service, business, derivations, descriptor)`
— `artifact_generator_generators.py:991`, invoked from `:620`.

- Gate (`:1033`–`:1036`): `want_rate = "throughput" in sli_kinds`,
  `want_error = "availability" in sli_kinds`; no-op if neither.
- "Already present?" via the unified classifier: `has_red_role(RedRole.RATE, panels, descriptor)`
  (`:1025`) / `RedRole.ERROR` (`:1026`).
- Emits **inline**:
  - `Request Rate` — `panels.append({... "title": "Request Rate", "expr": rate_expr,
    "unit": "reqps", "group": "Throughput"})` (`:1060`).
  - `Error Rate` — `error_panel` with optional error-budget thresholds (`:1075`–`:1093`).
  - `Availability (1h)` gauge — `:1121`. **This is an availability-kind artifact, NOT a RED-triple
    leg** (`:1101`–`:1104`); it stays out of `synthesize_red_panels` per NG2 / spec §3.4.
- Exprs come from `canonical_red_exprs(descriptor, service.service_id)` (`:1049`–`:1057`), keyed by
  `RedRole`, with an inline fallback for a degenerate descriptor.

### 2.2 Synthesizer #2 — locus path (inline)

`_locus_red_dashboard_yaml(service_id, loci)` — `affordance_map_consume.py:2098`.

- Family pick: `rate, err, dur = _pick_red_families(loci)` (`:2103`; picker at `:414`).
- Emits **inline** (only for populated slots, in rate→err→dur order):
  - `Request Rate` — `sum(rate({rate}[$__rate_interval]))`, `group: "Throughput"` (`:2107`).
  - `Error Rate` — `sum(rate({err}[$__rate_interval]))`, `group: "Errors"` (`:2118`).
  - `Duration` — `_duration_panel_expr(dur)`, `group: "Latency"` (`:2129`).
- `used.append(...)` (`:2116`/`:2127`/`:2138`) tracks the families in lockstep with the panels →
  serialized as `spec.locus_families` (`:2148`). This positional lockstep is load-bearing for the
  dedup (§2.3).

### 2.3 The family-name dedup (where the two writers meet)

`_apply_affordance_red_bind_panels(artifacts, services, affordance_map)`
— `artifact_generator.py:1195`, called from `:1847`.

- Re-runs `_locus_red_dashboard_yaml` (`:1289`) to get `red_panels` + `red_families` (`:1295`/`:1296`).
- Extracts the metric names already referenced by the in-memory (descriptor-generated) dashboard:
  `already_named = extract_referenced_metrics(existing)` (`:1317`).
- **Dedup, per candidate panel** (`:1326`–`:1334`):
  ```python
  for panel, fam in zip(red_panels, red_families):
      expr = str(panel.get("expr", ""))
      if expr in existing:                                  # 1: exact-expr match
          continue
      if _normalize_metric_name(fam) in already_named:      # 2: normalized-NAME match
          continue
      added_panels.append({**panel, "group": _RED_BIND_GROUP_PREFIX})
  ```
- `_normalize_metric_name` (`observability_artifact_checks.py:676`) does OTel-dot→underscore and
  strips one of `_bucket`/`_count`/`_sum`/`_total`. `extract_referenced_metrics` (`:691`) applies the
  same normalization to every metric parsed out of the existing exprs.

So the two writers ARE reconciled today — but by **normalized-name equality** (check #2), not by the
structural `(RedRole, metric_identity)` key. Check #2 is exactly the R1-F4 seam.

---

## 3. The R1-F4 Identity-Normalization Gap (the hard part)

### 3.1 Why the two identities can diverge

- **Descriptor path** references a real Prometheus metric name: e.g. `calls_total` or
  `rpc_server_duration_count`. After `_normalize_metric_name`, both strip to `calls` /
  `rpc_server_duration`.
- **Locus path** picks `family_or_signal` from the cited locus — a **family basename**
  (`affordance_map_consume.py:424`: `str(l.get("family_or_signal"))`), e.g. `calls` or
  `rpc_server_duration_seconds`. This is **not guaranteed to equal** `descriptor.throughput_metric`
  nor to normalize to the same base.

The dedup at `artifact_generator.py:1330` compares `_normalize_metric_name(fam)` against
`already_named`. It MISSES iff the locus family, once normalized, is a **different string** than the
normalized descriptor metric already in the dashboard. Concrete divergence classes:

| Descriptor metric (already panelled) | normalizes to | Locus family (`family_or_signal`) | normalizes to | Dedup? |
|---|---|---|---|---|
| `calls_total` | `calls` | `calls` | `calls` | HIT — collapses ✓ |
| `calls_total` | `calls` | `rpc_server_duration_seconds` | `rpc_server_duration_seconds` | **MISS → double RATE panel** |
| `http_server_duration_count` | `http_server_duration` | `http_requests` | `http_requests` | **MISS → double RATE panel** |

The `_normalize_metric_name` suffix-strip only reconciles names that share a base modulo one
`_total`/`_count`/`_bucket`/`_sum` suffix. Any *different base name* for the same logical throughput
series escapes it.

### 3.2 Do both writers actually fire for one service file? (empirically traced)

**Within a single `_apply_emit_red` call — NO (mutually exclusive).**
`_apply_emit_red` (`affordance_map_consume.py:2154`) branches on `metric_only` loci:
- If `metric_only` is non-empty (`:2180`) → writes `_locus_red_dashboard_yaml` output and **returns**
  (`:2224`). The whole file is *replaced* with the locus dashboard; the descriptor path never runs
  here.
- Else → falls through to `generate_dashboard_spec` (`:2233`, the descriptor path) and returns.

So `_apply_emit_red` is a clean either/or per service — it is **not** the double-emit site.

**Across the generate→bind pipeline — YES, this is the real R1-F4 site.**
The descriptor path runs at **generation time** (`_ensure_red_coverage`, invoked while the
`dashboard_spec` artifact is built), and `_apply_affordance_red_bind_panels`
(`artifact_generator.py:1195`, called at `:1847`) then **prepends** locus RED panels
(`panels[:0] = added_panels`, `:1340`) into that *same in-memory descriptor-generated dashboard*.
That is precisely the two-writers-on-one-file situation, and its ONLY guard against a duplicate is the
name-based check #2 at `:1330`. **This is where R1-F4 lives.** (Note `_apply_emit_red` and
`_apply_affordance_red_bind_panels` are two different landing paths for locus RED — TF-2 must handle
the bind path, which composes with the descriptor path; the emit path replaces and is self-consistent.)

### 3.3 The contract to add (FR-10a)

Per spec §4.1 FR-10a, TF-2 must either:

- **(a)** Define ONE normalization mapping the locus family name → the descriptor `metric_identity`,
  so both paths' RATE panels for one service carry the **same** key; OR
- **(b)** State (and structurally enforce) that the two writers are mutually exclusive per
  `dashboards/{svc}-dashboard-spec.yaml`.

The §3.2 trace shows (b) is **false** for the bind path — locus RED composes onto descriptor RED
there. So **(a) is required**: a single identity-normalization function, owned by `red_taxonomy`,
consumed by both adapters, so `(RedRole, metric_identity)` is a genuine cross-source key. The natural
home is a `red_metric_identity(name_or_family) -> str` helper alongside `synthesize_red_panels`,
reusing `_normalize_metric_name`'s suffix-strip PLUS any family→metric aliasing the descriptor already
knows (e.g. via `MetricDescriptor.throughput_metric`).

---

## 4. Proposed Approach

Follow spec §5 step 4, adapted for the two live inline synthesizers.

### 4.1 Make each synthesizer a thin adapter over `synthesize_red_panels`

Both `_ensure_red_coverage` and the locus RED builders build a `candidates: list[RedPanel]` and call
`synthesize_red_panels(existing, descriptor=..., want_roles=..., candidates=...)`, then render the
returned `RedPanel`s to the panel dicts they emit today.

- **Descriptor adapter (`_ensure_red_coverage`):**
  - `want_roles` from `sli_kinds`: `RATE` iff `throughput ∈ sli_kinds`, `ERROR` iff
    `availability ∈ sli_kinds` (mirrors `:1033`–`:1034`).
  - `descriptor` = the resolved `MetricDescriptor` (the descriptor tier).
  - `candidates` = one `RedPanel(role=RATE, metric_identity=<normalized throughput_metric>, ...)`
    and one `RedPanel(role=ERROR, metric_identity=<normalized throughput_metric>, ...)` — per D6 the
    ERROR leg rides `throughput_metric` (the selector is NOT the identity).
  - **Keep the `Availability (1h)` gauge as its own separate append** (`:1121`) — it is not a RED
    leg (NG2); do not route it through `synthesize_red_panels`.

- **Locus adapter (`_locus_red_dashboard_yaml` / the bind path):**
  - `want_roles` = the roles for which `_pick_red_families` returned a non-None family.
  - `descriptor=None` (descriptor-free tier).
  - `candidates` built from `_pick_red_families` via the **FR-8 tuple→`Mapping[RedRole, str]`
    adapter**: the positional `(rate, err, dur)` tuple (`affordance_map_consume.py:460`) maps to
    `{RATE: rate, ERROR: err, DURATION: dur}` (dropping None slots), and each family name becomes a
    `RedPanel.metric_identity` via the **FR-10a normalization** (§3.3) so it shares a key space with
    the descriptor path.

`synthesize_red_panels` then (a) skips any role already present in `existing` (via
`red_roles_present`, `red_taxonomy.py:315`) and (b) collapses any two candidates sharing
`(role, metric_identity)` (`:321`). At the bind site, pass the descriptor-generated panels as
`existing` and the locus candidates as `candidates` — the dedup becomes structural and the name-based
check #2 at `artifact_generator.py:1330` is deleted.

### 4.2 The identity-normalization contract (FR-10a)

Add to `red_taxonomy.py`:

```python
def red_metric_identity(name: str, *, descriptor: MetricDescriptor | None = None) -> str:
    """The single dedup identity for a RED metric, shared by the descriptor and locus paths.
    Strips the counter/histogram suffix (like _normalize_metric_name) AND resolves a locus
    family basename to the descriptor's throughput_metric identity when the descriptor knows it."""
```

Both adapters compute `metric_identity` through this one function, so `calls_total` (descriptor) and
`calls` (locus) — and any descriptor-known alias — collapse to one key.

---

## 5. Byte-Parity + Test Strategy (non-negotiable)

The session's hard rule: **generated-dashboard goldens stay byte-identical for correct cases.**

- **Golden corpus:** `tests/unit/observability/data/http_golden/` (`grpc-dashboard.yaml`,
  `http_with_avail-dashboard.yaml`, `counter_only-dashboard.yaml`, etc.). FR-11 requires the
  post-refactor descriptor path and locus path emit **byte-identical** `dashboard-spec.yaml` — same
  titles/exprs/units/groups, same panel ordering, same YAML serialization.
  - **Land the byte-parity golden gate FIRST** (before touching the synthesizers): a test that
    regenerates each golden through the current code and asserts byte-equality, so any drift the
    refactor introduces is caught at the diff.

- **Adversarial fixture for R1-F4 (the missing one):** `TestAdversarialParity`
  (`test_red_taxonomy.py:175`) already covers B2/B3/FR-4a divergences, and
  `test_fr10_dedup_by_role_and_identity` (`:148`) covers dedup — but **only for the SAME identity**
  (`calls_total` twice, `:153`–`:154`). It does **not** reproduce R1-F4's *divergent-identity*
  double-emit. TF-2 must add a fixture where:
  - the descriptor path has already emitted a RATE panel over `calls_total`
    (normalizes → `calls`), and
  - the locus path proposes a RATE panel whose `_pick_red_families` family is a **different** base
    (e.g. `http_requests` / `rpc_server_duration_seconds`),
  - and assert that **after FR-10a normalization + `synthesize_red_panels`, exactly ONE RATE panel
    survives** — proving the structural dedup catches what the name-based check at
    `artifact_generator.py:1330` misses.
  - A companion test should assert the OLD name-based path (pre-refactor) actually *fails* on that
    fixture (double panel), to prove the fixture is a real repro and not vacuous (per the FR-5a
    "corpus is silent → assert directly" rationale, `test_red_taxonomy.py:175` docstring).

- **FR-8 per-slot parity (R1-F9):** parametrized test over each locus set asserting the
  `(rate, err, dur)` slots are byte-unchanged **slot-by-slot** pre/post the tuple→Mapping adapter —
  not just tuple equality (the weak-duration rule `_RED_DUR_WEAK_RE` + distinct-family ordering make
  a canceling reassignment possible).

- **FR-7 scored-⟺-protected + FR-9/FR-10** unit tests already exist and must stay green.

---

## 6. Risks / Open Questions

- **OQ-TF2-1 — Is R1-F4 actually reachable?** The whole risk rests on a locus `family_or_signal`
  that normalizes to a **different** base than the descriptor `throughput_metric` for the SAME
  service, at the bind site (`artifact_generator.py:1330`). **Design a repro:** feed an affordance
  map whose cited locus family for a service is a throughput series NOT equal to that service's
  `descriptor.throughput_metric` (e.g. descriptor `calls_total`, locus `http_requests`), run the
  full generate → `_apply_affordance_red_bind_panels` pipeline, and assert two RATE panels land
  today. If it cannot be constructed from any real affordance map, R1-F4 downgrades to
  "unreachable-by-construction" and FR-10a becomes a belt-and-suspenders guard rather than a bug fix
  — record that verdict either way.

- **Panel ordering / gridPos byte-parity.** The bind path **prepends** (`panels[:0] = added_panels`,
  `artifact_generator.py:1340`) whereas `_ensure_red_coverage` **appends** (`panels.append`). Routing
  both through `synthesize_red_panels` must preserve each path's existing insertion position and any
  `gridPos` reflow (`affordance_map_consume.py:_reflow_gridpos` at `:1466`) — otherwise goldens drift
  even when the panel *set* is identical. The parity gate (§5) must include full-document byte-equality,
  not just panel-set equality.

- **`_RED_BIND_GROUP_PREFIX` group override.** The bind path stamps `group: _RED_BIND_GROUP_PREFIX`
  onto added panels (`:1332`), overriding the `RedPanel.group` the synthesizer would carry. Decide
  whether the adapter preserves that override (keep for byte-parity) or the group becomes part of the
  `RedPanel` contract.

- **`extract_referenced_metrics` still needed?** After FR-10a, the name-based check #2 (`:1330`) is
  deleted, but the exact-expr check #1 (`:1328`) and `existing` set may still be wanted as a cheap
  fast-path. Confirm no other consumer of `already_named` at that site.

---

## 7. Effort (M) + Recommended Process

**Effort: M.** One new normalization helper + two thin adapters + delete one name-based dedup, all
behind a byte-parity gate. The engine (`synthesize_red_panels`) already exists and is tested; TF-2 is
wiring + one genuinely new contract (FR-10a) + one new adversarial fixture. The risk is entirely in
byte-parity (ordering/gridPos/group) and in proving R1-F4 reachability, not in new algorithms.

**Recommended process (mirrors the session's arc):**

1. **reflective-requirements → CRP.** FR-10a is the only under-specified piece and it already drew a
   CRP finding; run the reflective-requirements loop on the FR-10a normalization contract + the
   ordering/gridPos parity risk, then a CRP round, *before* coding. The spec is v0.4 with R1 triage
   complete — TF-2 is the build of §5 step 4, so this is a focused delta, not a fresh spec.
2. **Land the byte-parity golden gate FIRST** (§5) — the regenerate-and-diff test over
   `http_golden/` and the `_locus_red_dashboard_yaml` output — so every subsequent commit is guarded.
3. **Add the R1-F4 repro fixture** and confirm it fails today (or record unreachable) — resolves
   OQ-TF2-1 before the fix, per spec §4.1 FR-5a's "assert directly, the corpus is silent" rationale.
4. **Implement FR-10a + the two adapters**, delete the name-based dedup (`artifact_generator.py:1330`),
   keep the Availability gauge separate.
5. **Green the full suite** incl. FR-7/FR-8-per-slot/FR-9/FR-10/FR-11 and the shrink refusal-ladder
   tests; verify the FR-13 grep guard still passes (no new RED classification outside `red_taxonomy`).

---

## Appendix — Verified Anchors

| Symbol | File:Line | Note |
|---|---|---|
| `synthesize_red_panels` | `red_taxonomy.py:300` | **Only occurrence in `src/` — zero callers.** |
| `RedPanel` (`(role, metric_identity)`) | `red_taxonomy.py:288` | dedup key at `:321` |
| `red_roles_present` (skip-if-present) | `red_taxonomy.py:238` | used at `:315` |
| `_ensure_red_coverage` (synth #1, inline) | `artifact_generator_generators.py:991` | `panels.append` `:1060`/`:1093`/`:1121` |
| `_locus_red_dashboard_yaml` (synth #2, inline) | `affordance_map_consume.py:2098` | `panels.append` `:2107`/`:2118`/`:2129` |
| `_pick_red_families` (positional tuple) | `affordance_map_consume.py:414` | returns `(rate, err, dur)` at `:460` |
| `_apply_emit_red` (either/or per call) | `affordance_map_consume.py:2154` | locus branch returns `:2224` |
| `_apply_affordance_red_bind_panels` (R1-F4 site) | `artifact_generator.py:1195` | name-dedup `:1330`; prepend `:1340` |
| `_normalize_metric_name` | `observability_artifact_checks.py:676` | strips `_bucket/_count/_sum/_total` |
| `extract_referenced_metrics` | `observability_artifact_checks.py:691` | builds `already_named` |
| `TestAdversarialParity` (no R1-F4 case yet) | `test_red_taxonomy.py:175` | `test_fr10_dedup` uses SAME identity `:148` |
| Goldens | `tests/unit/observability/data/http_golden/` | FR-11 byte-parity corpus |
| Spec §3.4 / FR-8 / FR-10a | `RED_TAXONOMY_UNIFICATION_REQUIREMENTS.md:303/371/416` | synthesizer + adapters + normalization |
