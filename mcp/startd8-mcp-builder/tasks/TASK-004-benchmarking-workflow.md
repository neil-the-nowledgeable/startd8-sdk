# TASK-004: Benchmarking Workflow

**Status:** OPEN  
**Priority:** High  
**Category:** Eval  
**Created:** 2025-12-09  
**Assigned To:** Unassigned  
**Dependencies:** TASK-003  

---

## Objective

Create a complete benchmarking workflow that runs evaluations across multiple skills, collects metrics, and produces comparison reports.

## Acceptance Criteria

- [ ] Workflow runs multiple skills against same test cases
- [ ] Metrics collected and aggregated across runs
- [ ] Comparison tables generated (skill vs skill)
- [ ] Trend tracking over time (optional)
- [ ] CLI or script interface
- [ ] Example benchmark suite included

## Context

Building on the evaluation framework (TASK-003), this task creates the full benchmarking workflow for comparing skills and tracking performance.

Use cases:
- Compare two HTML game skills on same prompts
- Track latency improvements after skill updates
- Identify which skill is most token-efficient
- A/B test skill variations

## Implementation Notes

### Benchmark Suite Structure

```
benchmarks/
├── benchmark_config.yaml       # Global benchmark settings
├── game_skills/
│   ├── suite.yaml              # Test suite definition
│   ├── prompts/
│   │   ├── simple_game.txt
│   │   └── complex_game.txt
│   └── results/
│       ├── 2025-12-09_run1.json
│       └── 2025-12-09_run2.json
└── mcp_skills/
    ├── suite.yaml
    └── ...
```

### Workflow Steps

1. **Load benchmark suite** — Parse YAML config
2. **Discover skills to test** — From suite or all available
3. **Run evaluation** — Execute each skill × prompt combination
4. **Collect metrics** — Extract from JSON responses
5. **Generate comparison** — Tables, charts (optional)
6. **Store results** — For historical tracking

### Example CLI

```bash
# Run a benchmark suite
python benchmark.py run benchmarks/game_skills/suite.yaml

# Compare results from two runs
python benchmark.py compare results/run1.json results/run2.json

# Generate report from latest results
python benchmark.py report benchmarks/game_skills/
```

### Comparison Output (Example)

```
┌─────────────────────────┬─────────────┬─────────────┬────────────┐
│ Metric                  │ Skill A     │ Skill B     │ Difference │
├─────────────────────────┼─────────────┼─────────────┼────────────┤
│ Avg Latency (ms)        │ 2,500       │ 3,200       │ -700 (28%) │
│ Avg Input Tokens        │ 1,234       │ 1,456       │ -222 (15%) │
│ Avg Output Tokens       │ 5,678       │ 4,890       │ +788 (16%) │
│ Success Rate            │ 100%        │ 95%         │ +5%        │
└─────────────────────────┴─────────────┴─────────────┴────────────┘
```

---

## Work Log

*No work started yet*

---

## Blockers

- **Depends on TASK-003** — Evaluation framework must be complete first

---

## Completion Notes

*Task not yet complete*
