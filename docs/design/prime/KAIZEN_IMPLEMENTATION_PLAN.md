# Kaizen for Prime Contractor — Implementation Plan

> **Date:** 2026-03-05
> **Requirements:** [KAIZEN_PRIME_REQUIREMENTS.md](./KAIZEN_PRIME_REQUIREMENTS.md)
> **Design Principle:** [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md)
> **Repositories:** `cap-dev-pipe` (pipeline orchestration), `startd8-sdk` (SDK modules)

---

## Implementation Order

Six layers, each independently shippable. Each layer's steps are ordered by dependency within the layer.

| Layer | Reqs | Files Changed | Effort |
|-------|------|---------------|--------|
| 1: Prime Post-Mortem Parity | KZ-100–102 | 1 cap-dev-pipe file | Small |
| 3: Run Metrics & Archive Index | KZ-300–302 | 1 SDK script + 1 cap-dev-pipe file | Small |
| 4: Cross-Run Aggregation | KZ-400–402 | 1 new cap-dev-pipe script | Medium |
| 2: Prompt-Response Pairing | KZ-200–204 | 3 SDK files + 1 cap-dev-pipe file | Medium-Large |
| 5: Feedback Loop | KZ-500–504 | 1 SDK script + 2 cap-dev-pipe files + 1 SDK module | Large |
| 6: Prompt Quality Correlation | KZ-600–601 | 1 SDK module + 1 new cap-dev-pipe script | Medium |

Layer 1 ships first (zero SDK changes, immediate value). Layer 3 before Layer 4 (index before aggregation). Layer 2 before Layer 6 (prompt data before correlation).

---

## Layer 1: Prime Post-Mortem Parity

**Closes:** K-5a | **Reqs:** REQ-KZ-100, 101, 102
**Changes:** `cap-dev-pipe/run-prime-contractor.sh` only

### Step 1.1 — Add post-mortem invocation (REQ-KZ-100)

**File:** `~/Documents/dev/cap-dev-pipe/run-prime-contractor.sh`
**Insert after:** Line 338 (after the timing/exit-code summary block)
**Insert before:** Line 340 (`exit $EXIT_CODE`)

Add a post-mortem block that invokes the existing standalone runner:

```bash
# ---------------------------------------------------------------------------
# Post-mortem evaluation (Kaizen — REQ-KZ-100)
# ---------------------------------------------------------------------------
echo ""
echo "--- Post-Mortem Evaluation ---"

set +e
python3 "$SDK_ROOT/scripts/run_prime_postmortem.py" \
    --run-dir "$OUTPUT_DIR" \
    --output-dir "$OUTPUT_DIR"
PM_EXIT=$?
set -e

if [ $PM_EXIT -ne 0 ]; then
    echo "  Post-mortem evaluation failed (exit $PM_EXIT) — non-fatal, continuing."
fi
```

**Why this works:**

- `run_prime_postmortem.py` already exists with `--run-dir` auto-discovery (`_discover_artifacts()` finds `prime-result*.json`, seed, queue state)
- `$OUTPUT_DIR` is already computed at line 130 as `$(dirname "${SEED:-$EXPORT_DIR/plan-ingestion}")`
- `$SDK_ROOT` is already set at line 31
- Python venv is already activated at lines 149-156
- Non-fatal: post-mortem failure does not change the contractor exit code
- Preserve the original `EXIT_CODE` from the contractor; the post-mortem step must not override it

**Output files produced:** (by existing `run_prime_postmortem.py`)

- `$OUTPUT_DIR/prime-postmortem-report.json` (REQ-KZ-101)
- `$OUTPUT_DIR/prime-postmortem-summary.md`
- `$OUTPUT_DIR/prime-postmortem-lessons.json`

### Step 1.2 — Add post-mortem summary display (REQ-KZ-102)

**File:** `~/Documents/dev/cap-dev-pipe/run-prime-contractor.sh`
**Insert after:** The post-mortem invocation block from Step 1.1

Mirror the artisan pattern from `run-artisan.sh:364-388`, adapted for prime postmortem field names:

```bash
# Display post-mortem summary (REQ-KZ-102)
PM_REPORT="$OUTPUT_DIR/prime-postmortem-report.json"
if [ -f "$PM_REPORT" ]; then
    echo ""
    echo "  Post-Mortem Evaluation:"
    python3 -c "
import json, sys
try:
    r = json.loads(open('$PM_REPORT').read())
    print(f'    Verdict:  {r[\"aggregate_verdict\"]} (score: {r[\"aggregate_score\"]:.2f})')
    print(f'    Features: {r[\"successful_features\"]}/{r[\"total_features\"]} passed')
    if r.get('failed_features'):
        print(f'    Failed:   {r[\"failed_features\"]}')
    patterns = r.get('cross_feature_patterns', [])
    if patterns:
        print(f'    Patterns: {len(patterns)} cross-feature')
    lessons = r.get('lessons', [])
    if lessons:
        print(f'    Lessons:  {len(lessons)} extracted')
    cost = r.get('cost_summary', {})
    if cost and cost.get('total_usd'):
        print(f'    Cost:     \${cost[\"total_usd\"]:.4f}')
except Exception as exc:
    print(f'    (could not parse report: {exc})', file=sys.stderr)
"
    echo ""
fi
```

**Field name mapping (artisan → prime):**

| Artisan field | Prime field | Notes |
|---------------|-------------|-------|
| `tasks_evaluated` | `successful_features` + `failed_features` | Prime uses feature terminology |
| `total_tasks` | `total_features` | |
| `method` | (not present) | Prime has no `method` field |
| `aggregate_verdict` | `aggregate_verdict` | Same |
| `aggregate_score` | `aggregate_score` | Same |
| `lessons` | `lessons` | Same |

### Step 1.3 — Verify

**Test procedure:**

1. Run a prime contractor pipeline: `./run-atomic.sh --plan ... --requirements ... --route prime`
2. After contractor completes, verify:
   - `prime-postmortem-report.json` exists in `pipeline-output/{project}/run-NNN/plan-ingestion/`
   - `prime-postmortem-summary.md` exists alongside it
   - Console output shows verdict, feature count, and cost
3. Run with a failing task (bad seed) to verify non-fatal behavior

---

## Layer 3: Run Metrics & Archive Index

**Closes:** K-5b | **Reqs:** REQ-KZ-300, 301, 302
**Changes:** `startd8-sdk/scripts/run_prime_postmortem.py` + `cap-dev-pipe/run-atomic.sh`

### Step 3.1 — Add `--emit-metrics` flag to postmortem script (REQ-KZ-300)

**File:** `~/Documents/dev/startd8-sdk/scripts/run_prime_postmortem.py`
**Modify:** Argument parser at lines 100-117, add flag:

```python
parser.add_argument(
    "--emit-metrics",
    action="store_true",
    help="Write kaizen-metrics.json alongside postmortem report.",
)
```

**Add after** line 164 (after `evaluator.evaluate()` returns `report`):

```python
if args.emit_metrics:
    _emit_kaizen_metrics(report, output_dir, run_id=None)
```

**New helper** `_extract_top_root_causes(report)` — extracts from `pipeline_attribution`, not `cross_feature_patterns`:

```python
def _extract_top_root_causes(report: "PrimePostMortemReport") -> list:
    """Aggregate root causes from pipeline_attribution stages."""
    cause_counts: dict[str, int] = {}
    for attr in report.pipeline_attribution:
        for cause, count in attr.root_causes.items():
            cause_counts[cause] = cause_counts.get(cause, 0) + count
    return [
        {"cause": cause, "count": count}
        for cause, count in sorted(cause_counts.items(), key=lambda x: -x[1])[:5]
    ]
```

**Note:** `CrossFeaturePattern` fields are `.description` and `.frequency` (not `.pattern_description`/`.occurrence_count`). The `pipeline_attribution[*].root_causes` (`Dict[str, int]`) provides the per-cause counts needed for `top_root_causes`.

**New function** `_emit_kaizen_metrics(report, output_dir, run_id, run_metadata_path, kaizen_enabled, kaizen_config_source_run)`:

