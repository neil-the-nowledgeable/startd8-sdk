# Digital Project Workbook — Access Control & Provisioning Auth Requirements

**Version:** 0.3 (Post-planning + lessons hardening — ready for CRP)
**Date:** 2026-07-08
**Status:** Draft
**Parent:** the Digital Project Workbook (`GRAFANA_KICKOFF_PORTAL_*`); consistent with the endpoint
auth posture in `WORKBOOK_STAKEHOLDER_RUN_*` FR-2.
**Pilot:** `household-o11y`

---

## 0. Planning Insights (Self-Reflective Update)

> A grounded pass over `dashboard_creator/{grafana_client,provisioning}.py`, the portal provision path,
> and `integrations/tracking_redaction.py`. Four corrections — the biggest: the SDK's Grafana client
> can't place a dashboard in a folder or set any permission today.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Provisioning supports a target folder | `GrafanaClient` has **only** `upsert_dashboard(json)` / `get` / `search` / `delete` — **no folder arg, no `folderUid`**. The dashboard is posted with no folder → lands in **General** (confirmed for household). | FR-1: add `folderUid` to the upsert + a create-folder call — a small **to-build**. |
| Folder view-ACLs are configurable via the SDK | `GrafanaClient` has **no permissions API** at all (`/api/folders/{uid}/permissions` unwrapped). | FR-2: a `set_folder_permissions` wrapper is **net-new to-build** — and it's the **load-bearing** control. |
| `tracking_redaction` can hide sensitive business values | It redacts **secrets + home paths** (via `fde.redaction`), NOT business-sensitive-but-non-secret values (budgets, targets). | FR-3: the primary control is the **restricted folder** (authz), not redaction. `tracking_redaction` is reused only to ensure **no secrets/paths/PII** leak into panels; business values are protected by *who can see the folder*, not by scrubbing them (scrubbing defeats the dashboard). |
| Least-privilege token is mostly a code change | The token is `$GRAFANA_API_TOKEN` from env; scope is a **Grafana-side SA role**, not SDK code. | FR-4 is largely a **posture/ops requirement** (a folder-scoped SA) + "never embed the token in artifacts." |

