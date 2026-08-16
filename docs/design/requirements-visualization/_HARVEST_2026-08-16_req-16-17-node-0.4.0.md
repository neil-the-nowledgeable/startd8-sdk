# Harvest — REQ-16 + REQ-17 (Node 0.4.0 schema bump)

**Date:** 2026-08-16 · **Surface:** `aaa39178` (feature) + ledger, landed to `main` ·
**Composition:** Harden-Then-Harvest (Spec Delivery Loop stage 7) · **Scope:** the 8 touched files of
the co-delivered REQ-16/17.

## Step 1 — HARDEN (/code-review + §1.5 value-path audit)

**Verdict: no Critical/High correctness defects; no `--fix` applied.** Independent adversarial review
(fresh eyes, separate agent) confirmed: the `pipeline_provenance` derivation-walk fallback is safe (guarded
`if node is not None and node.derivation:` — no IndexError; both src callers pass projected nodes that carry
edges, so behavior is identical to the pre-change `child_keys` walk); all 4 new Node fields have defaults
(no positional-construction / hashing / `dataclasses.fields` breakage); frozen-dataclass equality/replace
intact.

**§1.5 value-path findings (all Low / informational — none block):**
- **VP-1 (dormant-in-src, by design):** `field_parity_drift`, `status_gap_class`, `health_gap_class` have
  no `src/` call site — their call site is the **test gate** (`test_schema_conformance` /
  `test_status_agreement`), which is exactly what REQ-16 FR-2/FR-3 specify (`Lives: test`). The guards FIRE
  (negative tests exist: synthetic-field drift, manifest-drop drift). No runtime overclaim in commit/ledger.
  Not a defect — a test-side conformance gate fuelled by CI.
- **VP-2 (real value-path gap → backlog EB-1):** the 4 promoted fields are carried on the **Node object**
  (REQ-17 O-2, tested) but **dropped at the JSON boundary** — `project._node_to_json` / `nodes_from_json`
  enumerate a field subset that omits them (as it already omits the pre-existing `status_facets`). So
  `navigator build --source requirements --format json` does not surface the oracle/gate/history, and a
  JSON round-trip loses them. **Not a regression** (the fields are new) and **not in REQ-17's explicit
  scope** (its Verify is object-level), but it half-realizes the "carry, don't drop" thesis for any JSON
  consumer. Deferred to EB-1 because the JSON export **is** the cross-repo NODE-SCHEMA-JSON contract that
  NR-1/NR-3 reserve for the coordinated cross-repo handoff.
- **VP-3 (cosmetic):** `sources_node_schema._FIELD_META["attributes"]` example string changed
  `verify/approve` → `serves`; the attrs bag still carries `verify`/`approve_prompts`/`was` (render
  channel), so the old example was accurate. Neutral; not worth a churn.

## Step 2 — /python-code-refactor

**Skipped-as-no-op (Python in scope, but nothing to harden).** The added code is pure, total functions
(`field_parity_drift`, `status_gap_class`, `health_gap_class`) + a frozen dataclass + additive field
projection — no I/O, no exception paths, no logging surface. Robustness/logging refactor finds nothing.

## Step 3 — RETROSPECTIVE (the standard this delivery proved)

**The reusable standard — "additive schema-field promotion under a byte-identity guard":**
1. **One golden delta, co-churned.** Two specs that both touch `Node`'s field set landed as a *single*
   `node_field_names()` change (`{verify, approve, was, derivation}`) — the golden churned once, not twice.
   The exit oracle was `test_no_profile_is_byte_identical` **UNEDITED** + the field-set golden as the *only*
   intended change.
2. **The render channel and the semantic channel are separate.** New fields rode onto the Node as the SSOT
   while the pre-existing `attributes` bag stayed the render channel → byte-identity for free (fields aren't
   rendered). This is the SOTTO pattern applied to a schema bump.
3. **A schema bump earns a self-conformance gate.** `NODE_FIELD_MANIFEST` + `field_parity_drift` make the
   next un-mirrored field addition fail loud — metabolizing the exact drift class that left
   `NODE-SCHEMA.md` §1 stale. The gate is the schema-as-Node self-check.
4. **Reserve-don't-populate for forward-compat.** REQ-16 reserved the edge's `regime` slot UNSET so the
   follow-on realization REQ (REQ-18, already picked up) *fills a slot* rather than adding a parallel facet.
5. **Discriminating test over presence test.** The derivation-edge value was proven by *rewiring* an edge
   and asserting the provenance chain followed it (not `child_keys`) — a test that fails if the edge is
   inert, not merely one that checks the edge exists.

**Dormant inventory (Phase 2.5, grounded in code):** VP-1's three helpers (test-side by design — file as
prior-art, not defects) and VP-2's JSON-export gap (the one genuine built-but-unwired value path).

## Step 4 — ENHANCEMENT BACKLOG (single-pass; scoped surface → not full CEP)

| # | Enhancement | Value | Effort | Notes |
|---|---|---|---|---|
| **EB-1** | Surface the promoted fields (`verify`/`approve`/`was` + `derivation`, and `status_facets`) in the JSON export — **presence-gated / additive** (emit a key only when non-empty → byte-identical for every node that lacks it, SOTTO), and read them back in `nodes_from_json` for a true round-trip | closes VP-2: `--format json` and JSON round-trips carry the reliability semantics REQ-17 promoted | **M** | The JSON **is** the cross-repo NODE-SCHEMA-JSON contract → **coordinate with the NR-3 cross-repo handoff** (dev-os doc + CC mirror). Add a round-trip test asserting field preservation (current `test_nodes_json_roundtrip` only checks the tree). |
| **EB-2** | Consider whether `status_gap_class`/`health_gap_class` should back a runtime `gap_class` on the requirement projection (today only `status_key` exists), unifying the agreement taxonomy with the live status | promotes VP-1 from test-only to a runtime value path (if valuable) | **S** | Optional — only if a consumer needs the normalized gap-class at runtime. Guard byte-identity (attrs). |
| **EB-3** | Cross-repo adoption of `status_contract.json` by `extract.py` / `req-health.mjs` (REQ-16 NR-3 follow-up) | the portable contract earns its keep only once a 2nd impl runs it | **M** | Yokoten — the bus handoff below seeds it. |

## Step 5 — BUS

See the accompanying bus post (Yokoten to the Node/ContextCore + dev-os owners): the 0.4.0 field set is
live SDK-side, the parity gate now flags the dev-os §1 / CC-mirror drift **by design** until they adopt,
and `status_contract.json` is ready for the cross-repo twins. EB-1's JSON-export change should ride the
same coordinated NODE-SCHEMA-JSON contract update.

## Where the composition stopped

All 5 steps ran. Step 1 hardened (no fixes needed — clean surface). Step 2 was a no-op. Steps 3–4 are the
substantive harvest (this doc). Step 5 = the bus handoff (posted or explicit-skip recorded in the session).
