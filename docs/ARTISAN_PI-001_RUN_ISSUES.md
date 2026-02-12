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
- **Option A (per-task):** Regenerate the context seed with `comprehensive` depth tier for PI-001 (8192 tokens) via PlanIngestionWorkflow's SizeEstimator.
- **Option B (global):** Add `--design-max-tokens 8192` to `run_artisan_workflow.py` (would require SDK change; not currently supported).
- **Option C (seed edit):** Manually edit `artisan-context-seed.json` → `design_calibration.PI-001.max_output_tokens` → `8192`.

**Recommended:** Option C for a quick fix; Option A for a proper re-run of plan ingestion with higher calibration for infrastructure tasks.

---

## 2. Design Section Mismatch (Parser vs. Calibration)

**Symptom:**
```
WARNING [design_documentation] Design document missing section 'API Contracts' in iteration 1
WARNING [design_documentation] Design document missing section 'Security Considerations' in iteration 1
```

**Root cause:** `parse_design_document()` always validates against the full `DesignSection` enum (7 sections). PI-001's calibration uses a reduced set: `["Overview", "Architecture", "Data Model", "Error Handling", "Testing Strategy"]` — omitting "API Contracts" and "Security Considerations". The parser logs warnings even when the calibrated sections intentionally exclude them.

**Impact:** No functional failure; design phase continues. Warnings are noisy and can mislead developers into thinking the doc is incomplete.

**Mitigation:** SDK fix: `parse_design_document()` should accept and validate only against `context.sections` when provided, not the full enum. Until fixed, these warnings can be ignored for PI-001.

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

**Mitigations:**
- **Disable OTel:** `STARTD8_OTEL=disabled` before running.
- **Start collector:** `docker compose -f docker-compose.loki-stack.yml up -d` (if available in the SDK repo).
- **Use HTTP endpoint:** `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` if you have an HTTP OTLP receiver.

**Recommended:** `STARTD8_OTEL=disabled` for local runs when you don't need Grafana/Tempo.

---

## 4. Provider Registry Duplication

**Symptom:**
```
WARNING [startd8.providers.registry] Overwriting existing provider: anthropic
WARNING [startd8.providers.registry] Overwriting existing provider: openai
... (repeated for ollama, mock, gemini)
```

**Root cause:** `ProviderRegistry.discover()` is called multiple times (e.g., from design phase, plan ingestion, or other entry points). Each call re-registers providers, overwriting existing ones.

**Impact:** Cosmetic; no functional impact. Suggests redundant discovery in the codebase.

**Mitigation:** SDK fix: Make `ProviderRegistry.discover()` idempotent (skip if already discovered) or centralize discovery to a single entry point. Until fixed, safe to ignore.

---

## 5. Workflow Duration

**Observed:** The DESIGN phase alone took ~60+ seconds (one LLM call truncated at 4096 tokens). Full 7-phase run for PI-001 will take several minutes.

**Mitigation:** Use `--stop-after design` for faster design-only validation, or `--timeout 300` to cap total run time.

---

## Quick Command Reference

**Run with OTel disabled (cleaner logs):**
```bash
STARTD8_OTEL=disabled python3 ~/Documents/dev/startd8-sdk/scripts/run_artisan_workflow.py \
  --seed /Users/neilyashinsky/Documents/dev/wayfinder/out/manifest-generate-ingestion/artisan-context-seed.json \
  --output-dir /Users/neilyashinsky/Documents/dev/wayfinder/out/manifest-generate-ingestion/artisan-design \
  --task-filter PI-001
```

**Increase design tokens (edit seed first):**
```bash
# Edit artisan-context-seed.json: design_calibration.PI-001.max_output_tokens → 8192
# Then run as above.
```

**Design-only run (faster feedback):**
```bash
... --task-filter PI-001 --stop-after design
```

---

## Files

- **Seed:** `out/manifest-generate-ingestion/artisan-context-seed.json`
- **Output:** `out/manifest-generate-ingestion/artisan-design/`
- **Report:** `workflow-execution-report.json` (after FINALIZE)