**Resolved:** the highest-value control is **folder + folder-ACL** (authz), not content redaction.
**Still open:** OQ-1 (folder naming/sharing model), OQ-2 (how ACL principals are specified), OQ-3
(behavior when the target Grafana can't do folder ACLs — refuse to provision vs warn).

### 0.1 Lessons-Learned Hardening
- **Phantom-reference audit** — grounded every named symbol: `GrafanaClient.upsert_dashboard` exists;
  `create_folder`/`set_folder_permissions`/`folderUid` do **not** (marked to-build, FR-1/FR-2). Added
  the Reference Audit.
- **Overloaded-term discipline** — do **not** conflate `tracking_redaction` (a *secrets* redactor) with
  a *business-sensitivity* policy; they are different controls (FR-3 keeps them separate).
- **Single-source vocabulary** — the deployment-posture language (local-trusted vs strict, token
  handling) is **owned by `WORKBOOK_STAKEHOLDER_RUN_*` FR-2**; this doc cites it, doesn't restate it.
- **CRP steering** — brand-new doc; settled/do-not-relitigate: authz-via-folder-ACL is the primary
  control; the read Workbook embeds real values by design (data-minimization is defense-in-depth, not
  the main control); consistency with the endpoint FR-2 posture.

### Reference Audit

| Symbol / capability | Exists? | Path |
|---------------------|---------|------|
| `GrafanaClient.upsert_dashboard(json)` | ✅ (no folder arg) | `dashboard_creator/grafana_client.py:114` |
| `GrafanaClient` folder placement (`folderUid`) | ❌ to-build | — |
| `GrafanaClient` folder permissions / `set_folder_permissions` | ❌ to-build (the key gap) | — |
| `redact_text` / `redact_attrs` (secrets, not business values) | ✅ | `integrations/tracking_redaction.py:37,53` |
| endpoint auth posture (bearer token, local/strict split) | ✅ (cite, stay consistent) | `WORKBOOK_STAKEHOLDER_RUN_REQUIREMENTS.md` FR-2 |
| Grafana anonymous access (currently OFF) | ✅ verified 2026-07-08 | `o11y-dev` Grafana config |

---

## 1. Problem Statement

The **write/drive/apply endpoints** have solid, CRP-hardened auth (`WORKBOOK_STAKEHOLDER_RUN_*` FR-2;
`WORKBOOK_PANEL_PIPELINE_*` FR-R7). The **read Workbook** — the Grafana dashboard `startd8 kickoff
portal --provision` generates — has **none**. Observed 2026-07-08:

| Component | Current State | Gap |
|-----------|---------------|-----|
| Dashboard folder | provisioned to **General** (verified: household) | General is visible to **every org Viewer+** |
| Folder view-ACL | none | no control over *who sees* the project's data |
| Embedded content | raw business-target values, budgets, roster, staged recs baked as markdown | sensitive data exposed to any authorized folder viewer |
| Provisioning token | `$GRAFANA_API_TOKEN` SA, unspecified scope | possibly over-privileged; no rotation policy |
| Viewing boundary | Grafana login (anon OFF) — good, but unstated | could silently weaken |
| Shared instance | `o11y-dev` also hosts online-boutique/Beaver dashboards | one project's data leaks to unrelated viewers |

The read Workbook contains **real project decisions** (targets, budgets, stakeholders). On a shared
Grafana, "any authorized viewer sees it" is a genuine exposure.

## 2. Requirements

- **FR-1 — Provision to a dedicated, non-General folder.** `kickoff portal --provision` MUST place the
  Workbook in a **project-scoped folder** (e.g. `Kickoff — {project}` / uid `cc-kickoff-{project}`), not
  General. Requires adding `folderUid` to `upsert_dashboard` + a create-folder-if-absent call. A
  `--folder`/`--folder-uid` option; a sensible default derived from the project.
- **FR-2 — Restrict folder view-permissions (the load-bearing control).** The folder MUST carry
  **view-ACLs** so only intended principals (a team/role/user) see it — **never inheriting General's
  all-Viewers default** on a shared instance. Requires a `set_folder_permissions` wrapper over Grafana's
  `/api/folders/{uid}/permissions`. Default posture: **least-exposure** (the provisioning identity + an
  explicitly-named principal), not org-wide.
- **FR-3 — Content policy: no secrets/PII in panels; business values protected by the folder.** (a) The
  generated panels MUST NOT embed **secrets, API keys, tokens, or absolute home paths** — run any
  free-text through the `tracking_redaction` chokepoint before it becomes panel markdown. (b)
  Business-sensitive values (targets, budgets, roster, synthetic answers) are **protected by FR-1/FR-2
  (who can see the folder)**, NOT by scrubbing (scrubbing defeats the Workbook). (c) A **data-minimization
  default**: the Workbook prefers *state/summary* over raw values where a summary suffices, with raw
  values shown only inside the restricted folder.
- **FR-4 — Least-privilege provisioning token.** The provisioning credential SHOULD be a **folder-scoped
  service account** (dashboard/folder write, not org-admin). The token comes from env
  (`$GRAFANA_API_TOKEN`), is **never written into generated artifacts** (dashboard JSON, specs, logs),
  and the docs state a rotation expectation. (Consistent with `WORKBOOK_STAKEHOLDER_RUN_*` FR-2 token
  handling.)
- **FR-5 — Authenticated viewing boundary (anonymous stays OFF).** The Workbook requires
  **authenticated Grafana access**; **anonymous access MUST remain disabled** for Workbook folders. This
  is stated as a hard requirement + a **preflight check** (`kickoff portal --provision` warns/refuses if
  the target Grafana has anonymous access enabled).
- **FR-6 — Shared-Grafana isolation.** On a shared instance, a project's Workbook MUST NOT be visible to
  viewers of unrelated dashboards. FR-1 (own folder) + FR-2 (folder ACL) deliver this; the requirement
  is to **verify** no other-project viewer can read it (part of the pilot).

## 3. Non-Requirements

- **NR-1 — Not org-wide Grafana RBAC design.** We scope Workbook folders, not the instance's roles.
- **NR-2 — Not redacting business values.** The Workbook shows real targets/budgets by design; the
  control is *the folder*, not scrubbing. (Secrets/PII are still scrubbed — FR-3a.)
- **NR-3 — Not cloud/SSO/multi-org.** Local shared instance only; no enterprise IdP integration.
- **NR-4 — Not re-specifying endpoint auth.** The run/apply endpoints keep their FR-2 posture; this doc
  is the *dashboard* (read) side only.
- **NR-5 — No secret storage subsystem.** The token stays in env; we don't build a vault.

## 4. Open Questions

- **OQ-1 — Folder naming + sharing model.** One folder per project (`cc-kickoff-{project}`), or one
  shared "Kickoff" folder with per-dashboard ACLs? (Grafana ACLs are folder-level, favoring per-project
  folders.)
- **OQ-2 — How are ACL principals specified?** A `--viewers` option (team/role/user), a config default,
  or the provisioning SA only? What's the safe default when none is given (least-exposure)?
- **OQ-3 — Target Grafana can't set folder ACLs (old version / insufficient token perms).** Refuse to
  provision (fail-closed), or provision + loudly warn that access control could not be applied?
- **OQ-4 — Existing dashboards already in General** (household provisioned earlier) — migrate them to the
  restricted folder on next provision, or leave + document?

---

*v0.3 — Post-planning + lessons hardening. Key discovery: `GrafanaClient` has no folder/permission
support (both to-build); folder-ACL is the load-bearing control, not content redaction;
`tracking_redaction` is secrets-only. Ready for CRP.*
