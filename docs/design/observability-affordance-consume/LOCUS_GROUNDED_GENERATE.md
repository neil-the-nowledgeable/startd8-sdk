# AffordanceMap locus-grounded generate — startd8 note

**Parent REQ (ContextCore catalog):**  
`ContextCore/docs/design/requirements/REQ_O11Y_LOCUS_GROUNDED_ARTIFACT_GENERATE.md` (v0.3)  
**Plan:** `ContextCore/docs/plans/PLAN_O11Y_LOCUS_GROUNDED_ARTIFACT_GENERATE.md`  
**Phase B base:** [`REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md`](REQ_AFFORDANCE_MAP_GENERATOR_CONSUME.md)

## Shipped here

- Load AffordanceMap rows with `locus_status` / `source_loci` / `signal_kind`
- Optional `--needed-where` merge (AffordanceMap-native loci win)
- Planner: block `no_source_locus`/`unverifiable`/`locus_unavailable` for non–artifact-shape `gen.*`; `transport_only_loci` skip for RED; live `gen.improve_metric_coverage` when `source_backed` + metric loci
- Apply: locus-biased RED panels (metric families only); coverage PromQL bind to cited family
- Sidecar fields: `loci_used`, `locus_skip_reason`, `locus_status`

```bash
python3 scripts/generate_observability_artifacts.py \
  --onboarding-metadata PATH \
  --output-dir OUT \
  --affordance-map /path/to/affordance-map-export.json \
  # optional transitional:
  # --needed-where /path/to/needed-where.json \
  --dry-run
```

Prefer X2-enriched `affordance-map-export.json` from Thanos `analysis/fde-latest/`.
