# Dashboard Creator Phase 3 Requirements

**Status:** Implemented
**Phase:** 3 — Batch, Layout, Manifest, OTel, ContextCore
**Covers:** DC-108, DC-109, DC-110, DC-111, DC-201, DC-204, DC-205, DC-207

## Phase 2 Validation Context

Phase 2 (Provisioning) was validated before Phase 3 implementation:
- **191 of 193 tests passed** at validation time
- **Bug found:** `test_provisioning.py::_mock_client()` was missing `client.base_url = url` — mock returned a child MagicMock instead of a string. Fix was already applied before Phase 3 started.
- **193/193 green** after fix confirmation.

---

## Requirements

### DC-108: Row Auto-Grouping

**Priority:** P1
**Depends on:** DC-107

Automatically insert `panels.row()` elements to group panels when `PanelSpec.group` is specified.

**Acceptance Criteria:**
1. Panels sharing the same `group` value are preceded by a `panels.row(title=group)` element.
2. Groups are emitted in the order of first appearance.
3. Panels without a `group` are placed before all grouped rows.
4. Row panels have `collapsed: false` by default; `collapsed: true` when the group starts with `"+"` prefix.

**Implementation:** `src/startd8/dashboard_creator/layout.py::auto_group_rows()`

---

### DC-109: GridPos Auto-Layout

**Priority:** P1
**Depends on:** DC-107

Automatically calculate `gridPos` for panels that don't specify explicit positioning.

**Acceptance Criteria:**
1. Panels without `gridPos` are laid out left-to-right, top-to-bottom in a 24-column grid.
2. Default panel size: `{h: 8, w: 12}` (half-width, two per row).
3. Panels with explicit `gridPos` are placed at the specified position; auto-layout fills around them.
4. Row panels span the full width (`w: 24, h: 1`) and reset the Y cursor.

**Implementation:** `src/startd8/dashboard_creator/layout.py::auto_layout()`

---

### DC-110: Dry-Run + Check Mode

**Priority:** P1
**Depends on:** DC-100, DC-105, DC-107

Generate and optionally compile Jsonnet without writing output files or provisioning.

**Acceptance Criteria:**
1. `dry_run=True` generates the Jsonnet source and returns it without writing to disk.
2. `check=True` runs full validation + Jsonnet compilation but writes no files and performs no provisioning.
3. `check` mode exits with code `0` on success, `1` on validation or compilation failure.
4. Dry-run and check modes are mutually exclusive; specifying both raises `ConfigurationError`.

**Implementation:** Already implemented in Phase 1 — `workflow.py::_execute()` lines 294–305 (dry_run) and 353–364 (check).

---

### DC-111: Multi-Dashboard Batch

**Priority:** P1
**Depends on:** DC-100, DC-107

Process a list of DashboardSpec objects with per-dashboard error isolation.

**Acceptance Criteria:**
1. Accepts a list of specs or a directory path containing YAML/JSON spec files.
2. Each dashboard is processed independently; a failure in one does not abort others.
3. Produces a structured run report at `.startd8/reports/dashboard-create-report.json`.
4. Exit-code contract: `0` = all succeeded, `2` = partial success, `1` = all failed.
5. Progress callback emits per-dashboard progress.

**Implementation:** `src/startd8/dashboard_creator/batch.py`

---

### DC-201: ObservabilityManifest Sync

**Priority:** P1
**Depends on:** DC-105, DC-107

Create or update a `DashboardRef` entry in the project's `ObservabilityManifest` after successful dashboard compilation.

**Acceptance Criteria:**
1. Creates a `DashboardRef` with `uid`, `title`, `file_path`, `datasources`, and `metrics_used`.
2. `metrics_used` is populated from `${metrics.*}` references resolved during generation.
3. Appends the `DashboardRef` to `observability-manifest.yaml` without duplicating existing entries (upsert by UID).
4. Tags from `DashboardSpec.tags` are propagated to the `DashboardRef`.
5. Manifest sync is skipped when the manifest file doesn't exist (no error).

**Implementation:** `src/startd8/dashboard_creator/manifest_sync.py`

---

### DC-204: Mixin.libsonnet Auto-Update

**Priority:** P2
**Depends on:** DC-201

