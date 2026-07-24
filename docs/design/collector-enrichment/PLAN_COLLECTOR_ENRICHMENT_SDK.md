# Collector Enrichment — SDK Implementation Plan

**Version:** 1.0 (aligned to REQ v0.3.1)
**Date:** 2026-07-23
**Requirements:** `REQ_COLLECTOR_ENRICHMENT_SDK.md`

Deterministic, $0, bucket-1. Each step is independently testable; steps P1–P5 have no ordering
dependency except that P6 (wiring) needs P3, and P7 (tests) trails each.

---

## P1 — FR-1b: `ServiceHints` per-service business (small)

**Files:** `artifact_generator_models.py`, `artifact_generator_context.py`

1. Add to `ServiceHints` (after `datasource_uids`, keep dataclass field order stable):
   ```python
   # collector_enrichment FR-1b: per-service business context, already resolved
   # (target-over-project, field-by-field) by the ContextCore producer and forwarded on
   # instrumentation_hints[svc].business. Absent ⇒ ""/None ⇒ no enrichment statement.
   criticality: str = ""
   owner: Optional[str] = None
   ```
2. In `extract_service_hints`, before the `ServiceHints(...)` call:
   ```python
   _biz = hint.get("business") or {}
   if not isinstance(_biz, dict):
       _biz = {}
   ```
   and add to the constructor:
   ```python
   criticality=str(_biz.get("criticality") or ""),
   owner=(_biz.get("owner") or None),
   ```
3. **No** project fallback (NR-2). **No** consumer rewiring (NR-1).

**Test:** hint with `business` → fields set; hint without → `""`/`None`; malformed `business` (list) → ignored.

---

## P2 — FR-2: register the artifact type

**File:** `artifact_generator_context.py` (`_ARTIFACT_TYPE_REGISTRY`, ~line 44)

Insert after the `capability_index` / `onboarding_portal` rows:
```python
ArtifactTypeSpec("collector_enrichment", "collector_enrichment",
                 Category.PROJECT.value, Orientation.SYSTEM.value, False, 85),
```
`order=85` places it among project consumers. `requires_declaration=False` (presence-gated in P3/P6).

**Test:** `resolve_artifact_spec("collector_enrichment")` returns a PROJECT/SYSTEM row; `_stamp_taxonomy`
on a `collector_enrichment` result assigns category/orientation.

---

## P3 — FR-3/4/5/6: the emitter

**File:** `artifact_generator_generators.py` (new function + one helper)

1. **Escaping helper** (module-level, near other helpers):
   ```python
   def _ottl_str(s: str) -> str:
       """Go-style double-quoted OTTL literal body. Backslash first, then quote (FR-6)."""
       return s.replace("\\", "\\\\").replace('"', '\\"')
   ```
2. **Provenance hash** (reuse if a canonical hasher exists; else local):
   ```python
   def _business_provenance(rows: list[tuple[str, str, str]]) -> str:
       import hashlib, json
       canon = json.dumps(rows, sort_keys=True, separators=(",", ":"))
       return hashlib.sha256(canon.encode()).hexdigest()
   ```
   where `rows` = the sorted `(service_name, attr, value)` triples (the business subtree).
3. **`generate_collector_enrichment(services, business, report) -> ArtifactResult`:**
   - Build `rows`: for each service, `sel = service.service_name or service.service_id`; if
     `service.criticality`: append `(sel, "criticality", service.criticality)`; if `service.owner`:
     append `(sel, "owner", service.owner)`.
   - **Presence gate:** `if not rows: return ArtifactResult(status="skipped", content="", …)`.
   - **Validate** the built model (P4) — on `CollectorEnrichmentError` return `status="error"`,
     `error_message`, `content=""`.
   - **Sort** rows by `(attr_rank, service_name)` where `attr_rank = {"criticality":0,"owner":1}` (FR-5).
   - **Render** statements: `set(attributes["business.{attr}"], "{_ottl_str(value)}") where `
     `resource.attributes["service.name"] == "{_ottl_str(sel)}"`.
   - **Assemble** the dict (insertion-ordered) exactly matching the reference wrapper (FR-3), dump with
     `yaml.dump(..., default_flow_style=False, sort_keys=False)`.
   - **Header:** `# GENERATED — do not edit …\n# provenance: sha256:{hash}\n\n` prepended to the dump.
   - Return `ArtifactResult(artifact_type="collector_enrichment",
     service_id=business.project_id or "project",
     output_path="collector-enrichment/otelcol-business-enrichment.yaml",
     status="generated", content=header+body)`.

**Note (determinism of the YAML list):** statements are a YAML sequence; order is our sorted `rows`
order — insertion-preserved by `sort_keys=False`. Header hash is computed on the same sorted `rows` so it
is shuffle-invariant.