```python
def _emit_kaizen_metrics(
    report: "PrimePostMortemReport",
    output_dir: Path,
    run_id: str | None = None,
    run_metadata_path: Path | None = None,
    kaizen_enabled: bool = False,
    kaizen_config_source_run: str | None = None,
) -> None:
    """Extract standardized metrics from post-mortem report for Kaizen indexing."""
    cost = report.cost_summary
    micro = report.micro_prime_analysis

    # Prefer run-metadata.json as source of truth for run_id/timestamp (REQ-KZ-300)
    meta_run_id = run_id or report.report_id
    meta_timestamp = report.timestamp
    meta_run_dir = ""
    if run_metadata_path and run_metadata_path.is_file():
        try:
            run_meta = json.loads(run_metadata_path.read_text())
            meta_run_id = run_meta.get("run_id", meta_run_id)
            meta_timestamp = run_meta.get("timestamp", meta_timestamp)
            meta_run_dir = run_meta.get("run_dir", "")
        except (json.JSONDecodeError, OSError):
            pass

    metrics = {
        "schema_version": "1.0",
        "run_id": meta_run_id,
        "timestamp": meta_timestamp,
        "run_dir": meta_run_dir,
        "route": "prime",
        "kaizen_enabled": kaizen_enabled,
        "kaizen_config_source_run": kaizen_config_source_run,
        "success_rate": (
            report.successful_features / report.total_features
            if report.total_features > 0
            else 0.0
        ),
        "pass_count": report.successful_features,
        "fail_count": report.failed_features,
        "total_features": report.total_features,
        "total_cost_usd": cost.total_usd if cost else 0.0,
        "cost_per_success_usd": (
            cost.total_usd / max(report.successful_features, 1)
            if cost
            else 0.0
        ),
        "verdict": report.aggregate_verdict,
        "aggregate_score": report.aggregate_score,
        "top_root_causes": _extract_top_root_causes(report),
        "pipeline_attribution": [
            {"stage": a.stage.value, "failures": a.failure_count}
            for a in report.pipeline_attribution
            if a.failure_count > 0
        ],
        "lesson_count": len(report.lessons),
    }

    # Micro Prime stats (if available)
    if micro:
        metrics["micro_prime"] = {
            "total_elements": micro.total_elements,
            "successful_elements": micro.successful_elements,
            "escalated_elements": micro.escalated_elements,
            "tier_distribution": micro.tier_distribution,
            "avg_generation_time_ms": micro.avg_generation_time_ms,
        }
        if micro.total_elements > 0:
            metrics["escalation_rate"] = micro.escalated_elements / micro.total_elements

    metrics_path = output_dir / "kaizen-metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  Kaizen metrics: {metrics_path}")
```

**New CLI flags for `_emit_kaizen_metrics` parameter injection** (Step 3.1 cont.):

```python
parser.add_argument("--run-metadata", type=Path, help="Path to run-metadata.json for run_id/timestamp.")
parser.add_argument("--kaizen-enabled", action="store_true", help="Record that kaizen was active for this run.")
parser.add_argument("--kaizen-source-run", type=str, help="Source run ID from kaizen-config.json.")
```

Then the invocation becomes:

```python
if args.emit_metrics:
    _emit_kaizen_metrics(
        report, output_dir,
        run_id=None,
        run_metadata_path=getattr(args, 'run_metadata', None),
        kaizen_enabled=getattr(args, 'kaizen_enabled', False),
        kaizen_config_source_run=getattr(args, 'kaizen_source_run', None),
    )
```

**Lines of code:** ~80 new lines in `run_prime_postmortem.py`

### Step 3.2 — Update postmortem invocation to emit metrics (REQ-KZ-300)

**File:** `~/Documents/dev/cap-dev-pipe/run-prime-contractor.sh`
**Modify:** The post-mortem invocation added in Step 1.1 — add `--emit-metrics` and metadata flags:

```bash
# Build metadata flags for kaizen metrics (REQ-KZ-300)
PM_EXTRA_FLAGS="--emit-metrics"
RUN_METADATA="$OUTPUT_DIR/../run-metadata.json"
if [ -f "$RUN_METADATA" ]; then
    PM_EXTRA_FLAGS+=" --run-metadata $RUN_METADATA"
fi

# Kaizen state (derive from injected config + NO_KAIZEN)
KAIZEN_CONFIG_PATH="${KAIZEN_CONFIG_PATH:-}"
if [ -n "$KAIZEN_CONFIG_PATH" ] && [ -f "$KAIZEN_CONFIG_PATH" ] && [ "${NO_KAIZEN:-false}" != true ]; then
    PM_EXTRA_FLAGS+=" --kaizen-enabled"
    # Extract source_run for metrics
    KAIZEN_SOURCE_RUN=$(python3 -c "import json; print(json.load(open('$KAIZEN_CONFIG_PATH')).get('source_run',''))" 2>/dev/null || true)
    if [ -n "$KAIZEN_SOURCE_RUN" ]; then
        PM_EXTRA_FLAGS+=" --kaizen-source-run $KAIZEN_SOURCE_RUN"
    fi
fi

python3 "$SDK_ROOT/scripts/run_prime_postmortem.py" \
    --run-dir "$OUTPUT_DIR" \
    --output-dir "$OUTPUT_DIR" \
    $PM_EXTRA_FLAGS
```

### Step 3.3 — Add archive index append to `run-atomic.sh` (REQ-KZ-301)

**File:** `~/Documents/dev/cap-dev-pipe/run-atomic.sh`
**Insert after:** Line 517 (after state archiving block, before the "Atomic Run Complete" banner)

```bash
# ---------------------------------------------------------------------------
# Kaizen: Append run to project index (REQ-KZ-301)
# ---------------------------------------------------------------------------
KAIZEN_METRICS="$RUN_DIR/plan-ingestion/kaizen-metrics.json"
KAIZEN_INDEX="$PROCESS_HOME/pipeline-output/$NAME/kaizen-index.json"

if [ -f "$KAIZEN_METRICS" ]; then
    python3 -c "
import json, sys
from datetime import datetime, timezone
from pathlib import Path

metrics_path = Path('$KAIZEN_METRICS')
index_path = Path('$KAIZEN_INDEX')
run_id = '$RUN_ID'
route = '$ROUTE'
project = '$NAME'

try:
    metrics = json.loads(metrics_path.read_text())

    # Load or initialize index with schema fields (REQ-KZ-301)
    index = {'schema_version': '1.0', 'project': project, 'updated_at': '', 'runs': []}
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text())
        except json.JSONDecodeError:
            pass

    # Idempotency: remove existing entry with same run_id before appending (REQ-KZ-301)
    index['runs'] = [r for r in index.get('runs', []) if r.get('run_id') != run_id]

    # Append entry
    entry = {
        'run_id': run_id,
        'route': route,
        'timestamp': metrics.get('timestamp', ''),
        'kaizen_enabled': metrics.get('kaizen_enabled', False),
        'success_rate': metrics.get('success_rate', 0.0),
        'total_cost_usd': metrics.get('total_cost_usd', 0.0),
        'total_features': metrics.get('total_features', 0),
        'verdict': metrics.get('verdict', ''),
        'run_dir': metrics.get('run_dir', ''),
        'metrics_path': f'{run_id}/plan-ingestion/kaizen-metrics.json',
        'postmortem_path': f'{run_id}/plan-ingestion/prime-postmortem-report.json',
    }
    index['runs'].append(entry)
    index['updated_at'] = datetime.now(timezone.utc).isoformat()

    # Write atomically
    tmp = index_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(index, indent=2), encoding='utf-8')
    tmp.rename(index_path)
    print(f'  Kaizen index updated: {len(index[\"runs\"])} runs indexed')
except Exception as exc:
    print(f'  Kaizen index update failed (non-fatal): {exc}', file=sys.stderr)
"
fi
```

**Why inline Python:** Matches existing patterns in `run-atomic.sh` (e.g., `run-metadata.json` write at line 277, `run-prime-contractor.sh` uses inline Python at lines 88-95 and 166-224). Avoids adding a new script dependency. **Constraint:** Uses only stdlib modules (`json`, `pathlib`, `sys`, `datetime`) per REQ-KZ-301.

### Step 3.4 — Add retention policy flag (REQ-KZ-302)

**File:** `~/Documents/dev/cap-dev-pipe/run-atomic.sh`
**Modify:** Argument parser (lines 65-87), add:

```bash
--kaizen-keep)      KAIZEN_KEEP="$2";           shift 2 ;;
```

**Add default:** `KAIZEN_KEEP=20` to defaults section (line 59 area).

**Add after** the index append block (Step 3.3):

```bash
# Prune old runs if index exceeds retention limit (REQ-KZ-302)
if [ -f "$KAIZEN_INDEX" ] && [ -n "$KAIZEN_KEEP" ]; then
    python3 -c "
import json, shutil, os, sys
from pathlib import Path

index_path = Path('$KAIZEN_INDEX')
base = index_path.parent
keep = int('$KAIZEN_KEEP')

index = json.loads(index_path.read_text())
runs = index.get('runs', [])
# Sort by timestamp to ensure retention is chronological
def _ts(r):
    return r.get('timestamp', '')
runs = sorted(runs, key=_ts)
if len(runs) > keep:
    to_prune = runs[:-keep]
    index['runs'] = runs[-keep:]

    # Resolve latest symlink target before pruning (REQ-KZ-302)
    latest_link = base / 'latest'
    latest_target = None
    if latest_link.is_symlink():
        latest_target = latest_link.resolve().name

    for entry in to_prune:
        run_dir = base / entry['run_id']
        if run_dir.is_dir():
            try:
                shutil.rmtree(run_dir)
                print(f'  Pruned: {entry[\"run_id\"]}')
            except OSError as exc:
                print(f'  WARNING: Failed to prune {entry[\"run_id\"]}: {exc}', file=sys.stderr)

    # Update latest symlink if it pointed to a pruned run
    if latest_target and latest_target in {e['run_id'] for e in to_prune}:
        if index['runs']:
            new_latest = base / index['runs'][-1]['run_id']
            if new_latest.is_dir():
                latest_link.unlink(missing_ok=True)
                latest_link.symlink_to(new_latest.name)
                print(f'  Updated latest -> {index[\"runs\"][-1][\"run_id\"]}')

    tmp = index_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(index, indent=2))
    tmp.rename(index_path)
"
fi
```

