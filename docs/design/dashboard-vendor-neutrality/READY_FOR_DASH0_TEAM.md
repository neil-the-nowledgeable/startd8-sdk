# Ready for Dash0 Team — Perses Pilot Action Sheet

**Status:** Ready when the accompanying startd8 change is merged to `main`

**SDK-owned gates:** G1 ✅ · G2 ✅ · G4 ✅

**Dash0-owned gate:** G3 authorization/current target ☐ · live import T7 ☐

startd8 has completed its side of the pilot. The CLI now generates the reference dashboard through
the real neutral-model path, validates it against pinned Perses CUE, and reproduces the committed
artifact byte-for-byte. No Dash0 endpoint was contacted and no credential was requested or stored.

## Files to use

- Input: `pilot/dash0-pilot.observability.yaml`
- Import artifact: `pilot/obs-domain-dash0-pilot-v2.perses.json`
- Compatibility note: `DASH0_PERSES_COMPATIBILITY.md`
- Sanitized live-export profile:
  `tests/unit/dashboard_creator/fixtures/dash0_live_export_profile.golden.json`
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

Record the Dash0 product/build version visible to the team. Fourteen supplied live exports bound the
saved shape to `perses.dev/v1alpha1` `PersesDashboard`, dataset `default`, and Dash0-managed labels;
they do not replace authorization or prove that the current importer accepts this exact artifact.

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
6. Export the saved dashboard immediately, before making any UI edits.

Do not feed this exact file to an automated Dash0 CLI/operator/Terraform lane on the first attempt.
Those documented paths use a Dash0 `Dashboard` envelope or `PersesDashboard` CRD and stable IDs. If
the UI pilot passes, use the exported saved definition before designing an idempotent managed form.

Expected normalization is not an automatic failure: the supplied live evidence shows that Dash0
saves dashboards as `perses.dev/v1alpha1` `PersesDashboard`, adds dataset/managed-ID labels, includes
`variables: []`, and omits query datasource objects. The compatibility note distinguishes those
expected deltas from semantic loss.

## 4. Verify in Dash0

Record pass/fail for each item:

- [ ] Dashboard title is `dash0-pilot — domain observability (dynamic)`.
- [ ] Critical and Warning groups are visible and do not overlap.
- [ ] Three time-series panels render with their expected names.
- [ ] The explicit `default` Prometheus datasource is accepted; record whether Dash0 omits it when
      exporting the saved form.
- [ ] Query expressions remain the three `startd8_*` metric names from the source file.
- [ ] Critical thresholds are red; the warning threshold is orange.
- [ ] Count, seconds, and percent units render sensibly.
- [ ] Viewing/exporting the saved source does not silently remove panels, queries, or layouts.

The supplied demo exports query `traces_span_metrics_*` and HTTP metrics, not the three synthetic
`startd8_*` names. No-data is therefore expected unless those reference metrics were separately
loaded; this first attempt proves format and transformation fidelity. A parse/plugin/datasource
error is a compatibility failure. After the format attempt, generate a separate data-bearing
candidate against the demo's observed metrics rather than editing this golden.

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

Stop rather than editing around the result if Dash0 rejects the input, requires a hand edit before
acceptance, changes a plugin/query/layout, overlaps panels, loses thresholds/units, or disagrees
with the CUE oracle. The expected saved-form CRD/labels/empty-variables/datasource normalization is
documented separately and should be captured, not treated as semantic loss.
Return the evidence under the categories in `PILOT_NEXT_STEPS_dash0.md` §7. startd8 will update the
pin or lowering explicitly before another attempt.
