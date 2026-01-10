# TASK-003: Evaluation Framework Design

**Status:** OPEN  
**Priority:** High  
**Category:** Eval  
**Created:** 2025-12-09  
**Assigned To:** Unassigned  
**Dependencies:** None  

---

## Objective

Design and implement an evaluation framework that consumes JSON output from `startd8_use_skill` to enable systematic skill and agent comparison.

## Acceptance Criteria

- [ ] Define evaluation specification format (JSON/YAML/XML)
- [ ] Create evaluation runner that executes skills
- [ ] Capture metrics from JSON responses
- [ ] Support multiple test cases per evaluation
- [ ] Generate structured results files
- [ ] Document evaluation workflow

## Context

With the JSON-first refactor complete, we now have structured metrics from every skill execution. The evaluation framework should:

1. **Define** what to test (prompts, expected behaviors, metrics to collect)
2. **Execute** skills and collect JSON responses
3. **Store** results for analysis and comparison
4. **Report** on metrics (latency, tokens, success rate)

Reference documents:
- `context/evaluations_and_workflows_v1.md`
- `reference/evaluation.md`
- `scripts/evaluation.py` (existing script)
- `scripts/example_evaluation.xml` (example format)

## Implementation Notes

### Evaluation Spec Structure (Proposed)

```yaml
evaluation:
  name: "skill-comparison-v1"
  description: "Compare game design skills"
  
  skills:
    - name: "html5-game-designer-pro"
    - name: "mcp-builder"
  
  test_cases:
    - id: "TC001"
      prompt: "Create a simple tower defense game"
      expected_keywords: ["tower", "defense", "enemy"]
      max_latency_ms: 30000
      
    - id: "TC002"
      prompt: "Create a puzzle game with 3 levels"
      expected_keywords: ["puzzle", "level"]
      
  metrics:
    - latency_ms
    - input_tokens
    - output_tokens
    - output_length
```

### Results Structure (Proposed)

```json
{
  "evaluation": "skill-comparison-v1",
  "run_date": "2025-12-09T10:00:00Z",
  "results": [
    {
      "skill": "html5-game-designer-pro",
      "test_case": "TC001",
      "status": "pass",
      "metrics": {
        "latency_ms": 2500,
        "input_tokens": 1234,
        "output_tokens": 5678,
        "output_length": 15000
      },
      "response_json": { ... }
    }
  ],
  "summary": {
    "total_tests": 4,
    "passed": 4,
    "failed": 0,
    "avg_latency_ms": 2800
  }
}
```

### Implementation Steps

1. **Design evaluation spec format** — YAML preferred for readability
2. **Create `evaluation_runner.py`** — Loads spec, executes skills, collects results
3. **Integrate with `startd8_use_skill`** — Call with JSON format
4. **Create results storage** — JSON files in `evaluations/results/`
5. **Add CLI interface** — `python evaluation_runner.py run my_eval.yaml`

---

## Work Log

*No work started yet*

---

## Blockers

*None*

---

## Completion Notes

*Task not yet complete*