### Step 3.5 — Verify

1. Run a prime pipeline, verify `kaizen-metrics.json` appears in `plan-ingestion/`
2. Run a second pipeline, verify `kaizen-index.json` has 2 entries
3. Set `--kaizen-keep 1`, run a third, verify oldest run was pruned

---

## Layer 4: Cross-Run Aggregation

**Closes:** K-2 | **Reqs:** REQ-KZ-400, 401, 402
**Changes:** 1 new file `cap-dev-pipe/run-kaizen-trends.sh`
**Depends on:** Layer 3 (index and metrics files must exist)

### Step 4.1 — Create trend script shell wrapper

**File:** `~/Documents/dev/cap-dev-pipe/run-kaizen-trends.sh` (new)

Thin shell wrapper matching the `run-compare.sh` pattern:

```bash
#!/usr/bin/env bash
# Kaizen cross-run trend analysis (REQ-KZ-400)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/pipeline.env" ]; then
    source "$SCRIPT_DIR/pipeline.env"
fi

: "${PROCESS_HOME:=$SCRIPT_DIR}"
PROJECT="${1:?Usage: $0 <project-name>}"
PIPELINE_BASE="$PROCESS_HOME/pipeline-output/$PROJECT"
KAIZEN_INDEX="$PIPELINE_BASE/kaizen-index.json"

if [ ! -f "$KAIZEN_INDEX" ]; then
    echo "ERROR: No kaizen index found at $KAIZEN_INDEX" >&2
    echo "  Run at least one pipeline with post-mortem enabled first." >&2
    exit 1
fi

python3 "$SCRIPT_DIR/kaizen-trends.py" \
    --index "$KAIZEN_INDEX" \
    --base-dir "$PIPELINE_BASE" \
    --output-dir "$PIPELINE_BASE"
```

### Step 4.2 — Create trend analysis Python script

**File:** `~/Documents/dev/cap-dev-pipe/kaizen-trends.py` (new)

Reads `kaizen-index.json`, loads each run's `kaizen-metrics.json`, and produces:

**Output files:**

- `pipeline-output/{project}/kaizen-trends.json` — machine-readable trend data
- `pipeline-output/{project}/kaizen-trends.md` — human-readable markdown report

**Sections in the trend report:**

1. **Run History Table** — per-run: run_id, route, timestamp, success_rate, cost, verdict
2. **Success Rate Trend** — per-run success_rate with delta from previous run
3. **Cost Trend** — per-run total_cost_usd, cost_per_success_usd, outlier flag (2x average)
4. **Top Failure Root Causes** — aggregated across all runs, sorted by total count (REQ-KZ-401)
5. **Pattern Tracking** — first_seen, last_seen, occurrence_count, resolved flag (REQ-KZ-401)
6. **Improvement Indicators** — consecutive runs with improving/degrading success rate

**Implementation pattern:** Follow `run-compare.sh` report generation structure. Load metrics with skip tracking (REQ-KZ-400):

```python
loaded_runs = []
skipped_runs = []

for entry in index["runs"]:
    metrics_path = base_dir / entry["metrics_path"]
    if not metrics_path.exists():
        skipped_runs.append({"run_id": entry["run_id"], "reason": "metrics file missing"})
        continue
    try:
        metrics = json.loads(metrics_path.read_text())
        loaded_runs.append(metrics)
    except json.JSONDecodeError as exc:
        skipped_runs.append({"run_id": entry["run_id"], "reason": f"invalid JSON: {exc}"})
```

The `skipped_runs` list is included in both the JSON and Markdown output so operators can see if trend data is incomplete.

**Failure pattern persistence (REQ-KZ-401):**

Use the per-run `prime-postmortem-report.json` (not just `top_root_causes`) to accumulate `cross_feature_patterns` across runs:

```python
# Accumulate patterns across runs (from postmortem)
all_patterns: Dict[str, Dict] = {}
for entry in index["runs"]:
    pm_path = base_dir / entry["postmortem_path"]
    if not pm_path.exists():
        skipped_runs.append({"run_id": entry["run_id"], "reason": "postmortem missing"})
        continue
    report = json.loads(pm_path.read_text())
    for p in report.get("cross_feature_patterns", []):
        key = p.get("pattern_type") or p.get("description")
        if not key:
            continue
        if key not in all_patterns:
            all_patterns[key] = {
                "pattern_id": key,
                "first_seen_run": entry["run_id"],
                "last_seen_run": entry["run_id"],
                "occurrence_count": 0,
                "resolved": False,
            }
        all_patterns[key]["last_seen_run"] = entry["run_id"]
        all_patterns[key]["occurrence_count"] += int(p.get("frequency", 0) or 0)
```

Write accumulated patterns to `pipeline-output/{project}/kaizen-patterns.json`.

**Cost outlier detection (REQ-KZ-402):**

```python
costs = [m["total_cost_usd"] for m in runs if m.get("total_cost_usd")]
avg_cost = sum(costs) / len(costs) if costs else 0
for run in runs:
    run["cost_outlier"] = run.get("total_cost_usd", 0) > avg_cost * 2.0
```

**Estimated size:** ~200 lines Python

### Step 4.3 — Verify

1. Run 3+ prime pipelines to build up an index
2. Run `./run-kaizen-trends.sh {project}`
3. Verify `kaizen-trends.md` contains trend table, pattern tracking, cost analysis
4. Verify `kaizen-patterns.json` has accumulated failure patterns

---

## Layer 2: Prompt-Response Pairing

**Closes:** K-1 | **Reqs:** REQ-KZ-200, 201, 202, 203, 204
**Changes:** `startd8-sdk/src/startd8/contractors/prime_contractor.py` + `startd8-sdk/scripts/run_prime_workflow.py` + `startd8-sdk/src/startd8/contractors/protocols.py` + `cap-dev-pipe/run-atomic.sh`
**Depends on:** Layer 1 (post-mortem infrastructure in place)

### Step 2.1 — Factor out prompt persistence (REQ-KZ-203)

**File:** `~/Documents/dev/startd8-sdk/src/startd8/contractors/prime_contractor.py`

Extract the core write logic from `_persist_walkthrough_prompts()` (lines 1779-1823) into a lower-level shared function. The existing method builds prompts AND writes them. Factor into:

1. **`_build_phase_prompts(feature, gen_context)`** — returns a dict of `{filename: content}` pairs for all phases (spec, draft, review). Extracts prompt construction logic.

2. **`_write_prompt_files(output_dir, feature_id, prompts_dict, metadata_dict)`** — writes prompt files + metadata.json to `output_dir/{feature_id}/`. Sanitizes `feature_id` to prevent path traversal (replace `/`, `..`, null bytes) and applies redaction (if configured) before writing. Extracts file writing logic.

Add a small helper:

```python
def _sanitize_feature_id(self, feature_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", feature_id.replace("..", ""))
```

Then `_persist_walkthrough_prompts()` becomes:

```python
def _persist_walkthrough_prompts(self, feature, gen_context):
    prompts = self._build_phase_prompts(feature, gen_context)
    metadata = self._build_prompt_metadata(feature, gen_context)
    wt_dir = Path(self.storage_dir) / "walkthrough" / "prime"
    self._write_prompt_files(wt_dir, feature.id, prompts, metadata)
```

**No behavioral change** to walkthrough mode. This is a pure refactor.

### Step 2.2 — Add prompt persistence during real runs (REQ-KZ-200, 201)

**File:** `~/Documents/dev/startd8-sdk/src/startd8/contractors/prime_contractor.py`
**Method:** `develop_feature()` at line ~1920 (the walkthrough/real-run branch)

Add a kaizen prompt persistence path. In the real-run branch (not walkthrough), after `gen_context` is built and before the LLM call:

```python
# Kaizen prompt capture (REQ-KZ-200)
if getattr(self, '_kaizen_prompts_dir', None) and self._kaizen_redaction_ok:
    try:
        prompts = self._build_phase_prompts(feature, gen_context)
        metadata = self._build_prompt_metadata(feature, gen_context)
        self._write_prompt_files(
            Path(self._kaizen_prompts_dir),
            feature.id,  # sanitized inside _write_prompt_files
            prompts,
            metadata,
        )
    except Exception:
        logger.warning("Kaizen prompt capture failed for '%s'", feature.name, exc_info=True)
```

After **each** LLM phase call returns (spec, draft, review), persist the response for that phase:

