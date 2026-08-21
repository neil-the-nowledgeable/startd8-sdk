# Ready for Dash0 Team — Perses Pilot Action Sheet

**Status:** Ready when the accompanying startd8 change is merged to `main`

**SDK-owned gates:** G1 ✅ · G2 ✅ · G4 ✅

**Dash0-owned gate:** G3 ☐ · live import T7 ☐

startd8 has completed its side of the pilot. The CLI now generates the reference dashboard through
the real neutral-model path, validates it against pinned Perses CUE, and reproduces the committed
artifact byte-for-byte. No Dash0 endpoint was contacted and no credential was requested or stored.

## Files to use

- Input: `pilot/dash0-pilot.observability.yaml`
- Import artifact: `pilot/obs-domain-dash0-pilot-v2.perses.json`
- Compatibility note: `DASH0_PERSES_COMPATIBILITY.md`
- Boundary inventory: `T0_perses-coverage-matrix.md`

Do not edit the import artifact before the first attempt. A rejection is useful compatibility
evidence; a hand edit would erase it.

## 1. Close G3 before importing

The Dash0 pilot owner supplies, outside this repository:

- the target Dash0 organization/project and dataset;
- an account allowed to create a dashboard;
- the selected import path (for this exact bare Perses artifact, use the Dash0 UI **Edit as JSON**
  upload documented for external Perses JSON);
- confirmation that the `default` Prometheus datasource resolves in that target;
- a secure credential channel if the Dash0 CLI is used. Never paste a token into an issue, log,
  screenshot, shell history excerpt, or repository file.

Record the Dash0 product/build version visible to the team. Dash0's public docs confirm external
Perses JSON import but do not publish the exact Perses core/spec/plugin version behind the importer.

## 2. Reconfirm the artifact locally (no Dash0 action)

From the startd8-sdk repository:

```bash
go install cuelang.org/go/cmd/cue@v0.16.1
export STARTD8_CUE_BINARY="$(go env GOPATH)/bin/cue"
STARTD8_SECRETS_BACKEND=local startd8 dashboard create \
  docs/design/dashboard-vendor-neutrality/pilot/dash0-pilot.observability.yaml \
  --target perses \
  --project dash0-pilot \
  --output-dir docs/design/dashboard-vendor-neutrality/pilot \
  --check
```

Expected: exit 0 and `Check passed — Perses Dashboard: obs-domain-dash0-pilot-v2`. `--check` does not
write. If it fails, stop before Dash0 and return the complete redacted error.

## 3. Recommended first import: Dash0 UI

Per Dash0's [Import Dashboards](https://www.dash0.com/docs/dash0/dashboards/import-dashboards)
documentation:

1. Open **Dashboards** and select **+ Add**.
2. Open **Edit as JSON** in the dashboard editor.
3. Upload `pilot/obs-domain-dash0-pilot-v2.perses.json` unchanged.
4. Capture the accept/reject result before clicking through any conversion prompt.
5. If accepted, click **Apply**, then save once.

Do not feed this exact file to an automated Dash0 CLI/operator/Terraform lane on the first attempt.
Those documented paths use a Dash0 `Dashboard` envelope or `PersesDashboard` CRD and stable IDs. If
the UI pilot passes, export the saved definition before designing an idempotent managed form.

## 4. Verify in Dash0

Record pass/fail for each item:

- [ ] Dashboard title is `dash0-pilot — domain observability (dynamic)`.
- [ ] Critical and Warning groups are visible and do not overlap.
- [ ] Three time-series panels render with their expected names.
- [ ] The `default` Prometheus datasource resolves for every query.
- [ ] Query expressions remain the three `startd8_*` metric names from the source file.
- [ ] Critical thresholds are red; the warning threshold is orange.
- [ ] Count, seconds, and percent units render sensibly.
- [ ] Viewing/exporting the saved source does not silently remove panels, queries, or layouts.

No-data is not automatically a format failure: first confirm whether the chosen dataset actually
contains the three reference metrics. A parse/plugin/datasource error is a compatibility failure.

## 5. Return this evidence

- Dash0 product/build identifier and import path used;
- exact accept/reject response, with secrets redacted;
- exported post-import Perses source;
- screenshots of both groups and all three panels;
- whether the datasource and each query resolved;
- any transformation Dash0 applied;
- a short verdict: `pass`, `pass-with-documented-transform`, or `fail`.

Store evidence in the pilot's approved location, not in this repository if it contains tenant or
dataset information. Report only sanitized artifacts here.

## 6. Stop conditions

Stop rather than editing around the result if Dash0 rejects the resource, requires a different
plugin kind/envelope, overlaps the panels, loses thresholds/units, or disagrees with the CUE oracle.
Return the evidence under the categories in `PILOT_NEXT_STEPS_dash0.md` §7. startd8 will update the
pin or lowering explicitly before another attempt.
