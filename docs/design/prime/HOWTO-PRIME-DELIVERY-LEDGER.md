# HOWTO — Emit a delivery ledger after Prime merge

**Cite:** [`REQ-PRIME-DELIVERY-LEDGER.md`](./REQ-PRIME-DELIVERY-LEDGER.md) ·
[`PLAN-PRIME-DELIVERY-LEDGER.md`](./PLAN-PRIME-DELIVERY-LEDGER.md) ·
Check half: `dev-os/scripts/reconcile_lives_evidence.py`

## When

After generated project files are on a known merge commit (or tip). Do **not** treat
draft-time FLCM / disk-quality PASS as evidence.

## Emit

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

## Check (no conductor)

```bash
python3 /Users/neilyashinsky/Documents/dev/dev-os/scripts/reconcile_lives_evidence.py \
  --req /path/to/REQ.md \
  --dossier /path/to/generated-project/.startd8/delivery-ledger.yaml \
  --repo /path/to/generated-project-git-root \
  --out /tmp/prime-delivery-reconcile.json
```

Cross-repo: `--repo` is the **generated** git root; `--req` may live elsewhere.
Stub Book A (FR ids, no Lives) yields `fr-missing-lives` — proves Book B loads; it is
not agreement. Fuel `Lives:` separately for `agree`.

## Non-goals

No live sync of contracts ⟷ FRs ⟷ health (harvest Option 5 — rejected).