Automatically add a new dashboard import to `mixin.libsonnet` when a new `.libsonnet` file is generated.

**Acceptance Criteria:**
1. Adds `'{name}.json': (import 'dashboards/{name}.libsonnet'),` to the `grafanaDashboards+::` block.
2. Does not duplicate existing entries.
3. Preserves the existing formatting and trailing comma style.
4. Skip when `persist_source=False` (no `.libsonnet` written).

**Implementation:** `src/startd8/dashboard_creator/mixin_update.py`

---

### DC-205: OTel Span Emission

**Priority:** P1
**Depends on:** —

Emit OpenTelemetry spans for key workflow operations with custom attributes.

**Acceptance Criteria:**
1. Root span attributes: `dashboard.uid`, `dashboard.title`, `dashboard.panel_count` (set on parent span from WorkflowBase).
2. Child spans: `dashboard_creator.generate`, `dashboard_creator.compile`, `dashboard_creator.persist`, `dashboard_creator.provision`.
3. `dashboard_creator.compile` span includes `compilation.duration_ms` and `compilation.backend`.
4. Error spans set `otel.status_code = ERROR` with the error message and record the exception.
5. Graceful degradation: workflow succeeds without OTel installed (import guarded by try/except).

**Implementation:** `src/startd8/dashboard_creator/workflow.py` — `_child_span()`, `_set_root_span_attrs()`

---

### DC-207: ContextCore Project Context

**Priority:** P2
**Depends on:** DC-200, DC-205

Enrich OTel spans with ContextCore project metadata.

**Acceptance Criteria:**
1. If `.contextcore.yaml` exists (walks up to 3 parent dirs), extract `spec.project.id` and `spec.project.name`.
2. Set `io.contextcore.project.id` and `io.contextcore.project.name` span attributes on the root span.
3. Graceful degradation: if `.contextcore.yaml` is absent or malformed, skip enrichment without error.

**Implementation:** `src/startd8/dashboard_creator/workflow.py` — `_load_contextcore_context()`, `_enrich_span_with_contextcore()`

---

## Traceability Matrix