```python
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB (REQ-KZ-201 size guard)

def _persist_kaizen_response(self, feature_id: str, phase: str, raw_response: str) -> None:
    """Persist a single phase response alongside its prompt files (REQ-KZ-201)."""
    if not getattr(self, '_kaizen_prompts_dir', None) or not self._kaizen_redaction_ok:
        return
    try:
        safe_id = self._sanitize_feature_id(feature_id)
        resp_dir = Path(self._kaizen_prompts_dir) / safe_id
        resp_dir.mkdir(parents=True, exist_ok=True)

        # Apply redaction if configured (REQ-KZ-204)
        text = self._apply_kaizen_redaction(raw_response)

        # Size guard: truncate and emit sidecar metadata (REQ-KZ-201)
        if len(text.encode("utf-8")) > _MAX_RESPONSE_BYTES:
            original_bytes = len(text.encode("utf-8"))
            text = text[:_MAX_RESPONSE_BYTES] + "\n<!-- TRUNCATED -->\n"
            sidecar = {"original_bytes": original_bytes, "truncated": True}
            (resp_dir / f"{phase}_response.meta.json").write_text(
                json.dumps(sidecar), encoding="utf-8"
            )

        (resp_dir / f"{phase}_response.md").write_text(text, encoding="utf-8")
    except Exception:
        logger.warning("Kaizen response capture failed for '%s' phase '%s'", feature_id, phase, exc_info=True)
```

Then at each phase call site:

```python
# After spec phase:
self._persist_kaizen_response(feature.id, "spec", spec_raw_response)
# After draft phase:
self._persist_kaizen_response(feature.id, "draft", draft_raw_response)
# After review phase:
self._persist_kaizen_response(feature.id, "review", review_raw_response)
```

**Prerequisite:** `GenerationResult` (in `contractors/protocols.py`) must be extended with an optional `raw_response: str | None = None` field, populated by the code generator before the response is parsed. Alternatively, the code generator can stash the raw response in `metadata["raw_response"]`. This must be done for all three phase generators (spec, draft, review).

**Activation:** Set `self._kaizen_prompts_dir` when a `--kaizen` CLI flag or kaizen config is detected. Default: `None` (no overhead).

### Step 2.3 — Add redaction support (REQ-KZ-204)

**File:** `~/Documents/dev/startd8-sdk/src/startd8/contractors/prime_contractor.py`

Add redaction config loading and application:

```python
import re

def _load_kaizen_redaction_config(self) -> tuple[list[re.Pattern], str, bool]:
    """Load redaction rules from .startd8/kaizen-redactions.json or KAIZEN_REDACTIONS env.

    Returns (patterns, replacement, ok). If ok is False, persistence is disabled.
    """
    import os
    config_text = None

    # Env takes precedence
    env_val = os.environ.get("KAIZEN_REDACTIONS")
    if env_val:
        config_text = env_val
    else:
        redaction_path = Path(self.project_root) / ".startd8" / "kaizen-redactions.json"
        if redaction_path.is_file():
            config_text = redaction_path.read_text(encoding="utf-8")

    if config_text is None:
        return [], "[REDACTED]", True  # No config = no redaction needed, persistence OK

    try:
        config = json.loads(config_text)
        patterns = [re.compile(p) for p in config.get("patterns", [])]
        replacement = config.get("replacement", "[REDACTED]")
        return patterns, replacement, True
    except (json.JSONDecodeError, re.error, TypeError) as exc:
        logger.warning(
            "Invalid kaizen redaction config — disabling prompt/response persistence: %s", exc
        )
        return [], "[REDACTED]", False  # ok=False → persistence disabled

def _apply_kaizen_redaction(self, text: str) -> str:
    """Apply redaction patterns to text before writing."""
    for pattern in self._kaizen_redaction_patterns:
        text = pattern.sub(self._kaizen_redaction_replacement, text)
    return text
```

During `__init__()`, if kaizen is enabled:

```python
self._kaizen_redaction_patterns, self._kaizen_redaction_replacement, self._kaizen_redaction_ok = \
    self._load_kaizen_redaction_config()
```

**Fail-closed behavior:** If `_kaizen_redaction_ok` is False, all prompt/response persistence is skipped for the run (Steps 2.2 checks `self._kaizen_redaction_ok`).

### Step 2.4 — Add `--kaizen` flag to `PrimeContractorWorkflow`

**File:** `~/Documents/dev/startd8-sdk/src/startd8/contractors/prime_contractor.py`
**Method:** `__init__()` — add `kaizen: bool = False` parameter

When `kaizen=True`, set a run-isolated directory if run_id is available:

```python
run_id = os.environ.get("RUN_ID") or None
base = Path(self.storage_dir) / "kaizen-prompts"
self._kaizen_prompts_dir = str(base / run_id) if run_id else str(base)
```

If `RUN_ID` is not set, fallback to the legacy path (no run subdir). This keeps behavior deterministic while allowing isolation when available.

**File:** `~/Documents/dev/startd8-sdk/scripts/run_prime_workflow.py`
**Add:** `--kaizen` argparse flag, forwarded to `PrimeContractorWorkflow(kaizen=True)`

### Step 2.5 — Archive prompt directory in `run-atomic.sh` (REQ-KZ-202)

**File:** `~/Documents/dev/cap-dev-pipe/run-atomic.sh`
**Insert after:** Line 517 (after existing state archiving, before kaizen index block from Step 3.3)

```bash
# Archive Kaizen prompts (REQ-KZ-202)
KAIZEN_PROMPTS="$PROJECT_ROOT/.startd8/kaizen-prompts"
if [ -d "$KAIZEN_PROMPTS" ]; then
    if cp -r "$KAIZEN_PROMPTS" "$RUN_DIR/kaizen-prompts"; then
        rm -rf "$KAIZEN_PROMPTS"
        echo "  Archived and removed: kaizen-prompts/"
    else
        echo "  WARNING: Failed to archive kaizen-prompts/ — preserving original" >&2
    fi
fi
```

Follows the pattern of lines 301-306 (archive `.prime_contractor_state.json`) and lines 308-313 (archive `.startd8/state/`). The conditional removal ensures data is preserved on copy failure (REQ-KZ-202 constraint).

### Step 2.6 — Pass `--kaizen` through pipeline

**File:** `~/Documents/dev/cap-dev-pipe/run-prime-contractor.sh`
**Modify:** Pass `--kaizen` to `run_prime_workflow.py` when kaizen is enabled.

Simplest approach: add to `PRIME_CONTRACTOR_EXTRA_ARGS` in `pipeline.env`:

```bash
PRIME_CONTRACTOR_EXTRA_ARGS="--micro-prime --kaizen"
```

Or add an explicit `--kaizen` flag to `run-atomic.sh` that forwards to the contractor args.

**Run-id propagation:** Ensure `RUN_ID` is exported in the environment for the prime contractor process (e.g., in `run-atomic.sh` before invoking `run-prime-contractor.sh`) so prompt persistence can use run-isolated directories.

### Step 2.7 — Verify

1. Run with `--kaizen` enabled
2. Verify `.startd8/kaizen-prompts/{feature_id}/` contains spec/draft/review prompt files + `spec_response.md`, `draft_response.md`, `review_response.md`
3. After `run-atomic.sh` completes, verify prompts archived in `pipeline-output/{project}/run-NNN/kaizen-prompts/`
4. Run in walkthrough mode, compare prompt files — they should be identical (REQ-KZ-203)
5. Create a `.startd8/kaizen-redactions.json` with test patterns, verify redaction is applied in persisted files
6. Create an invalid redaction config, verify persistence is disabled and warning is logged

---

## Layer 5: Feedback Loop

**Closes:** K-3 | **Reqs:** REQ-KZ-500, 501, 502, 503, 504
**Changes:** `startd8-sdk/scripts/run_prime_postmortem.py` + `startd8-sdk/src/startd8/contractors/prime_contractor.py` + `cap-dev-pipe/run-atomic.sh`
**Depends on:** Layer 1, 3 (post-mortem + metrics must exist)

### Step 5.1 — Add suggestion generation to postmortem (REQ-KZ-501)

**File:** `~/Documents/dev/startd8-sdk/scripts/run_prime_postmortem.py`
**Add flag:** `--emit-suggestions`

**New function** `_emit_kaizen_suggestions(report, output_dir)`:

Maps known `RootCause` patterns to concrete config suggestions:

```python
_CAUSE_TO_SUGGESTION = {
    "PHANTOM_IMPORT": {
        "phase": "draft",
        "hint": "Validate all imports exist in the target project before referencing them.",
        "config_key": "prompt_hints",
    },
    "DUPLICATE_IMPORT": {
        "phase": "draft",
        "hint": "Check for existing imports before adding new ones. Deduplicate at file top.",
        "config_key": "prompt_hints",
    },
    "SCOPE_CORRUPTION": {
        "phase": "draft",
        "hint": "Preserve the existing function/class structure. Do not reorganize scopes.",
        "config_key": "prompt_hints",
    },
    # ... map all 16 RootCause values
}
```

For each `cross_feature_pattern` with frequency >= 2, emit a suggestion. Match on `pattern_type` (the structured classification field) rather than substring search on `description` to avoid false positives:

