# CI/CD Capability — Implementation Plan

**Version:** 1.0 (Post-planning pass)
**Date:** 2026-06-21
**Status:** Draft
**Tracks:** `CICD_REQUIREMENTS.md` v0.2

---

## 1. Planning Discoveries (D1–D10)

The planning pass traced every requirement to real source. The two-layer architecture, the
provider/drift/renderer clone, CLI gate invocation, and manifest extensibility all hold. **Five
requirements were misframed or infeasible as written** — captured here and folded into requirements §0.

| # | v0.1 assumption | Code reality (file:line) | Impact |
|---|---|---|---|
| **D1** | `ci_codegen` clones `ScaffoldFileProvider` 1:1 | Cloneable (`provider.py:18-52`), but the ownership marker `_MARKER="# GENERATED from app.yaml"` + `_KIND_RE`/`_MSHA_RE` are scaffold-private (`drift.py:16-18`). Reusing `is_owned_scaffold_file` would make scaffold claim CI files. | Need a **separate** `ci_codegen/drift.py` with marker `# GENERATED from app.yaml (cicd)`. Hashing (`schema_sha256`) is shareable. FR-GEN-2/3. |
| **D2** | Renderer map keyed by `(vendor, kind)` tuple | Drift re-render only threads `manifest_text` (`drift.py:51`); it dispatches by **kind**. Vendor must be **baked into the kind string** (e.g. `cicd-github-validate`) so drift can recover the renderer. | FR-GEN-4 **reframed**: emit-time map may be a tuple, but the on-disk artifact-kind must flatten vendor in. |
| **D3** | CI/CD coherence rows add without restructuring | `evaluate_coherence(manifest, *, has_auth_seam, has_tenant)` (`coherence.py:47-95`) takes only `AppManifest`+2 bools. CI facts (`registry`, `build.enabled`, secrets backend) aren't on `AppManifest`. | FR-COH-1 needs a **signature extension** (new `cicd` kwarg) + new `AppManifest` fields. Wiring point exists (`cli_generate.py:346-376`). |
| **D4** | `secrets/` backend enumerates key **names** for Layer A | **No name-only API.** Protocol exposes `get_all_secrets()→{name:value}` and `get_secret(key)→value` (`protocol.py:63-77`); `local` returns `{}` (`local.py:24-26`). Harvesting names would return empty (local) or **fetch real values into memory** (Doppler) — violating FR-SEC-4. Deny-list `is_dangerous_key()` IS importable (`__init__.py:46`). | **FR-SEC-1 INFEASIBLE as written.** Names must come from the `cicd.secrets` manifest block + the `.env.example` convention (`ANTHROPIC_API_KEY`/`DATABASE_URL`/`DOPPLER_TOKEN`, `renderers.py:264-283`), deny-list-filtered. |
| **D5** | CD smoke boots the deployed artifact via the harness | Harness **boots installed-mode only**: `mode != installed` ⇒ `Stage.BOOT = SKIPPED` `skipped:deployed-needs-db` (`deploy.py:133-141`). No Postgres/`DATABASE_URL` boot path. | **FR-CD-1/2 BLOCKED for deployed apps.** M3 smoke scoped to **installed** apps; deployed smoke = documented skip + harness-prerequisite tracked separately. |
| **D6** | `cicd.registry` reuses `container.*`; Dockerfile is mode-aware | `container.*` = only `dockerfile: bool` (`manifest.py:177`). **No registry concept anywhere** (zero grep hits). Dockerfile **always binds `0.0.0.0`** (`renderers.py:119`); only the comment + `run.sh` are mode-derived. | FR-BLD-1/2 **reframed**: `cicd.registry` is **net-new** (no reuse); "mode-aware Dockerfile" → "optionally-emitted Dockerfile gated by `container.dockerfile`." |
| **D7** | CI runs `pip install startd8 && startd8 …`; coherence is a step | `startd8` IS a console_script (`pyproject.toml:113-114`, v0.4.0, py≥3.9). Gates are real subcommands. **Coherence has NO standalone CLI** — it runs inside `generate backend` (`cli_generate.py:349`). | FR-CI-1 confirmed; **coherence must ride inside `generate cicd`**, no `startd8 coherence` exists. Resolves OQ-1. |
| **D8** | New `generate cicd` / `cicd provision` follow existing registration | Confirmed. `app.add_typer(generate_app, name=…)` (`cli.py:992`); `generate cicd` = `@generate_app.command` sibling of `scaffold` (`cli_generate.py:537`); `cicd provision` = new `cicd_app` Typer + callback (`cli.py:1009` pattern). | FR-GEN-5/FR-PROV-1 confirmed, mechanical. |
| **D9** | A deployment-mode wireframe section exists to mirror | No standalone section; mode is folded into `_scaffold_section` (`plan.py:354-402`). Sections are a fixed tuple (`plan.py:1029-1034`). | FR-COH-3 feasible: add `_cicd_section` + append to tuple + `_ITERATION_BY_SECTION` (`render.py:189`). |
| **D10** | Adding top-level `cicd:` to `app.yaml` is trivial | Parser is **strict/fail-loud**: `_TOP_KEYS` closed set, unknown key ⇒ `raise ValueError` (`manifest.py:16-19,77-79`). An unregistered `cicd:` **breaks every existing `generate` run**. | FR-GEN-1 ordering-critical: add `"cicd"` to `_TOP_KEYS` + strict sub-parse in **M0**, before any manifest carries it. |