| Requirement | Criterion # | Implementation File | Test File | Test Class/Method |
|-------------|------------|--------------------|-----------|--------------------|
| DC-108 | 1 | `layout.py::auto_group_rows` | `test_layout.py` | `TestAutoGroupRows::test_row_panels_inserted_before_each_group` |
| DC-108 | 2 | `layout.py::auto_group_rows` | `test_layout.py` | `TestAutoGroupRows::test_groups_emitted_in_first_appearance_order` |
| DC-108 | 3 | `layout.py::auto_group_rows` | `test_layout.py` | `TestAutoGroupRows::test_ungrouped_panels_come_first` |
| DC-108 | 4 | `layout.py::auto_group_rows` | `test_layout.py` | `TestAutoGroupRows::test_collapsed_row_from_plus_prefix` |
| DC-109 | 1 | `layout.py::auto_layout` | `test_layout.py` | `TestAutoLayout::test_three_panels_wrap_to_next_row` |
| DC-109 | 2 | `layout.py::auto_layout` | `test_layout.py` | `TestAutoLayout::test_two_panels_side_by_side` |
| DC-109 | 3 | `layout.py::auto_layout` | `test_layout.py` | `TestAutoLayout::test_explicit_gridpos_preserved` |
| DC-109 | 4 | `layout.py::auto_layout` | `test_layout.py` | `TestAutoLayout::test_row_panel_spans_full_width` |
| DC-110 | 1 | `workflow.py::_execute` | `test_workflow.py` | `TestWorkflowExecution::test_dry_run_returns_jsonnet_source` |
| DC-110 | 2 | `workflow.py::_execute` | `test_workflow.py` | `TestWorkflowExecution::test_check_mode_compiles_but_no_write` |
| DC-110 | 4 | `workflow.py::_custom_validate` | `test_workflow.py` | `TestWorkflowValidation::test_dry_run_and_check_mutually_exclusive` |
| DC-111 | 1 | `batch.py::run_batch` | `test_batch.py` | `TestRunBatch::test_directory_input` |
| DC-111 | 2 | `batch.py::run_batch` | `test_batch.py` | `TestRunBatch::test_exception_isolation` |
| DC-111 | 3 | `batch.py::_persist_report` | `test_batch.py` | `TestRunBatch::test_report_persisted` |
| DC-111 | 4 | `batch.py::BatchReport` | `test_batch.py` | `TestBatchReport::test_exit_code_*` |
| DC-111 | 5 | `batch.py::run_batch` | `test_batch.py` | `TestRunBatch::test_progress_callback` |
| DC-201 | 1 | `manifest_sync.py::build_dashboard_ref` | `test_manifest_sync.py` | `TestBuildDashboardRef::test_builds_with_all_fields` |
| DC-201 | 2 | `manifest_sync.py::extract_metrics_used` | `test_manifest_sync.py` | `TestExtractMetricsUsed::test_*` |
| DC-201 | 3 | `manifest_sync.py::sync_manifest` | `test_manifest_sync.py` | `TestSyncManifest::test_idempotent_resync` |
| DC-201 | 4 | `manifest_sync.py::sync_manifest` | `test_manifest_sync.py` | `TestSyncManifest::test_tags_propagated` |
| DC-201 | 5 | `manifest_sync.py::sync_manifest` | `test_manifest_sync.py` | `TestSyncManifest::test_missing_manifest_skips_without_error` |
| DC-204 | 1 | `mixin_update.py::update_mixin_imports` | `test_mixin_update.py` | `TestUpdateMixinImports::test_adds_entry_to_grafana_dashboards_block` |
| DC-204 | 2 | `mixin_update.py::update_mixin_imports` | `test_mixin_update.py` | `TestUpdateMixinImports::test_duplicate_entry_not_added` |
| DC-204 | 3 | `mixin_update.py::update_mixin_imports` | `test_mixin_update.py` | `TestUpdateMixinImports::test_idempotent_double_call` |
| DC-204 | 4 | `workflow.py::_execute` | `test_workflow.py` | `TestPhase3MixinUpdate::test_mixin_updated_when_persist_source` |
| DC-205 | 1 | `workflow.py::_set_root_span_attrs` | `test_workflow.py` | `TestPhase3OTelSpans::test_workflow_succeeds_without_otel` |
| DC-205 | 2 | `workflow.py::_child_span` | `workflow.py` | Steps 6, 7, 9, 10 wrapped |
| DC-205 | 4 | `workflow.py::_execute` | — | Compile/provision spans set ERROR status |
| DC-205 | 5 | `workflow.py` | `test_workflow.py` | `TestPhase3OTelSpans::test_workflow_succeeds_without_otel` |
| DC-207 | 1 | `workflow.py::_load_contextcore_context` | `test_workflow.py` | `TestPhase3ContextCore::test_load_contextcore_present` |
| DC-207 | 2 | `workflow.py::_enrich_span_with_contextcore` | `workflow.py` | Called after enforce_uid |
| DC-207 | 3 | `workflow.py::_load_contextcore_context` | `test_workflow.py` | `TestPhase3ContextCore::test_load_contextcore_absent` |

## Files Created/Modified

| File | Action | Purpose |
|------|--------|---------|
| `src/startd8/dashboard_creator/layout.py` | **Created** | DC-108, DC-109 |
| `src/startd8/dashboard_creator/mixin_update.py` | **Created** | DC-204 |
| `src/startd8/dashboard_creator/manifest_sync.py` | **Created** | DC-201 |
| `src/startd8/dashboard_creator/batch.py` | **Created** | DC-111 |
| `src/startd8/dashboard_creator/workflow.py` | Modified | DC-205, DC-207, wiring |
| `src/startd8/dashboard_creator/__init__.py` | Modified | New exports |
| `src/startd8/observability/manifest.py` | Modified | Added `tags` to DashboardRef |
| `tests/unit/dashboard_creator/test_layout.py` | **Created** | 13 tests |
| `tests/unit/dashboard_creator/test_mixin_update.py` | **Created** | 6 tests |
| `tests/unit/dashboard_creator/test_manifest_sync.py` | **Created** | 12 tests |
| `tests/unit/dashboard_creator/test_batch.py` | **Created** | 10 tests |
| `tests/unit/dashboard_creator/test_workflow.py` | Modified | 8 new integration tests |
| `tests/unit/dashboard_creator/conftest.py` | Modified | Added `grouped_spec_dict` fixture |
