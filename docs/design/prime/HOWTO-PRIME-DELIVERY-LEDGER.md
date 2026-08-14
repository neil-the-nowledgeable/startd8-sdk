# HOWTO — Emit a delivery ledger after Prime merge

**Cite:** [`REQ-PRIME-DELIVERY-LEDGER.md`](./REQ-PRIME-DELIVERY-LEDGER.md) ·
[`PLAN-PRIME-DELIVERY-LEDGER.md`](./PLAN-PRIME-DELIVERY-LEDGER.md) ·
Check half: `dev-os/scripts/reconcile_lives_evidence.py`

## When

After generated project files are on a known merge commit (or tip). Do **not** treat
draft-time FLCM / disk-quality PASS as evidence.

## Emit (post-hoc)

```bash
python3 -m startd8.contractors.prime_delivery_ledger \
  --postmortem /path/to/plan-ingestion/prime-postmortem-report.json \
  --traceability /path/to/plan-ingestion/ingestion-traceability.json \
  --project-root /path/to/generated-project-git-root \
  --merge-sha <40-hex> \
  # default out: <project-root>/.startd8/delivery-ledger.yaml
```

`--merge-sha unknown` writes work items with **empty** evidence and loud skips (FR-4).

Never point `--out` at a ContextCore `dossier.yaml` (emitter refuses).

## Emit (optional postmortem hook)

When `PrimePostMortemEvaluator.evaluate(..., project_root=…)` runs `_write_outputs`, the
evaluator calls the same emitter **only if** a merge SHA is supplied via (first wins):

1. `result_dict["delivery_merge_sha"]` (preferred), or `result_dict["merge_sha"]`
2. env `PRIME_DELIVERY_MERGE_SHA`

and `ingestion-traceability.json` sits beside the written postmortem in `output_dir`.
Missing merge SHA → info-level skip (no invented locators). Failures are non-fatal to
the postmortem write path.

## Check (no conductor)

```bash
python3 /Users/neilyashinsky/Documents/dev/dev-os/scripts/reconcile_lives_evidence.py \
  --req /path/to/REQ.md \
  --dossier /path/to/generated-project/.startd8/delivery-ledger.yaml \
  --repo /path/to/generated-project-git-root \
  --out /tmp/prime-delivery-reconcile.json
```

Cross-repo: `--repo` is the **generated** git root; `--req` may live elsewhere.

| Book A | Expected Check |
|--------|----------------|
| Stub REQ (FR ids, no Lives) | `fr-missing-lives` — proves Book B loads |
| Fueled `Lives: code git:<sha>:<path>` matching ledger | `agree` for matching FRs |

Fuel Lives by hand (or a deliberate authoring pass). Do **not** auto-write Lives from
the ledger (harvest Option 5 — rejected).

## Non-goals

No live sync of contracts ⟷ FRs ⟷ health.