---

## 2. Milestones

> Decision: extend the existing `scaffold_codegen` `AppManifest`/parser (not a separate parser),
> because coherence and renderers all consume `AppManifest`. New module `src/startd8/ci_codegen/`.

### M0 — manifest + provider skeleton + VCS hygiene (FR-GEN-1..3, FR-VCS-*)
- **Modify** `scaffold_codegen/manifest.py`: add `"cicd"` to `_TOP_KEYS`; strict `cicd` sub-parse (mirror `deployment` `:98-101`) → `cicd_vendors`, `cicd_registry`, `cicd_environments`, `cicd_build_enabled`, `cicd_secrets`, `cicd_codeowners` on `AppManifest`.
- **Create** `ci_codegen/drift.py`: own `_MARKER="# GENERATED from app.yaml (cicd)"`, `is_owned_cicd_file()`, `cicd_in_sync()`; reuse `schema_sha256`; dispatch `CICD_RENDERERS` by flat vendor-embedded kind (D2).
- **Create** `ci_codegen/provider.py`: `CiCdFileProvider` (`name="cicd"`).
- **Create** `ci_codegen/renderers.py`: `render_gitignore`, `render_gitattributes`, `render_codeowners`, `render_pr_template`; `CICD_RENDERERS`.
- **Create** `ci_codegen/__init__.py`.
- **Modify** `pyproject.toml`: register `cicd = "startd8.ci_codegen.provider:CiCdFileProvider"` under `startd8.contractors.deterministic_providers`.
- **Modify** `cli_generate.py`: `@generate_app.command("cicd")` with `--check` (clone scaffold `:537-602`).

### M1 — GitHub validate job + coherence (FR-CI-*, FR-COH-1/2)
- **Modify** `ci_codegen/renderers.py`: `render_github_validate` → `.github/workflows/validate.yml` running `startd8 generate backend --check`, `generate cicd --check`, `pytest`, `ruff`, `mypy`, `polish check`; `m.python_version`; push+PR triggers.
- **Modify** `scaffold_codegen/coherence.py`: extend `evaluate_coherence` with a `cicd` kwarg; rows — push+`installed`⇒ERROR, `deployed`+build+no-Dockerfile⇒ERROR, `deployed`+push+local-secrets⇒ERROR, CI+no-migrations+`deployed`⇒WARN.
- **Modify** `cli_generate.py`: `generate cicd` calls coherence + fails on ERROR (mirror `:346-376`).

