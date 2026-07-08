# Workbook Access Control & Provisioning Auth — Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-07-08
**Requirements:** `WORKBOOK_ACCESS_CONTROL_REQUIREMENTS.md` (v0.3)

## Planning summary

The load-bearing control is **folder + folder-ACL**, and the SDK's `GrafanaClient` supports **neither**
today (only `upsert_dashboard(json)`). So the core of this work is a small, well-bounded extension of
`grafana_client.py` + wiring it into the portal provision path — plus posture/ops requirements (token
scope, anon-off) that are checks + docs, not much code.

## M1 — Folder + ACL (the load-bearing control)

**Goal:** the Workbook lands in a project-scoped folder that only intended principals can view.
- `grafana_client.py`: add `create_folder(title, uid)`, `folderUid` param on `upsert_dashboard`, and
  `set_folder_permissions(uid, items)` over `/api/folders/{uid}/permissions`.
- Portal wiring (`cli_concierge.py` provision path + `dashboard_creator` config): `--folder-uid`
  (default `cc-kickoff-{project}`) + `--viewers` (principals). **Least-exposure default** (provisioning
  identity + explicitly-named viewers; never org-wide).
- **Fail-closed (OQ-3):** if the target Grafana can't set folder ACLs (version/permission), **refuse to
  provision by default** (`--allow-no-acl` to override + a loud warning).
- **Exit:** household provisions into `Kickoff — household-o11y`; an org Viewer NOT in the ACL cannot see it.

## M2 — Content policy (secrets out; business values folder-protected)

**Goal:** no secrets/PII in panels; business values guarded by the folder, not scrubbed.
- Run any free-text that becomes panel markdown through `tracking_redaction.redact_text` (secrets +
  home paths) before it's embedded — a thin pass in `portal_spec`'s section builders.
- Data-minimization: keep the existing state/summary bias; do NOT scrub business values (they're the
  point) — they're protected by M1.
- **Exit:** a planted fake secret/home-path in a kickoff input does not appear verbatim in the dashboard JSON.

## M3 — Viewing boundary + token posture

**Goal:** authenticated-only viewing; least-privilege, non-leaked token.
- Preflight in `--provision`: query Grafana's frontend settings; **refuse/warn if anonymous access is
  enabled** for the org (FR-5).
- Docs: provisioning uses a **folder-scoped service account** (not org-admin); token from env, never
  written into dashboard JSON/specs/logs; rotation expectation.
- **Exit:** provision refuses on an anon-enabled Grafana (or with `--allow-anon` + warning); grepping the
  generated JSON for the token finds nothing.

## M4 — Pilot + verdict

- Migrate the household Workbook from General → the restricted folder; verify from a **second, non-ACL
  Grafana user** that the Workbook is not visible; confirm no other-project viewer can read it. Verdict.

## Traceability

| Req | Milestone |
|-----|-----------|
| FR-1 dedicated folder | M1 |
| FR-2 folder view-ACL | M1 |
| FR-3 content policy | M2 |
| FR-4 least-privilege token | M3 |
| FR-5 anon-off viewing boundary | M3 |
| FR-6 shared-Grafana isolation | M1 + M4 |

## Risks

1. **Grafana ACL model quirks** — folder permissions differ across Grafana versions / with RBAC on;
   `set_folder_permissions` must handle the response and the fail-closed path (OQ-3) cleanly.
2. **Existing General-folder dashboards** (household already provisioned) — decide migrate-on-next-provision
   vs leave (OQ-4); a left-behind copy in General defeats the control.
3. **Token over-privilege is a Grafana-side config** — the SDK can recommend + check, but can't enforce a
   least-privilege SA; state this honestly.
