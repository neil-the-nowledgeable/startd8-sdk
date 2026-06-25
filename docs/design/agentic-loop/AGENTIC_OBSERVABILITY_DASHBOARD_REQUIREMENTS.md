**Dashboard UID**: `cc-agentic-loop-observability`
**Title**: Agentic Loop Observability

## 1. Dashboard Purpose & Audience

**Dashboard-Specific Question**: Are agentic-loop runs completing successfully, efficiently, and
within cost — and when they don't, why?

Operational visibility into `AgenticSession` runs: outcome mix, token/cost spend, efficiency
(turns/tools per run), and the failure/safety modes (budget stops, context-overflow + compaction,
repeated-call breaks). All panels derive from the `agentic.session` span and its child spans
registered in the observability span manifest by FR-CC3 (`collect_span_descriptors()`).

**Target Audience**: SDK operators and engineers running the agentic loop in production.

> **RESOLVABILITY-PENDING:** no live `agentic.session` spans flow yet (new capability) and no
> spanmetrics connector derives `agentic.*` metrics — queries must be re-verified to return non-zero
> series once real runs land (the "100% coverage / 0 series" failure mode the lesson gates out).

## 2. Data Sources & Metrics

Data source is **Tempo (TraceQL metrics)**. TraceQL attribute access uses the `span.` prefix (a bare
name silently returns empty).

| Metric | Type | Labels | Source |
|--------|------|--------|--------|
| `agentic.session` (span) | trace | span.agentic.stop_reason, span.agentic.turns, span.agentic.total_tokens, span.agentic.total_cost_usd, span.gen_ai.request.model, span.gen_ai.usage.input_tokens, span.gen_ai.usage.output_tokens, span.io.contextcore.project.id | startd8 agentic loop (FR-CC3) |
| `agentic.tool_call` (span) | trace | span.agentic.tool, span.agentic.tool_ok | startd8 agentic loop |
| `agentic.compaction` (span) | trace | span.agentic.compaction_attempt | startd8 agentic loop |

## 3. Time Range & Refresh

- **Default time range**: now-6h to now
- **Auto-refresh**: 1m
- **Timezone**: Browser

## 4. Panels

### Row 1: Run health (y=0)

#### Panel 1: Runs (total)
- **Type**: stat
- **PromQL**: `{ name = "agentic.session" } | count_over_time()`
- **Grid position**: h=5 w=6 x=0 y=0
- **Field config**: unit=short, threshold=blue(0)
- **Options**: colorMode=value, reduceOptions=sum
- **Description**: Total agentic runs over the range.

#### Panel 2: Success rate (completed)
- **Type**: gauge
- **PromQL**: `{ name = "agentic.session" && span.agentic.stop_reason = "completed" } | count_over_time()`
- **Grid position**: h=5 w=6 x=6 y=0
- **Field config**: unit=percentunit, min=0, max=1, threshold=red(0) yellow(0.7) green(0.9)
- **Description**: Share of runs that reached the `completed` stop_reason.

#### Panel 3: Outcome breakdown
- **Type**: piechart
- **PromQL** (1 target):
  - **A**: `{ name = "agentic.session" } | count_over_time() by (span.agentic.stop_reason)` → `{{span.agentic.stop_reason}}`
- **Grid position**: h=10 w=12 x=12 y=0
- **Field config**: unit=short
- **Options**: pieType=donut, legend=table+right with value+percent

#### Panel 4: Runs over time (by outcome)
- **Type**: timeseries
- **PromQL** (1 target):
  - **A**: `{ name = "agentic.session" } | rate() by (span.agentic.stop_reason)` → `{{span.agentic.stop_reason}}`
- **Grid position**: h=8 w=12 x=0 y=5
- **Field config**: unit=short

### Row 2: Cost & tokens (y=13)

#### Panel 5: Total cost (USD)
- **Type**: stat
- **PromQL**: `{ name = "agentic.session" } | sum_over_time(span.agentic.total_cost_usd)`
- **Grid position**: h=5 w=6 x=0 y=13
- **Field config**: unit=currencyUSD, threshold=blue(0)
- **Options**: colorMode=value, reduceOptions=sum

#### Panel 6: Cost over time (by model)
- **Type**: timeseries
- **PromQL** (1 target):
  - **A**: `{ name = "agentic.session" } | sum_over_time(span.agentic.total_cost_usd) by (span.gen_ai.request.model)` → `{{span.gen_ai.request.model}}`
- **Grid position**: h=8 w=9 x=6 y=13
- **Field config**: unit=currencyUSD

#### Panel 7: Tokens in / out
- **Type**: timeseries
- **PromQL** (2 targets):
  - **A**: `{ name = "agentic.session" } | sum_over_time(span.gen_ai.usage.input_tokens)` → `input`
  - **B**: `{ name = "agentic.session" } | sum_over_time(span.gen_ai.usage.output_tokens)` → `output`
- **Grid position**: h=8 w=9 x=15 y=13
- **Field config**: unit=short

### Row 3: Efficiency & safety modes (y=21)

#### Panel 8: Turns per run (p50 / p95)
- **Type**: timeseries
- **PromQL** (2 targets):
  - **A**: `{ name = "agentic.session" } | quantile_over_time(span.agentic.turns, 0.5)` → `p50`
  - **B**: `{ name = "agentic.session" } | quantile_over_time(span.agentic.turns, 0.95)` → `p95`
- **Grid position**: h=8 w=8 x=0 y=21
- **Field config**: unit=short

#### Panel 9: Tool calls (rate + failures)
- **Type**: timeseries
- **PromQL** (2 targets):
  - **A**: `{ name = "agentic.tool_call" } | rate()` → `tool calls`
  - **B**: `{ name = "agentic.tool_call" && span.agentic.tool_ok = false } | rate()` → `failures`
- **Grid position**: h=8 w=8 x=8 y=21
- **Field config**: unit=short

#### Panel 10: Compaction events (overflow recovery)
- **Type**: timeseries
- **PromQL** (1 target):
  - **A**: `{ name = "agentic.compaction" } | rate()` → `compactions`
- **Grid position**: h=8 w=8 x=16 y=21
- **Field config**: unit=short

#### Panel 11: Safety-bound stops (budget / repeated / overflow)
- **Type**: timeseries
- **PromQL** (1 target):
  - **A**: `{ name = "agentic.session" && span.agentic.stop_reason =~ "budget|repeated_calls|context_overflow" } | rate() by (span.agentic.stop_reason)` → `{{span.agentic.stop_reason}}`
- **Grid position**: h=8 w=24 x=0 y=29
- **Field config**: unit=short

## 5. Row Organization

| Row | Title | Collapsed | Notes |
|-----|-------|-----------|-------|
| 1 | Run health | No | Top-line outcomes and success rate |
| 2 | Cost & tokens | No | Spend and token throughput |
| 3 | Efficiency & safety modes | No | Turns, tools, compaction, safety bounds |

## 6. Variables (Filters)

### Variable: project
| Property | Value |
|----------|-------|
| Type | custom |
| Label | Project |
| Query | All : .* |
| Include All | true |
| All Value | .* |

### Variable: model
| Property | Value |
|----------|-------|
| Type | custom |
| Label | Model |
| Query | All : .* |
| Include All | true |
| All Value | .* |

## 7. SLO / Alert Candidates

- Run success rate `< 0.7` for `15m` → warning.
- Context-overflow run share `> 0.1` for `15m` → warning.
- Cost burn over `1h` `>` a deployment-set ceiling → warning.

(Thresholds must be real numbers — the spec validator rejects non-numeric/bool values.)