```python
suggestions = []
for pattern in report.cross_feature_patterns:
    if pattern.frequency < 2:
        continue
    # Match on pattern_type (structured field), not description (free text)
    suggestion_template = _CAUSE_TO_SUGGESTION.get(pattern.pattern_type)
    if suggestion_template:
        suggestions.append({
            "pattern": pattern.description,
            "pattern_type": pattern.pattern_type,
            "frequency": pattern.frequency,
            "suggested_action": suggestion_template["hint"],
            "config_key": suggestion_template["config_key"],
            "phase": suggestion_template["phase"],
            "confidence": "high" if pattern.frequency >= 3 else "medium",
            "auto_applicable": False,
        })
```

Wrap in schema envelope (REQ-KZ-501):

```python
output = {
    "schema_version": "1.0",
    "source_run": report.report_id,
    "suggestions": suggestions,
}
suggestions_path = output_dir / "kaizen-suggestions.json"
suggestions_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
```

### Step 5.2 — Define kaizen config schema (REQ-KZ-500)

The kaizen config file lives at `pipeline-output/{project}/kaizen-config.json`. Schema:

```json
{
  "schema_version": "1.0",
  "last_updated": "2026-03-05T14:30:00Z",
  "source_run": "run-003-20260305T1430",
  "prompt_hints": [
    {
      "phase": "draft",
      "hint": "...",
      "source": "...",
      "added": "2026-03-05"
    }
  ],
  "complexity_overrides": {},
  "known_failure_mitigations": []
}
```

This file is **manually curated** from suggestions. The operator reviews `kaizen-suggestions.json`, accepts/rejects, and edits `kaizen-config.json`. Automation comes later (maturity level progression per the design principle).

### Step 5.3 — Add config injection to `run-atomic.sh` (REQ-KZ-502, 503)

**File:** `~/Documents/dev/cap-dev-pipe/run-atomic.sh`
**Add to argument parser:** `--no-kaizen` flag

```bash
NO_KAIZEN=false
# In parser:
--no-kaizen)        NO_KAIZEN=true;               shift ;;
```

**Insert before** the contractor command construction (line 472):

```bash
# Kaizen config injection (REQ-KZ-502)
KAIZEN_CONFIG="$PROCESS_HOME/pipeline-output/$NAME/kaizen-config.json"
if [ -f "$KAIZEN_CONFIG" ] && [ "$NO_KAIZEN" != true ]; then
    echo "  Kaizen config: $KAIZEN_CONFIG"
    export KAIZEN_CONFIG_PATH="$KAIZEN_CONFIG"
    export KAIZEN_ENABLED=true
    EXTRA_CONTRACTOR_ARGS+=(--kaizen-config "$KAIZEN_CONFIG")
fi
export NO_KAIZEN
```

### Step 5.4 — Add `--kaizen-config` to `PrimeContractorWorkflow` (REQ-KZ-502)

**File:** `~/Documents/dev/startd8-sdk/src/startd8/contractors/prime_contractor.py`
**Add to `__init__()`:** `kaizen_config_path: str | None = None`

When set, load and validate the config with fail-open behavior (REQ-KZ-502):

```python
_MAX_HINTS_PER_PHASE = 5

def _load_kaizen_config(self, path: str) -> dict | None:
    """Load and validate kaizen config. Returns None on failure (fail-open)."""
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(config, dict) or config.get("schema_version") != "1.0":
            logger.warning("Kaizen config schema mismatch — ignoring: %s", path)
            return None
        return config
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Kaizen config invalid — proceeding without kaizen: %s", exc)
        return None
```

Apply `prompt_hints` by injecting into `gen_context` during `develop_feature()`, with deduplication and per-phase cap:

```python
if self._kaizen_config and self._kaizen_config.get("prompt_hints"):
    # Deduplicate by content hash and cap per phase (REQ-KZ-502)
    seen_hashes: set[str] = set()
    phase_counts: dict[str, int] = {}
    hints_for_phase: list[str] = []

    for h in self._kaizen_config["prompt_hints"]:
        phase = h.get("phase", "all")
        if phase not in (current_phase, "all"):
            continue
        hint_text = h.get("hint", "")
        content_hash = hashlib.sha256(hint_text.encode()).hexdigest()[:16]
        if content_hash in seen_hashes:
            continue
        seen_hashes.add(content_hash)
        count = phase_counts.get(phase, 0)
        if count >= _MAX_HINTS_PER_PHASE:
            continue
        phase_counts[phase] = count + 1
        hints_for_phase.append(hint_text)

    if hints_for_phase:
        gen_context["kaizen_hints"] = "\n".join(f"- {h}" for h in hints_for_phase)
```

The drafter system prompt or user prompt template then includes `{kaizen_hints}` if present.

**File:** `~/Documents/dev/startd8-sdk/scripts/run_prime_workflow.py`
**Add:** `--kaizen-config PATH` argparse flag, forwarded to workflow.

### Step 5.5 — Add improvement verification to trend script (REQ-KZ-504)

**File:** `~/Documents/dev/cap-dev-pipe/kaizen-trends.py`
**Add section:** For each kaizen config entry with a `source_run`, compare metrics before and after:

```python
if kaizen_config_path.exists():
    config = json.loads(kaizen_config_path.read_text())
    source_run = config.get("source_run")
    if source_run:
        # Find the source run's timestamp for robust comparison (M-3: avoid run_id string ordering)
        source_ts = None
        for r in runs:
            if r["run_id"] == source_run:
                source_ts = r.get("timestamp", "")
                break

        if source_ts:
            before = [r for r in runs if r.get("timestamp", "") <= source_ts]
            # Only kaizen-enabled runs in post-kaizen window (REQ-KZ-504)
            after = [
                r for r in runs
                if r.get("timestamp", "") > source_ts and r.get("kaizen_enabled")
            ]

            if before and after:
                before_avg = mean(r["success_rate"] for r in before)
                after_avg = mean(r["success_rate"] for r in after)
                sr_delta = after_avg - before_avg

                # Cost regression check
                before_cost = mean(r.get("cost_per_success_usd", 0) for r in before if r.get("cost_per_success_usd"))
                after_cost = mean(r.get("cost_per_success_usd", 0) for r in after if r.get("cost_per_success_usd"))
                cost_regression = (
                    before_cost > 0 and after_cost > before_cost * 1.5
                )

                # Classify per acceptance criteria (REQ-KZ-504):
                if len(after) < 2:
                    verdict = "INCONCLUSIVE"
                elif sr_delta >= 0.05:
                    verdict = "IMPROVED"
                elif sr_delta <= -0.05 or cost_regression:
                    verdict = "REGRESSION"
                else:
                    verdict = "INCONCLUSIVE"
```

### Step 5.6 — Verify

1. Run a pipeline, observe `kaizen-suggestions.json` in output
2. Manually create `kaizen-config.json` from suggestions
3. Run next pipeline, verify `--kaizen-config` is passed through
4. Run with `--no-kaizen`, verify config is NOT injected
5. Run `./run-kaizen-trends.sh`, verify improvement verification section present

---

## Layer 6: Prompt Quality Correlation

**Closes:** K-4 | **Reqs:** REQ-KZ-600, 601
**Changes:** `startd8-sdk` (evaluator extension) + 1 new cap-dev-pipe script
**Depends on:** Layer 2 (prompt data must exist), Layer 3 (metrics must exist)

### Step 6.1 — Extend prompt evaluator for real-run prompts (REQ-KZ-600)

**File:** `~/Documents/dev/startd8-sdk/src/startd8/contractors/postmortem.py`

The `WalkthroughPromptEvaluator` already computes requirement/constraint coverage scores. Extend it (or create a lightweight wrapper) to accept a directory of prompt files from kaizen-prompts (identical format to walkthrough).

New function:

```python
def extract_prompt_characteristics(prompt_dir: Path) -> Dict[str, Any]:
    """Extract measurable characteristics from a set of prompt files."""
    chars = {}
    for phase in ("spec", "draft", "review"):
        user_prompt = prompt_dir / f"{phase}_user_prompt.md"
        if user_prompt.exists():
            text = user_prompt.read_text(encoding="utf-8")
            chars[f"{phase}_token_count"] = len(text.split())
            chars[f"{phase}_length"] = len(text)

    # Load metadata for context completeness
    metadata_path = prompt_dir / "metadata.json"
    if metadata_path.exists():
        meta = json.loads(metadata_path.read_text())
        chars["context_key_count"] = len(meta.get("context_keys", []))
        chars["has_existing_files"] = meta.get("has_existing_files", False)
        chars["target_file_count"] = len(meta.get("target_files", []))

    return chars
```

### Step 6.2 — Create correlation script

**File:** `~/Documents/dev/cap-dev-pipe/run-kaizen-correlation.sh` (wrapper) + `kaizen-correlation.py` (new)

For each archived run that has both `kaizen-prompts/` and `kaizen-metrics.json`:

1. Extract prompt characteristics per feature (Step 6.1)
2. Load post-mortem per-feature verdicts from `prime-postmortem-report.json`
3. Join on feature_id
4. Compute correlations:
   - Mean prompt length for PASS vs FAIL features
   - Context key count for PASS vs FAIL
   - `has_existing_files` correlation with success
   - Phase-level prompt size correlation with success