### M2 — build/push + named secrets + supply-chain (FR-BLD-*, FR-SEC-*, FR-SUP-1/2)
- **Modify** `ci_codegen/renderers.py`: `render_github_build` (gated on `m.dockerfile`); SHA-pinned actions; OIDC; **secret refs by name only**, names from `m.cicd_secrets` + `.env.example` convention, filtered via `secrets.is_dangerous_key` (D4). Net-new `cicd.registry` handling (D6).
- **Modify** `scaffold_codegen/coherence.py`: registry/secrets-backend rows.

### M3 — CD smoke (FR-CD-*) — GATED (D5)
- **Modify** `ci_codegen/renderers.py`: `render_github_smoke` → `startd8 deploy local --json`, gate on `LadderResult`.
- **Scope**: smoke for **installed** apps only; `deployed` ⇒ documented skip (harness can't boot Postgres). Deployed smoke = **prerequisite** (new harness deployed-boot in `deploy_harness/deploy.py:133-141`), tracked outside this feature.

### M4 — remaining vendors (FR-GEN-4/6)
- **Modify** `ci_codegen/renderers.py`: gitlab/circleci/azure/bitbucket renderers under vendor-embedded kinds in `CICD_RENDERERS`. No core change (validates D2).

### M5 — Layer B provisioning (FR-PROV-*) — GitHub first
- **Create** `cli_cicd.py`: `cicd_app` Typer + callback; `provision` command, **`--dry-run` default**, idempotent; tokens via `secrets.get_secret`; **refuses on `generate cicd --check` drift** (FR-PROV-5).
- **Create** `ci_provision/github.py`: REST + GHCR side effects (repo create, push, secret register, branch protection).
- **Modify** `cli.py`: `app.add_typer(cicd_app, name="cicd")`.

### Cross-cutting — wireframe (FR-COH-3, after M1)
- **Modify** `wireframe/plan.py`: `_cicd_section(state)` (clone `_scaffold_section`) appended to the section tuple (`:1029-1034`).
- **Modify** `wireframe/render.py`: add `"cicd"` to `_ITERATION_BY_SECTION` (`:189`).

---

## 3. Traceability (FR → milestone)

| Milestone | Requirements |
|---|---|
| M0 | FR-GEN-1, FR-GEN-2, FR-GEN-3, FR-GEN-5, FR-VCS-1..4 |
| M1 | FR-GEN-6, FR-CI-1..4, FR-COH-1, FR-COH-2 |
| M2 | FR-BLD-1..4, FR-SEC-1..4, FR-SUP-1, FR-SUP-2 |
| M3 | FR-CD-1..3 (installed-scoped) |
| M4 | FR-GEN-4, remaining FR-GEN-6 vendors |
| M5 | FR-PROV-1..6 |
| Cross | FR-COH-3, FR-SUP-3/4 (optional) |

---

## 4. Critical Files
- `src/startd8/scaffold_codegen/manifest.py` — `_TOP_KEYS` strict gate + `AppManifest` fields (M0, D10)
- `src/startd8/scaffold_codegen/coherence.py` — matrix + signature extension (M1, D3)
- `src/startd8/scaffold_codegen/drift.py` — template for `ci_codegen/drift.py` (D1)
- `src/startd8/cli_generate.py` — `generate cicd` registration + coherence wiring (M0/M1, D7/D8)
- `src/startd8/deploy_harness/deploy.py:133-141` — installed-only boot (M3 blocker, D5)
- `src/startd8/secrets/{protocol.py,manager.py,__init__.py}` — no name-enum; deny-list (D4)
- `src/startd8/wireframe/plan.py`, `render.py` — wireframe section (D9)
- `pyproject.toml` — entry-point + console_script (D7)

---

*Plan v1.0 — paired with requirements v0.2.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