**Test:** golden output for a 2-service fixture; shuffled-input byte-identity; escaping with `"`/`\` in owner.

---

## P4 — FR-8: fail-fast validation

**File:** new `src/startd8/observability/collector_enrichment_validation.py` (keeps the fail-fast raise
separate from the fail-soft `observability_artifact_checks.py` pattern — different contract).

```python
_CRITICALITY = {"critical", "high", "medium", "low"}

class CollectorEnrichmentError(ValueError): ...

def validate_collector_enrichment(rows, business_services) -> None:
    # rows: list[(service_name, attr, value)]; business_services: set[str] of services that
    # carried any business context (pre-render), to catch "present but zero statements".
    covered = {r[0] for r in rows}
    missing = business_services - covered
    if missing: raise CollectorEnrichmentError(f"services with business context but no statement: {sorted(missing)}")
    for sel, attr, val in rows:
        if not sel or not sel.strip(): raise CollectorEnrichmentError("empty service.name")
        if attr == "criticality" and val not in _CRITICALITY:
            raise CollectorEnrichmentError(f"criticality out of enum: {val!r}")
    seen = [r[0] for r in rows]
    dupes = {s for s in seen if seen.count(s) > 1 and ...}  # duplicate (service, attr) pairs
    # duplicate service.name for the SAME attr is the real error; different attrs on one service is normal
    pairs = [(r[0], r[1]) for r in rows]
    if len(pairs) != len(set(pairs)):
        raise CollectorEnrichmentError("duplicate (service, attr) statement")
```
Call `validate_collector_enrichment(rows, business_services)` inside the generator before serialization.

**Test:** each raise path; a valid rows list passes silently.

---

## P5 — FR-10a/11: semantic parity gate + fixture

**Files:** new `src/startd8/observability/collector_enrichment_parity.py`;
`tests/unit/observability/fixtures/otelcol-business-enrichment.reference.yml` (verbatim copy of the real
reference `transform/business` block).

```python
@dataclass
class ParityResult:
    matches: bool
    only_in_generated: dict
    only_in_reference: dict
    value_mismatch: dict

def _extract_map(cfg_yaml: str) -> dict[str, dict[str, str]]:
    """Parse a collector config → {service.name: {attr: value}} from transform/business.
    Splits `where … == "a" or … == "b"` back into per-service entries (grouping-insensitive)."""
    # yaml.safe_load → processors["transform/business"]["trace_statements"][*]["statements"]
    # regex each: set\(attributes\["business\.(\w+)"\],\s*"((?:[^"\\]|\\.)*)"\)\s+where\s+(.*)
    # from the where-clause, findall resource.attributes\["service.name"\]\s*==\s*"((?:[^"\\]|\\.)*)"
    # unescape \\ and \" back to raw; assign value to each matched service+attr.

def check_collector_enrichment_parity(generated_yaml, reference_yaml) -> ParityResult:
    g, r = _extract_map(generated_yaml), _extract_map(reference_yaml)
    ... symmetric diff over services and per-attr values ...
```

**Test:** parity of the generator's output (fed the Online-Boutique service→business map) vs the fixture
returns `matches == True`; a deliberately altered value yields `value_mismatch`.

---

## P6 — wire into the run

**File:** `artifact_generator.py`, in `generate_observability_artifacts`, near the `capability_index`
block (~line 800), **before** the `_stamp_taxonomy` loop (so the result gets stamped):
```python
try:
    _ce = generate_collector_enrichment(services, business, report)
    if _ce.status != "skipped":
        report.artifacts.append(_ce)
except Exception:
    logger.exception("collector_enrichment generation failed")
```
No `declared`/`owned_elsewhere` gate (presence-gated inside the generator). The existing `_stamp_taxonomy`
loop (`if not _a.category`) stamps it; `_write_artifacts` writes it under `output_dir` on non-dry-run.

**Test:** end-to-end `generate_observability_artifacts` with a business-carrying metadata fixture emits the
file with correct taxonomy; without business context, no file appears (accept 3a).

---

## P7 — tests

`tests/unit/observability/test_collector_enrichment.py`:
- FR-1b extraction (P1) · registry/taxonomy (P2) · emitter golden + shuffle-invariance + escaping (P3) ·
  provenance-hash stability (P4) · validator raise paths (P4) · parity vs fixture (P5) · e2e wiring +
  byte-identical-absence (P6).

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/observability/test_collector_enrichment.py -v`
then the full observability suite to confirm **zero byte-diff** on existing fixtures (SOTTO regression guard).

---

## Risk / rollback

- **Byte regression on existing artifacts** — the only shared-file edits are additive (2 dataclass fields
  with defaults, 1 registry row, 1 wiring block guarded by presence). Full observability suite is the guard.
- **OTTL form drift vs a future Collector version** — the statement form is pinned to the shipped reference;
  the semantic parity gate is the canary if the demo block changes.
- **Reference fixture divergence** — fixture is a verbatim copy; a comment records its source path + that it
  is a non-normative snapshot for parity only.