**Statistical method (REQ-KZ-601):** Use Spearman rank correlation. Implement a stdlib-only rank-based calculation; if `scipy` is available it may be used, but do not add new dependencies to `cap-dev-pipe` for this.

**Minimum sample size:** If fewer than 10 feature data points are available across all runs, emit an "insufficient data" section in the report and skip correlation coefficients. The report still includes the raw PASS/FAIL group means for directional insight.

Output: `pipeline-output/{project}/kaizen-correlation.json` + `kaizen-correlation.md`

**Estimated size:** ~200 lines Python (including optional scipy fallback)

### Step 6.3 — Verify

1. Run 2+ pipelines with `--kaizen` (prompts captured)
2. Run `./run-kaizen-correlation.sh {project}`
3. Verify correlation report identifies prompt characteristic differences between PASS/FAIL features

---

## File Change Summary

### cap-dev-pipe (pipeline orchestration)

| File | Change Type | Layers |
|------|------------|--------|
| `run-prime-contractor.sh` | Modify (add ~40 lines post-mortem + metrics) | 1, 3 |
| `run-atomic.sh` | Modify (add ~60 lines: index, archive, config, retention) | 2, 3, 5 |
| `run-kaizen-trends.sh` | New (~15 lines wrapper) | 4 |
| `kaizen-trends.py` | New (~200 lines) | 4, 5 |
| `run-kaizen-correlation.sh` | New (~15 lines wrapper) | 6 |
| `kaizen-correlation.py` | New (~150 lines) | 6 |

### startd8-sdk

| File | Change Type | Layers |
|------|------------|--------|
| `scripts/run_prime_postmortem.py` | Modify (add ~90 lines: `--emit-metrics` with new flags, `--emit-suggestions`) | 3, 5 |
| `src/startd8/contractors/prime_contractor.py` | Modify (refactor prompts ~50 lines, kaizen capture ~60 lines, redaction ~40 lines, config load ~40 lines) | 2, 5 |
| `src/startd8/contractors/protocols.py` | Modify (add `raw_response` field to `GenerationResult`) | 2 |
| `scripts/run_prime_workflow.py` | Modify (add `--kaizen`, `--kaizen-config` flags ~10 lines) | 2, 5 |
| `src/startd8/contractors/postmortem.py` | Modify (add `extract_prompt_characteristics()` ~30 lines) | 6 |

### New artifacts produced per run

| Artifact | Location | Producer |
|----------|----------|----------|
| `prime-postmortem-report.json` | `plan-ingestion/` | Layer 1 |
| `prime-postmortem-summary.md` | `plan-ingestion/` | Layer 1 |
| `prime-postmortem-lessons.json` | `plan-ingestion/` | Layer 1 |
| `kaizen-metrics.json` | `plan-ingestion/` | Layer 3 |
| `kaizen-suggestions.json` | `plan-ingestion/` | Layer 5 |
| `kaizen-prompts/{run_id}/{feature_id}/` | run dir | Layer 2 |
| `kaizen-prompts/{run_id}/{feature_id}/{phase}_response.md` | run dir | Layer 2 |

### New project-level artifacts

| Artifact | Location | Producer |
|----------|----------|----------|
| `kaizen-index.json` | `pipeline-output/{project}/` | Layer 3 |
| `kaizen-patterns.json` | `pipeline-output/{project}/` | Layer 4 |
| `kaizen-trends.json` + `.md` | `pipeline-output/{project}/` | Layer 4 |
| `kaizen-config.json` | `pipeline-output/{project}/` | Layer 5 (manual) |
| `kaizen-correlation.json` + `.md` | `pipeline-output/{project}/` | Layer 6 |

---

## Risk Register

| Risk | Mitigation |
|------|-----------|
| Post-mortem adds latency to prime runs | Post-mortem runs AFTER contractor finishes, before exit. ~5-10s overhead. Non-blocking for code generation. |
| Field name mismatch artisan vs prime postmortem | Step 1.2 uses prime-specific field names (`total_features`, not `tasks_evaluated`). No field name normalization attempted. |
| Prompt persistence slows down real runs | Kaizen prompt capture is opt-in (`--kaizen` flag). File writes are <1ms per feature. Failures caught and logged, never abort the run. |
| Index file corruption on concurrent runs | Atomic write via rename (`.tmp` → final). `run-atomic.sh` is single-threaded per project. Idempotent append prevents duplicates on re-run. |
| Retention pruning deletes valuable data | Default keep=20. Operator-configurable. Pruning only runs from `run-atomic.sh` Phase 5, never mid-run. `latest` symlink updated if target pruned. |
| Kaizen config injection degrades quality | `--no-kaizen` bypass for clean baselines. Config is manually curated, not auto-applied. Trend script verifies improvement. Invalid config is fail-open (warn + skip). |
| Secret leakage via prompt/response files | Redaction rules (REQ-KZ-204) with fail-closed behavior: invalid redaction config disables persistence entirely. Env override (`KAIZEN_REDACTIONS`) for CI/CD. |
| Large LLM responses bloat archive | 2 MB size guard (REQ-KZ-201) with truncation sentinel and sidecar metadata. |
| Retention pruning removes `latest` symlink target | Pruning script checks symlink target and updates to most recent retained run (REQ-KZ-302). |
| Run-id unavailable in SDK process | Fallback to non-run-isolated prompt path; log a debug note. Export `RUN_ID` from `run-atomic.sh` when possible. |
| Concurrent runs for same project race on `kaizen-index.json` | Optional: add a simple file lock (`flock` or lockfile) around index update if concurrent runs are expected. |

---

## Convergent Review — Round R1 (Triaged)

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 19:55 UTC
- **Scope**: Plan quality/robustness alignment with updated Kaizen requirements

### Findings

| ID | Area | Severity | Finding | Fix |
|----|------|----------|---------|-----|
| R1-S1 | Robustness | high | Prompt persistence path is not run-isolated and `feature_id` is not sanitized; risk of collisions and path traversal. | Use run-id subdirectory when available and add `_sanitize_feature_id()`; apply in prompt/response writes. |
| R1-S2 | Correctness | medium | Kaizen metrics flags depend on undeclared env vars; `kaizen_source_run` not passed. | Use `KAIZEN_CONFIG_PATH` from `run-atomic.sh` and pass `--kaizen-enabled` / `--kaizen-source-run` explicitly. |
| R1-S3 | Data Quality | medium | Retention pruning assumes index order; can delete wrong runs if order drifts. | Sort by `timestamp` before pruning; update `latest` accordingly. |
| R1-S4 | Analysis | medium | Trend script uses `top_root_causes` to build patterns, but requirements specify `cross_feature_patterns`. | Load `prime-postmortem-report.json` per run and accumulate `cross_feature_patterns`. |
| R1-S5 | Safety | low | Post-mortem invocation could inadvertently alter exit code semantics. | Explicitly preserve contractor `EXIT_CODE` and keep post-mortem non-fatal. |

### Quick Wins

| ID | Area | Severity | Suggestion |
|----|------|----------|-----------|
| R1-Q1 | Metrics | low | Record `run_dir` in `kaizen-index.json` for easier navigation. |
| R1-Q2 | Concurrency | low | Consider optional file lock for `kaizen-index.json` if parallel runs are expected. |

### Triage Disposition

| ID | Disposition | Applied To | Notes |
|----|------------|------------|-------|
| R1-S1 | **ACCEPTED** | Layer 2 | Run-id isolation + sanitization added |
| R1-S2 | **ACCEPTED** | Layer 3/5 | `KAIZEN_CONFIG_PATH` + source_run passthrough |
| R1-S3 | **ACCEPTED** | Layer 3 | Sort by timestamp before pruning |
| R1-S4 | **ACCEPTED** | Layer 4 | Use postmortem `cross_feature_patterns` |
| R1-S5 | **ACCEPTED** | Layer 1 | Exit-code preservation emphasized |
| R1-Q1 | **ACCEPTED** | Layer 3 | `run_dir` included in index entry |
| R1-Q2 | **DEFERRED** | Risk Register | Optional lock if concurrency becomes a need |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected).
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

---

### Areas Substantially Addressed

(No areas have reached the threshold of 3 accepted suggestions yet.)

### Areas Needing Further Review

- **Interfaces**: 0/3 suggestions accepted (need 3 more)
- **Validation**: 0/3 suggestions accepted (need 3 more)
- **Security**: 0/3 suggestions accepted (need 3 more)
- **Architecture**: 1/3 suggestions accepted (need 2 more)
- **Ops**: 1/3 suggestions accepted (need 2 more)
- **Risks**: 2/3 suggestions accepted (need 1 more)
- **Data**: 2/3 suggestions accepted (need 1 more)

