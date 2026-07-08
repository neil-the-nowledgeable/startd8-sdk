# Digital Project Workbook — Team Runbook (Template)

A copy-and-adapt runbook a **project team** can use to run kickoff via the **Digital Project Workbook** —
a Grafana dashboard generated from the project's kickoff state. Copy this into your project (e.g.
`docs/kickoff/KICKOFF_NEXT_STEPS.md`) and fill in the `<…>` placeholders once.

> **What this is:** a shared, whole-project view of the foundational kickoff decisions (targets,
> conventions, observability, build prefs, stakeholders), projected onto a Grafana dashboard.
> Generating it is deterministic and **free** (no LLM). The board is **read/status only** — you edit
> inputs with the `confirm` command, which refreshes the board.

## Fill these in once (per environment)

| Placeholder | What it is | Example |
|---|---|---|
| `<SDK_VENV>` | Path to the startd8-sdk virtualenv (has the Workbook feature + `[server]` extra) | `~/Documents/dev/startd8-sdk/.venv` |
| `<PROJECT>` | Your project's root directory | `~/Documents/dev/my-project` |
| `<GRAFANA>` | Grafana base URL | `http://localhost:3000` |
| `<SLUG>` | Your project's dashboard slug = the folder name, lowercased, spaces/`_`→`-` | `my-project` |
| `<DS_UID>` | (Step 4 only) datasource UID that proxies the stakeholder endpoint | `startd8-stakeholders` |

Your board will be at **`<GRAFANA>/d/cc-portal-kickoff-<SLUG>`**.

---

## 0. One-time setup (per shell)

Run everything from **any directory** — commands take explicit paths, so the working directory doesn't
matter. What matters is using the venv's `startd8` (it has the Workbook feature *and* the server extra):

```bash
source <SDK_VENV>/bin/activate

startd8 kickoff portal --help | grep -q -- --index && echo "✓ startd8 has the Workbook feature"
curl -s -o /dev/null -w "grafana = %{http_code} (expect 200)\n" <GRAFANA>/api/health
[ -n "$GRAFANA_API_TOKEN" ] && echo "✓ GRAFANA_API_TOKEN set" || echo "✗ export GRAFANA_API_TOKEN first"
```

> `No module named 'starlette'` means you're using a `startd8` without the `[server]` extra — activate
> the venv above (only the optional stakeholder-panel serve step needs it).

---

## 1. Create the Workbook and publish it to Grafana

```bash
PROJECT=<PROJECT>
GRAFANA=<GRAFANA>

startd8 kickoff instantiate "$PROJECT" --apply --provision "$GRAFANA"
```

Scaffolds the kickoff inputs under `$PROJECT/docs/kickoff/inputs/`, generates the Workbook, and pushes it
to Grafana. Open **`<GRAFANA>/d/cc-portal-kickoff-<SLUG>`** — you'll see each input domain, how many
fields are confirmed, and the open gaps.

*(Prefer to generate locally without pushing? Drop `--provision "$GRAFANA"` — the JSON lands under
`$PROJECT/.startd8/dashboards/`. Add `--no-portal` to skip the dashboard entirely.)*

---

## 2. The kickoff loop — decide inputs, the board updates live

Inputs start as templates. Confirm each field with a real value (or accept the default as-is); every
confirm **refreshes and re-pushes the board**, so progress shows up in Grafana immediately.

```bash
startd8 kickoff assess "$PROJECT"                    # what's still awaiting a decision

# set a real value (repeat per field):
startd8 kickoff confirm "<domain>.yaml#/<field>" --value "<value>" --provision "$GRAFANA"

# or accept a default unchanged:
startd8 kickoff confirm "conventions.yaml#/language" --as-is --provision "$GRAFANA"
```

Field names come from `startd8 kickoff assess "$PROJECT"` (or list them with
`startd8 kickoff confirm --all --as-is --dry-run --project "$PROJECT"`); they look like
`domain.yaml#/path.to.field`.

**Bulk-accept every default, then refresh once:**
```bash
startd8 kickoff confirm --all --as-is --yes --project "$PROJECT"
startd8 kickoff portal "$PROJECT" --provision "$GRAFANA"
```

---

## 3. All projects in one place (portfolio index)

```bash
startd8 kickoff portal --index --provision "$GRAFANA" --yes
```
Open **`<GRAFANA>/d/cc-portal-kickoff-index`** — a self-updating list linking every project's Workbook.
New projects appear automatically (no regeneration needed).

---

## 4. (Optional) Run a stakeholder panel from the dashboard

A Grafana panel can run a role-played stakeholder Q&A (this **spends** a little via an LLM).

```bash
# Terminal 1 — start the endpoint (leave running); copy the token it prints:
startd8 kickoff stakeholders serve --enable-apply --strict --host 0.0.0.0 --daily-ceiling 5
```
Then in Grafana: **Add → Visualization → "StartD8 Kickoff Stakeholders"**, set **Run datasource
UID = `<DS_UID>`**, mode **Run**. Needs a `stakeholders.yaml` roster in
`$PROJECT/docs/kickoff/inputs/`. Every answer is **synthetic & unratified** — a stand-in, not a real
person. (Datasource setup: `grafana-plugins/kickoff-stakeholders-panel/provisioning/`.)

---

## What renders, and one known limitation

- **Text panels** (fields, the What/Why/Who per domain, the pipeline funnel) render fully — the useful
  part today.
- **Gauges** (confirmed %, gaps) may show **"No data"** — the live-metric feed is a separate, deferred
  piece of work. Use the field text panels + `startd8 kickoff assess` for the real numbers for now.

The Workbook is a **read/status surface** — you never edit values *in* Grafana. All edits go through the
`confirm` loop (§2), which keeps the board in sync.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No module named 'starlette'` | Wrong `startd8` — `source <SDK_VENV>/bin/activate` (only step 4 needs it). |
| `Workbook: skipped — no jsonnet toolchain` | Install jsonnet: `brew install jsonnet` (or `pip install gojsonnet`). |
| Provision fails / 401 | `export GRAFANA_API_TOKEN=<a Grafana service-account token>`. |
| Board didn't update after confirm | You omitted `--provision <GRAFANA>` — re-run `startd8 kickoff portal "$PROJECT" --provision "$GRAFANA"`. |
| `refusing to overwrite a different project's Workbook` | Two projects' names map to the same board UID — rename this project's folder. |

---

## Quick reference

```bash
PROJECT=<PROJECT>; GRAFANA=<GRAFANA>

startd8 kickoff instantiate "$PROJECT" --apply --provision "$GRAFANA"   # create + publish
startd8 kickoff assess "$PROJECT"                                       # what's awaiting
startd8 kickoff confirm <field> --value <v> --provision "$GRAFANA"      # decide a field (board updates)
startd8 kickoff portal "$PROJECT" --provision "$GRAFANA"                # re-publish on demand
startd8 kickoff portal --index --provision "$GRAFANA" --yes             # all-projects index
```

Board: **`<GRAFANA>/d/cc-portal-kickoff-<SLUG>`** · Index: **`<GRAFANA>/d/cc-portal-kickoff-index`**

---

*Template. The feature it documents: `WORKBOOK_PROJECT_START_REQUIREMENTS.md` (generation lifecycle),
`GRAFANA_KICKOFF_PORTAL_REQUIREMENTS.md` (the dashboard/content + the deferred live-metrics track).*
