# Recon artifacts (rungs 1→2, preserved)

These are the **throwaway recon scripts** that established the TSDB→relational ladder's first two
rungs. They were originally written to `/tmp/` (see NEXT_STEPS "Recon artifacts"); preserved here
before `/tmp` was cleared because they are the **working starting shape** for the production
`tsdb_maturation/{reader,specimen}.py` (M0/M1).

| File | Rung | What it proves / provides |
|---|---|---|
| `tsdb_recon.py` | 1 | Inventory series reachable via the Grafana datasource proxy (`/api/datasources` → per-prometheus `__name__` values). Read-only. |
| `tsdb_inspect.py` | 2 | Label structure + per-label cardinality of candidate metrics (`/api/v1/query`). |
| `tsdb_range.py` | 1→2 | `query_range` over a wide window to locate + materialize real samples, then flatten one metric to a specimen JSON. |
| `specimen-startd8_cost_USD_total.json` | — | A real flattened specimen (28 records; labels `job/model/project/provider` + `value`/`observed_at`). Used as an M0/M1 fixture. |

> These are **urllib**-based and hand-shaped. The production reader (`reader.py`, FR-1) generalizes
> the *shape* — instant `last_over_time(<m>[<lookback>])`, endpoint config, empty-result detection,
> auth handling — onto `httpx`. Do not import these from `src/`; they are reference only.