---

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Isolate prompt path per run-id; add `_sanitize_feature_id()` | Antigravity (R1) | Run-id subdir added to kaizen-prompts path; slash/dotdot sanitization in Step 2.2 | 2026-03-05 |
| R1-S2 | Use `KAIZEN_CONFIG_PATH` env var; pass `--kaizen-enabled` and `--kaizen-source-run` explicitly | Antigravity (R1) | Step 5.3 updated to export `KAIZEN_CONFIG_PATH` and `KAIZEN_ENABLED`; Step 3.1 reads them | 2026-03-05 |
| R1-S3 | Sort runs by `timestamp` (not index order) before pruning in retention policy | Antigravity (R1) | Step 3.4 pruning script updated to sort `index["runs"]` by `timestamp` before slicing | 2026-03-05 |
| R1-S4 | Load `prime-postmortem-report.json` per run to accumulate `cross_feature_patterns` (not `top_root_causes`) | Antigravity (R1) | Step 4.2 pattern tracking updated: load full postmortem per run; iterate `cross_feature_patterns` | 2026-03-05 |
| R1-S5 | Preserve contractor `EXIT_CODE` explicitly; keep post-mortem invocation non-fatal | Antigravity (R1) | Step 1.1 updated: `set +e` / `set -e` around PM invocation; exit code restored before `exit` | 2026-03-05 |
| R1-Q1 | Include `run_dir` in `kaizen-index.json` entries for easier navigation | Antigravity (R1) | Step 3.3 index entry updated to include `"run_dir"` field alongside `metrics_path` | 2026-03-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) | | | | |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R2

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 19:01:00 UTC
- **Scope**: Second-pass sweep targeting Interfaces (0/3), Validation (0/3), and Security (0/3) as the highest-priority uncovered areas, plus Architecture (1/3) and Ops (1/3); all 7 areas below substantially-addressed threshold after R1

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | The plan calls `_build_phase_prompts(feature, gen_context)` and `_write_prompt_files(output_dir, feature_id, prompts_dict, metadata_dict)` as new extracted functions but never specifies the return type of `_build_phase_prompts` or the shape of `metadata_dict` — callers in Steps 2.2 and 2.3 therefore have no contract to code against | Without a defined return type for `_build_phase_prompts` (e.g., `dict[str, str]` mapping filename → content) and a defined schema for `metadata_dict` (which keys? are they the same keys that `extract_prompt_characteristics` later looks for in `metadata.json`?), the refactor in Step 2.1 will generate a function boundary that the reader cannot implement without cross-consulting `_persist_walkthrough_prompts()`. More critically, Step 6.1's `extract_prompt_characteristics` reads `context_keys`, `has_existing_files`, and `target_files` from `metadata.json` — but Step 2.1 never states that `_write_prompt_files` writes a `metadata.json` file or what it contains. This is a silent interface contract buried in the existing code path. | Step 2.1 (Layer 2) — add a "Return Types and metadata.json Schema" sub-section: (a) `_build_phase_prompts` returns `dict[str, str]` keyed by filename (`{phase}_user_prompt.md`, `{phase}_system_prompt.md`); (b) `_write_prompt_files` writes `metadata.json` containing at minimum `{"context_keys": list[str], "has_existing_files": bool, "target_files": list[str], "feature_id": str, "timestamp": str}`. Reference this schema from Step 6.1 explicitly. | Unit test: assert the keys in `metadata.json` written by `_write_prompt_files` are a superset of the keys consumed by `extract_prompt_characteristics`. |
| R2-S2 | Interfaces | high | Step 5.4 injects `{kaizen_hints}` into `gen_context`, but the plan never specifies which prompt template consumes this key or how it is rendered — without this, the injection is a no-op that silently succeeds | The plan says "the drafter system prompt or user prompt template then includes `{kaizen_hints}` if present" (Step 5.4, end of code block). This is the most critical integration point in Layer 5 — the entire feedback loop depends on hints actually appearing in the LLM prompt — yet the plan defers the template modification with a vague "or". Which template? Where in the template? What happens if `kaizen_hints` is absent? If the template doesn't have the `{kaizen_hints}` slot, the `gen_context` key is silently ignored and no hint is ever injected. | Step 5.4 — add a "Template Integration" sub-section: specify (a) which prompt template file is modified (e.g., `prompts/lead_contractor.yaml` or the inline system prompt string in `prime_contractor.py`), (b) where `{kaizen_hints}` is inserted (e.g., after the constraints block), and (c) the conditional rendering pattern: only the `kaizen_hints` block appears if `gen_context.get("kaizen_hints")` is non-empty. | Integration test: run a pipeline with a known config, inspect the captured `draft_user_prompt.md` and assert the hint text appears verbatim in the prompt. |
| R2-S3 | Security | high | Step 2.2's redaction (REQ-KZ-204) is described in the requirements but the plan's implementation steps never specify WHERE in the write pipeline redaction is applied — the code in Step 2.2 calls `_write_prompt_files(...)` and `(resp_dir / "draft_response.md").write_text(raw, ...)` with no mention of redaction | The risk register lists "Secret leakage via prompt/response files" as mitigated by REQ-KZ-204, but the plan's implementation steps for Layer 2 (Steps 2.1–2.6) contain zero references to redaction. Step 2.2's code snippet writes `raw` directly to disk. The redaction logic must be applied before `write_text` — but where is this called? In `_write_prompt_files`? In a wrapper? At the point of response capture? The plan leaves this unimplemented. The requirements document specified the redaction contract precisely; the plan does not translate it into an implementation step. | Step 2.2 — add a "Redaction Callsite" paragraph: before calling `_write_prompt_files(...)` and before writing `{phase}_response.md`, apply `_apply_redaction(content, redaction_config)` where `redaction_config` is loaded once at workflow init (from `.startd8/kaizen-redactions.json` or `KAIZEN_REDACTIONS` env). If `redaction_config` is None, pass content through unchanged. If loading fails, disable persistence for the run (fail-closed, per REQ-KZ-204). | Unit test: confirm that a prompt containing a string matching a configured redaction pattern is replaced before `write_text` — and that writing never occurs when redaction config is invalid. |
| R2-S4 | Validation | high | None of the Layer verification steps (Steps 1.3, 2.6, 3.5, 4.3, 5.6, 6.3) specify failure cases — every verification step only describes the happy path | A verification plan that only tests success cases is incomplete. Each layer has specific failure modes that are explicitly governed by requirements (e.g., post-mortem failure must be non-fatal for Layer 1, invalid redaction config must disable persistence for Layer 2, invalid `kaizen-config.json` must proceed without kaizen for Layer 5). The verification steps do not include a single negative test ("verify that X does NOT happen when Y fails"). This creates a gap between the requirements' robustness constraints and the plan's verification evidence — an implementer completing all verification steps could still have broken failure handling. | Each Layer verify step — add 1–2 negative test cases per layer: e.g., Step 1.3 add "kill the SDK during post-mortem and verify the pipeline exits with the original contractor exit code"; Step 2.6 add "run with an invalid `KAIZEN_REDACTIONS` value and verify no prompt files are written"; Step 5.6 add "pass a malformed `kaizen-config.json` and verify the run proceeds without hints". | Run each negative test case; assert that the failure mode behavior matches the requirement constraint (non-fatal, fail-closed, etc.). |
| R2-S5 | Validation | medium | The File Change Summary (lines 1101–1118) itemizes line-count estimates for each change, but these estimates have no acceptance criteria — there is no check that the implemented changes stay within the documented scope | The plan estimates "+40 lines" for `run-prime-contractor.sh`, "+60 lines" for `run-atomic.sh`, "~90 lines" for `run_prime_postmortem.py`, etc. These are useful as scope signals, but if an implementation grows to 200 lines where the plan said 40, there is no mechanism to flag scope creep or mandate a plan revision. This is particularly risky for `prime_contractor.py` which is already ~2000 lines — adding 190 lines of kaizen code without a structural boundary (e.g., a mixin, a separate module) may make the file unnavigable. | File Change Summary section — add a "Scope Guards" note: (a) if any single change exceeds 1.5x the estimated line count, it signals a plan deviation requiring review; (b) kaizen-specific logic in `prime_contractor.py` (capture, redaction, config injection) should be grouped into a `KaizenMixin` or helper class, not scattered inline; (c) the estimate is a target, not a budget — over-engineering should be flagged as eagerly as under-engineering. | After implementation, run `git diff --stat` against each modified file and compare line counts to the File Change Summary table. |
| R2-S6 | Architecture | high | Step 5.1's `_CAUSE_TO_SUGGESTION` dict maps `RootCause` pattern types to prompt hints, but the dict is defined as a module-level constant with only 3 of 16 `RootCause` values filled in (and a `# ... map all 16 RootCause values` comment) — the plan provides no guidance on how the remaining 13 mappings should be derived or validated | When an implementer sees `# ... map all 16 RootCause values`, they have three options: (a) guess at hints for all 16, (b) leave the unmapped causes without suggestions (silent no-op for those patterns), or (c) add a fallback suggestion for unmapped causes. The plan doesn't specify which is correct. More critically, if `pattern.pattern_type` is a value NOT in `_CAUSE_TO_SUGGESTION`, the lookup returns `None` and the suggestion is silently skipped — the plan's code path already handles this (`if suggestion_template:`), but the requirements say patterns should produce suggestions. The gap between "16 root causes" and "3 mapped examples" is an implementation hole that will produce incorrect behavior for 13 of 16 pattern types on day one. | Step 5.1 — add a "Completing the Mapping" sub-section listing all 16 `RootCause` enum values from `prime_postmortem.py` and their corresponding prompt hint and phase, or explicitly documenting that unmapped causes produce no suggestion (and noting this as a known limitation). Also add a runtime warning log when a pattern is skipped because its type has no mapping. | Unit test: for each `RootCause` value that appears in `_CAUSE_TO_SUGGESTION`, assert a suggestion is produced. For values NOT mapped, assert a warning is logged and no suggestion is emitted (explicit no-op, not silent). |
| R2-S7 | Architecture | medium | Step 3.3's inline Python for the `kaizen-index.json` append uses `f-string` interpolation of shell variables (`'$KAIZEN_METRICS'`, `'$RUN_ID'`) directly into a Python heredoc — this pattern fails silently if `RUN_ID` contains special characters (spaces, quotes, shell metacharacters) or if the path contains single quotes | The plan uses the same pattern as the existing `run-atomic.sh` inline Python snippets (noted as justification in Step 3.3). However, the `RUN_ID` value is user-influenced (derived from a timestamp + project name), meaning an unusual project name like `my project` or `O'Brien's` would produce syntactically broken Python that `python3 -c` silently executes as a partial script. The correct fix is to pass shell values as argv arguments to the inline Python (`sys.argv[1]`) or as environment variables (`os.environ["RUN_ID"]`), never via f-string interpolation into source code. | Step 3.3 and Step 3.4 — replace shell-variable interpolation in inline Python with `os.environ` reads: set `os.environ["KAIZEN_METRICS"] = "$KAIZEN_METRICS"` in bash (safe, as it's an env var assignment, not source interpolation) and read `metrics_path = Path(os.environ["KAIZEN_METRICS"])` inside the Python block. Apply this pattern consistently to all inline Python snippets in Steps 3.3, 3.4, and 5.3. | Test: create a project with a name containing a space and single quote; run a pipeline; verify the index is written correctly and Python doesn't crash with a SyntaxError. |
| R2-S8 | Ops | medium | The plan specifies `"kaizen-config.json"` at `pipeline-output/{project}/` but `run-atomic.sh`'s injection step (Step 5.3) sets `KAIZEN_CONFIG` to `"$PROCESS_HOME/pipeline-output/$NAME/kaizen-config.json"` — the `$NAME` variable is never defined in the plan and may differ from the `{project}` placeholder used throughout the rest of the document | The plan consistently uses `{project}` as the project identifier in artifact paths (e.g., `pipeline-output/{project}/kaizen-index.json`). Step 5.3 introduces `$NAME` without defining it — readers must infer from `run-atomic.sh`'s argument parser that `$NAME` is the `--name` argument. If `$NAME` and `--project` mean different things in `run-atomic.sh` (or if a future refactor renames the variable), the config path silently becomes wrong. | Step 5.3 — add a one-line note: "`$NAME` is the `--name` argument passed to `run-atomic.sh`, equivalent to `{project}` used throughout this document." Also align all path references in the plan to consistently use either the variable name or the placeholder, with a mapping table at the start of the section. | Code review: verify that every path constructed in Steps 3.3, 3.4, 5.3 uses `$NAME` consistently and matches the `pipeline-output/{project}/` layout described in the requirements. |
| R2-S9 | Security | medium | Step 2.2's response size guard (REQ-KZ-201, 2 MB limit) truncates large LLM responses and writes a sidecar `{phase}_response.meta.json`, but the plan's code never checks whether the response itself is a binary payload (e.g., base64-encoded image data) before calling `.write_text()`, which will raise `UnicodeDecodeError` on non-UTF-8 content | The `raw` variable in Step 2.2 comes from `getattr(result, 'raw_response', None) or result.metadata.get("raw_response")`. LLM APIs can return non-UTF-8 bytes in error responses or in multimodal contexts. `.write_text(raw, encoding="utf-8")` will raise if `raw` contains non-UTF-8 sequences. More subtly, if `raw` is already a `bytes` object rather than a `str` (possible depending on how the code generator returns it), `write_text` will raise `TypeError`. The plan should specify the type contract for `raw_response` and add defensive handling. | Step 2.2 — add a "Type and Encoding Guard" note: `raw_response` MUST be `str | None` (not `bytes`); the code generator is responsible for decoding. Before writing, apply`raw = raw.encode("utf-8", errors="replace").decode("utf-8")` to sanitize non-UTF-8 sequences (replacing them with `?` to avoid losing the response structure). Document this as a lossy fallback. | Unit test: set `raw_response` to a string containing a non-UTF-8 byte sequence; assert the response file is written without raising, and the written content contains the `?` replacement character. |
| R2-S10 | Ops | low | The plan has two separate `run-atomic.sh` modification blocks for Phase 5 post-run steps (Step 2.4 for kaizen-prompts archiving, Step 3.3 for index append, Step 3.4 for pruning, Step 5.3 for config injection) — but none of them specify the ORDER these blocks appear relative to each other in the final file | `run-atomic.sh` is a sequential shell script. The order of the four Phase 5 additions matters: (a) prompt archiving (Step 2.4) must happen BEFORE index append (Step 3.3), because the index entry's `metrics_path` references files that must exist; (b) config injection (Step 5.3) must happen BEFORE the contractor command is constructed, which is in Phase 2 — not Phase 5 at all; (c) pruning (Step 3.4) must happen AFTER indexing (Step 3.3). Without an explicit sequencing diagram or ordered insertion list, an implementer adding these blocks in document-order will produce a broken pipeline on the first run. | New "Phase 5 Insertion Order" sub-section (after the File Change Summary) — specify the exact ordered sequence of additions in `run-atomic.sh`: (1) config injection goes into Phase 2 (before contractor invocation); (2) prompt archiving (Step 2.4) → (3) metrics extraction trigger (Step 3.2) → (4) index append (Step 3.3) → (5) retention pruning (Step 3.4), all in Phase 5. | Implementation walkthrough: annotate the final `run-atomic.sh` diff with phase labels and verify the order matches this specification. |

