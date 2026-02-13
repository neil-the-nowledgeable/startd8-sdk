# Artisan Workflow PI-001 Run — Proactive Issue Report

**Simulated run:** `run_artisan_workflow.py --task-filter PI-001`  
**Date:** 2026-02-12  
**Seed:** `artisan-context-seed.json`  
**Project:** wayfinder

---

## Summary

Simulation identified **5 issues** before the workflow completed. Addressing these proactively will reduce noise, cost, and incomplete outputs.

---

## 1. Token Truncation (Design Phase)

**Symptom:**
```
WARNING [startd8.agents.claude] Response from claude-4 was truncated (stop_reason=max_tokens). 
Output tokens: 4096. Consider increasing max_tokens (currently 4096).
```

**Root cause:** PI-001 uses `depth_tier: "standard"` with `max_output_tokens: 4096` in `design_calibration`. The design doc for "Generator module skeleton" (core infrastructure, Jinja registry, orchestration) exceeds 4096 tokens.

**Impact:** Design document is truncated; downstream DESIGN iterations may fail or produce incomplete artifacts.

**Mitigations:**
- **Option A (CLI override):** Use `--design-max-tokens 8192` to override per-task calibration.
- **Option B (per-task):** Regenerate the context seed with `comprehensive` depth tier for PI-001 (8192 tokens) via PlanIngestionWorkflow's SizeEstimator.
- **Option C (seed edit):** Manually edit `artisan-context-seed.json` → `design_calibration.PI-001.max_output_tokens` → `8192`.

**Recommended:** Option A for a quick fix; Option B for a proper re-run of plan ingestion with higher calibration for infrastructure tasks.

---

## 2. Design Section Mismatch (Parser vs. Calibration)

**Symptom:**
```
WARNING [design_documentation] Design document missing section 'API Contracts' in iteration 1
WARNING [design_documentation] Design document missing section 'Security Considerations' in iteration 1
```

**Root cause:** `parse_design_document()` always validates against the full `DesignSection` enum (7 sections). PI-001's calibration uses a reduced set: `["Overview", "Architecture", "Data Model", "Error Handling", "Testing Strategy"]` — omitting "API Contracts" and "Security Considerations". The parser logs warnings even when the calibrated sections intentionally exclude them.

**Impact:** No functional failure; design phase continues. Warnings are noisy and can mislead developers into thinking the doc is incomplete.

**Mitigation:** Fixed in SDK: `parse_design_document()` now accepts `expected_sections` and validates only those when provided. Calibrated section lists from the seed are respected.

---

## 3. OpenTelemetry Export Failures

**Symptom:**
```
WARNING [opentelemetry.exporter.otlp.proto.grpc.exporter] Transient error StatusCode.UNAVAILABLE encountered while exporting traces to localhost:4317, retrying in 1.18s.
ERROR [opentelemetry.exporter.otlp.proto.grpc.exporter] Failed to export traces to localhost:4317, error code: StatusCode.UNAVAILABLE
```

(Same for logs.)

**Root cause:** OTLP exporter is configured to send traces/logs to `localhost:4317`, but no OTel collector is running (e.g., no `docker-compose.loki-stack.yml` or Grafana Agent).

**Impact:** Telemetry is dropped; no functional impact on the workflow. Retries add small latency and log noise.

**Mitigation:** Fixed in SDK: When `STARTD8_OTEL=auto` (default), the SDK now performs a connectivity check before configuring OTLP. If the endpoint is unreachable, it skips OTLP entirely and logs a single INFO message instead of retrying and failing.

**Manual overrides:**
- `STARTD8_OTEL=disabled` — skip OTel entirely.
- `STARTD8_OTEL=enabled` — force OTLP configuration (no pre-flight check).

---

## 4. Provider Registry Duplication

**Symptom:**
```
WARNING [startd8.providers.registry] Overwriting existing provider: anthropic
WARNING [startd8.providers.registry] Overwriting existing provider: openai
... (repeated for ollama, mock, gemini)
```

**Root cause:** Entry points and built-in providers both register the same providers; built-ins overwrote entry-point registrations.

**Mitigation:** Fixed in SDK: `_register_builtin_providers()` now skips registration when a provider is already present (e.g. from entry points), eliminating overwrite warnings. `discover()` is already idempotent (`_discovered` flag).

---

## 5. Workflow Duration

**Observed:** The DESIGN phase alone took ~60+ seconds (one LLM call truncated at 4096 tokens). Full 7-phase run for PI-001 will take several minutes.

**Mitigation:** Use `--stop-after design` for faster design-only validation, or `--timeout 300` to cap total run time.

---

## 6. Multi-File Split Failure (IMPLEMENT Phase)

**Symptom:**
```
ERROR Multi-file split failed: drafter output matched ['src/pkg/module.py'] but not ['src/pkg/__init__.py']
```

**Root cause:** When a task targets multiple files, the LLM drafter must produce a separate fenced code block per file. LLMs commonly omit `__init__.py` (treating it as "just imports") or drop files from high-LOC multi-file tasks due to output truncation.