#### Review Round R3

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 20:20:00 UTC
- **Scope**: Third-pass sweep focused on Interfaces (0/3), Security (0/3), Validation (0/3), plus Data/Ops edge cases

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Interfaces | high | Avoid a breaking change to `GenerationResult` when capturing raw responses. Use `metadata["raw_response"]` (no signature change) or migrate to a `dataclass` with defaults and update all call sites in one commit. | `GenerationResult` is a `NamedTuple`; adding a field changes the constructor signature and will break positional instantiations across the codebase. The plan doesn’t list a compatibility strategy or enumerate call sites to update. | Step 2.2 (raw response capture) + `contractors/protocols.py` change — add a "Compatibility Strategy" subsection and a checklist of call sites to update. | Unit test: scan for `GenerationResult(` instantiations and assert all call sites pass the new field (if migrating), or confirm raw response is present in `metadata` with no signature change. |
| R3-S2 | Security | medium | Write kaizen artifacts with restrictive permissions (files `0o600`, directories `0o700`, or `umask 077`) to reduce inadvertent exposure. | Redaction reduces leakage risk but prompts/responses can still contain sensitive context. Default permissions may be group/world readable on shared systems. | Step 2.2 (prompt/response writes), Step 3.1 (`kaizen-metrics.json`), Step 5.1 (`kaizen-suggestions.json`), Step 4.2 (`kaizen-trends.json`). | Integration test: run with kaizen enabled; assert file modes for prompt/response/metrics are not group/world readable. |
| R3-S3 | Data | medium | Version and timestamp downstream outputs: add `schema_version` and `generated_at` to `kaizen-trends.json`, `kaizen-patterns.json`, and `kaizen-correlation.json`. | Metrics/index files are versioned; downstream outputs are not. Without version metadata, future schema changes will silently break consumers. | Step 4.2 (`kaizen-trends.py` / `kaizen-patterns.json`) and Step 6.2 (`kaizen-correlation.py`). | Unit test: assert `schema_version` and `generated_at` exist in each output JSON. |
| R3-S4 | Ops | medium | Clamp `KAIZEN_KEEP` to safe bounds (e.g., min 5, max 200) and treat `0` as minimum to avoid wiping the index. | The retention policy trusts user input. `KAIZEN_KEEP=0` would prune all runs; very large values can bloat the index and slow inline Python. | Step 3.4 retention policy — add clamp logic and warnings. | Integration test: set `KAIZEN_KEEP=0` and verify index remains non-empty; set a huge value and verify clamping. |
| R3-S5 | Validation | medium | Add a negative test for partial postmortem data in `_emit_kaizen_metrics` (e.g., `pipeline_attribution=None`, `micro_prime_analysis=None`) to ensure metrics emission still succeeds. | The plan assumes `pipeline_attribution` and `micro_prime_analysis` are present; partial prime runs may omit them, causing `AttributeError` and skipping metrics. | Step 3.1 verification — add a unit test with a mock `PrimePostMortemReport` missing attribution/analysis fields; expect valid JSON with empty arrays. | Unit test: assert `kaizen-metrics.json` writes with `"pipeline_attribution": []` and no exceptions. |