**Impact:** Missing files cause build failures; downstream tasks that `import` from the package root fail at `REVIEW` or `TEST`.

### Troubleshooting Matrix (Three Questions diagnostic)

| Question | Check | What to look for |
|----------|-------|------------------|
| **1. Is the contract complete?** (Plan Ingestion) | `artisan-context-seed.json` → task's `target_files` | Are all required files listed? Is `__init__.py` present? Did PARSE correctly group files? |
| **2. Was the contract faithfully translated?** (Preflight / DESIGN) | `artisan-context-seed-enriched.json` → `_enrichment.environment_checks` | Do you see `multi_file_split_risk` and `init_py_in_multi_file` warnings? Was `design_calibration.max_output_tokens` sufficient? |
| **3. Was the translated plan faithfully executed?** (IMPLEMENT) | `generation_results.json` → task entry; `workflow-execution-report.json` | Check `multi_file_split.matched_count` vs `target_count`. Check `_gate3_validation` for missing/stubbed files. |

### Defense-in-depth layers (trace backward from symptom)

```
IMPLEMENT output incomplete (symptom)
  └─ Gate 3 (enhanced): _gate3_validation shows missing_on_disk or stubbed_files?
  │    └─ Downstream stubs? (downstream_stubbed ≠ []) → expected, not a failure
  │    └─ Real stubs? (stubbed_files ≠ []) → generation failure, investigate below
  │
  └─ Smart retry gate: was retry skipped? (all unmatched files are downstream)
  │    └─ Yes → correct optimization, downstream stubs are pre-created by Gate 2c
  │    └─ No → retry fired, check Layer 5 below
  │
  └─ Layer 5: retry with role hints fired? (check "retry_used" in metadata)
       └─ Layer 4: extraction heuristic matched __init__.py? (check debug logs)
            └─ Layer 3: __init__.py constraint was in prompt_constraints?
                 └─ Layer 2: MULTI_FILE_OUTPUT_FORMAT had verification checklist?
                      └─ Layer 1: lead spec mentioned all target files?
                           └─ Gate 2c: design-to-implement reconciliation?
                           │    └─ Downstream files pre-stubbed on disk?
                           │    └─ Downstream files excluded from drafter targets?
                           │    └─ DOWNSTREAM FILE STUBS constraint in prompt?
                           │
                           └─ Gate 2b: _multi_file_risk metadata in seed?
                           │    └─ LOC estimation mismatch detected? (Fix 3)
                           │
                           └─ Gate 2a: auto-split oversized tasks (>3 files)?
                                └─ PARSE prompt: did LLM respect max 3-file guidance?

  Review phase guard:
  └─ Downstream stubs excluded from review code body?
  └─ Reviewer NOT penalizing expected stub files?
```

**Mitigations (by severity):**

| Severity | Action |
|----------|--------|
| Quick fix | `ARTISAN_FORCE_IMPLEMENT=1` to retry with all defense layers active |
| Structural fix | Re-run plan ingestion — oversized tasks (>3 files) are now auto-split by Gate 2a |
| Manual fix | Edit `artisan-context-seed.json` — split the multi-file task into single-file tasks with dependencies |
| Prevention | Re-ingest with updated PARSE prompt (now includes file-grouping guidance) |
| Downstream | Gate 2c auto-detects design-designated downstream files and pre-stubs them — no retry wasted |

---

## Quick Command Reference

**Dress rehearsal (recommended for proactive issue detection):**
```bash
./scripts/dress-rehearsal.sh PI-001
# Or with wayfinder paths explicit:
ARTISAN_SEED=~/Documents/dev/wayfinder/out/manifest-generate-ingestion/artisan-context-seed.json \
  ./scripts/dress-rehearsal.sh PI-001
```

**Full run adopting dress-rehearsal artifacts (skips redundant design LLM calls):**
```bash
./scripts/adopt-prior.sh PI-001
# Or wayfinder convenience wrapper:
./scripts/adopt-prior-PI-001.sh
```

**Resume a single-feature run after interruption:**
```bash
ARTISAN_RESUME=1 ./scripts/adopt-prior.sh PI-001
# Or with wayfinder wrapper:
ARTISAN_RESUME=1 ./scripts/adopt-prior-PI-001.sh
```

**Force fresh IMPLEMENT (ignore cached generation_results):**
```bash
ARTISAN_FORCE_IMPLEMENT=1 ./scripts/adopt-prior.sh PI-001
# Or directly:
python3 scripts/run_artisan_workflow.py --seed ... --adopt-prior --force-implement --task-filter PI-001
```

**Run with OTel disabled (cleaner logs):** Scripts set `STARTD8_OTEL=disabled` automatically.

**Design-only run (faster feedback):**
```bash
# Add --stop-after design to run_artisan_workflow.py; see scripts for full usage
```

---

## Files

- **Seed:** `out/manifest-generate-ingestion/artisan-context-seed.json`
- **Output:** `out/manifest-generate-ingestion/artisan-design/`
- **Report:** `workflow-execution-report.json` (after FINALIZE)
