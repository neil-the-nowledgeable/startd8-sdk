# Iterative Development Workflow

## Overview

The **Iterative Development Workflow** implements an automated **dev-review-fix loop** where:

1. 🔨 **Developer Agent** implements a task
2. 👀 **Reviewer Agent** reviews the code and tests functionality  
3. ⚠️  **If issues found**: Sends feedback back to developer
4. 🔄 **Loop continues** until code passes review or max iterations reached

This pattern is perfect for:
- **Automated code generation** with quality assurance
- **Bug fixing** with validation
- **Test-driven development** workflows
- **Code refactoring** with safety checks
- **Learning scenarios** where agents improve iteratively

---

## Quick Start

### Basic Usage

```python
from startd8.iterative_workflow import IterativeDevWorkflow
from startd8.providers import ProviderRegistry

# Initialize agents
ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

developer = anthropic.create_agent("claude-sonnet-4-20250514", name="developer")
reviewer = openai.create_agent("gpt-4o", name="reviewer")

# Create workflow
workflow = IterativeDevWorkflow(
    developer_agent=developer,
    reviewer_agent=reviewer,
    max_iterations=3
)

# Run
task = """
Implement a Python function to validate email addresses.
Include proper error handling and test cases.
"""

result = workflow.run(task)

if result.successful:
    print("✓ Task completed successfully!")
    print(f"Final code:\n{result.final_code}")
else:
    print(f"Failed after {result.total_iterations} iterations")
```

### From TUI

```bash
startd8 tui
```

Select: **`🔄 Iterative Dev Workflow (Dev → Review → Fix)`**

---

## How It Works

### The Feedback Loop

```
┌─────────────┐
│   START     │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  Dev Agent:     │  Iteration 1
│  Implement Task │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Review Agent:  │
│  Check Code     │
└────────┬────────┘
         │
    ┌────┴────┐
    │ PASS?   │
    └─┬────┬──┘
      │Yes │No
      │    │
      │    ▼
      │  ┌─────────────────┐
      │  │  Dev Agent:     │  Iteration 2
      │  │  Fix Issues     │
      │  └────────┬────────┘
      │           │
      │           ▼
      │  ┌─────────────────┐
      │  │  Review Agent:  │
      │  │  Re-check       │
      │  └────────┬────────┘
      │           │
      │      ┌────┴────┐
      │      │ PASS?   │
      │      └─┬────┬──┘
      │        │Yes │No → Repeat
      │        │    │    (up to max_iterations)
      ▼        ▼    │
┌──────────────┐   │
│   SUCCESS    │◄──┘
└──────────────┘
```

### What Happens in Each Iteration

**Phase 1: Development**
```python
# First iteration: Fresh implementation
prompt = f"Implement: {task_description}"

# Later iterations: Fix based on feedback
prompt = f"""
Implement: {task_description}

PREVIOUS REVIEW FEEDBACK:
ISSUES TO FIX:
  • {issue_1}
  • {issue_2}

YOUR PREVIOUS IMPLEMENTATION:
{previous_code}

Please fix the issues above.
"""
```

**Phase 2: Review**
```python
# Reviewer checks:
review_prompt = f"""
Review this implementation of: {task_description}

IMPLEMENTATION:
{code}

Check for:
1. Does it fulfill requirements?
2. Are there bugs or errors?
3. Code quality and best practices?
4. Test coverage?

Format:
PASS/FAIL: [verdict]
SCORE: [0-100]
ISSUES:
- [List issues]
SUGGESTIONS:
- [List improvements]
"""
```

**Phase 3: Decision**
- **PASS** → Workflow complete, return final code
- **FAIL** → Send feedback to developer, next iteration
- **Max iterations reached** → Return best attempt with warnings

---

## API Reference

### IterativeDevWorkflow

```python
class IterativeDevWorkflow:
    def __init__(
        self,
        developer_agent: BaseAgent,
        reviewer_agent: BaseAgent,
        max_iterations: int = 3,
        dev_prompt_template: Optional[str] = None,
        review_prompt_template: Optional[str] = None,
        on_iteration_complete: Optional[Callable] = None
    )
```

**Parameters:**
- `developer_agent`: Agent that implements tasks (e.g., an Anthropic or OpenAI agent)
- `reviewer_agent`: Agent that reviews code (different model recommended)
- `max_iterations`: Maximum dev-review cycles (default: 3)
- `dev_prompt_template`: Custom template for developer prompts
- `review_prompt_template`: Custom template for reviewer prompts
- `on_iteration_complete`: Callback after each iteration

**Returns:** `IterativeWorkflowResult`

### IterativeWorkflowResult

```python
@dataclass
class IterativeWorkflowResult:
    workflow_id: str
    task_description: str
    status: WorkflowStatus  # COMPLETED_SUCCESS, COMPLETED_MAX_ITERATIONS, FAILED
    
    iterations: List[Iteration]  # Full history
    
    final_code: str
    final_review: Optional[ReviewFeedback]
    
    total_iterations: int
    successful: bool
    
    # Metrics
    total_time_ms: int
    total_dev_tokens: int
    total_review_tokens: int
    total_cost: float
```

### ReviewFeedback

```python
@dataclass
class ReviewFeedback:
    passed: bool
    issues: List[str]
    suggestions: List[str]
    score: Optional[int]  # 0-100
    review_text: str
```

---

## Examples

### Example 1: Simple Function with Validation

```python
from startd8.iterative_workflow import IterativeDevWorkflow
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

dev = anthropic.create_agent("claude-sonnet-4-20250514")
reviewer = openai.create_agent("gpt-4o")

workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=3)

task = """
Implement `validate_email(email: str) -> bool` that:
1. Validates email format using regex
2. Handles edge cases (None, empty, whitespace)
3. Returns True for valid, False for invalid
4. Includes docstring and test cases
"""

result = workflow.run(task)

print(f"Success: {result.successful}")
print(f"Iterations: {result.total_iterations}")
print(f"Final Score: {result.final_review.score}/100")
print(f"\nFinal Code:\n{result.final_code}")
```

### Example 2: Bug Fix Workflow

```python
buggy_code = """
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)
"""

task = f"""
Fix the bugs in this code:

{buggy_code}

Known issues:
- Doesn't handle empty list (ZeroDivisionError)
- No type hints
- No error handling
- No docstring

Fix all issues and add comprehensive error handling.
"""

result = workflow.run(task)

if result.successful:
    print("✓ All bugs fixed and passed review!")
else:
    print(f"⚠ Still has issues after {result.total_iterations} attempts")
    for issue in result.final_review.issues:
        print(f"  - {issue}")
```

### Example 3: Custom Prompts for Security Focus

```python
security_review_prompt = """You are a security expert reviewing code.

TASK: {task_description}
CODE: {implementation}

Check for:
1. SQL injection vulnerabilities
2. XSS vulnerabilities
3. Input validation
4. Authentication/authorization issues
5. Sensitive data handling
6. Error information leakage

Format:
PASS/FAIL: [verdict]
SCORE: [0-100]
ISSUES:
- [Security issues]
SUGGESTIONS:
- [Security improvements]
REVIEW:
[Detailed security analysis]
"""

from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

workflow = IterativeDevWorkflow(
    developer_agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    reviewer_agent=openai.create_agent("gpt-4o"),
    max_iterations=5,  # More iterations for security
    review_prompt_template=security_review_prompt
)

task = """
Implement a user login function with:
1. Username/password validation
2. Database query for auth
3. Session token generation
4. Rate limiting for failed attempts
"""

result = workflow.run(task, context={'framework': 'Flask', 'db': 'PostgreSQL'})
```

### Example 4: Monitoring Progress

```python
def print_progress(iteration):
    """Callback to show progress"""
    print(f"\n{'='*60}")
    print(f"Iteration {iteration.iteration_number}")
    print(f"{'='*60}")
    print(f"Dev Time: {iteration.dev_time_ms}ms")
    print(f"Review Time: {iteration.review_time_ms}ms")
    
    if iteration.feedback:
        status = "PASSED ✓" if iteration.feedback.passed else "FAILED ✗"
        print(f"Review: {status}")
        print(f"Score: {iteration.feedback.score}/100")
        
        if iteration.feedback.issues:
            print(f"\nIssues Found:")
            for issue in iteration.feedback.issues:
                print(f"  • {issue}")

from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

workflow = IterativeDevWorkflow(
    developer_agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    reviewer_agent=openai.create_agent("gpt-4o"),
    max_iterations=3,
    on_iteration_complete=print_progress  # Add callback
)

result = workflow.run("Implement a binary search function")
```

### Example 5: Using Mock Agents (No API Keys)

```python
from startd8.providers import ProviderRegistry

# Perfect for testing without API costs!
ProviderRegistry.discover()
mock = ProviderRegistry.get_provider("mock")
dev = mock.create_agent("mock-model", name="mock-dev")
reviewer = mock.create_agent("mock-model", name="mock-reviewer")

workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=2)

result = workflow.run("Implement quicksort")

# Mock agents always pass on second iteration
assert result.successful
assert result.total_iterations == 2
```

---

## Configuration Options

### Custom Developer Prompts

```python
custom_dev_prompt = """You are a {style} developer.

TASK:
{task_description}

REQUIREMENTS:
- Follow {coding_standard}
- Use {best_practice}

{iteration_context}
{feedback_section}

Implement the solution."""

workflow = IterativeDevWorkflow(
    developer_agent=dev,
    reviewer_agent=reviewer,
    dev_prompt_template=custom_dev_prompt
)

# Variables are auto-filled
result = workflow.run(task, context={
    'style': 'senior Python',
    'coding_standard': 'PEP-8',
    'best_practice': 'type hints and docstrings'
})
```

### Custom Review Criteria

```python
custom_review_prompt = """Review for {focus_area}:

TASK: {task_description}
CODE: {implementation}

Check specifically:
{criteria}

PASS/FAIL: [verdict]
SCORE: [0-100]
ISSUES:
- [List issues]
"""

workflow = IterativeDevWorkflow(
    developer_agent=dev,
    reviewer_agent=reviewer,
    review_prompt_template=custom_review_prompt
)

result = workflow.run(task, context={
    'focus_area': 'performance',
    'criteria': '1. O(n) complexity\n2. Memory efficiency\n3. No premature optimization'
})
```

---

## Best Practices

### 1. Choose Different Agents

**Why?** Different models have different strengths.

```python
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

# Good: Diverse perspectives (different providers/models)
workflow = IterativeDevWorkflow(
    developer_agent=anthropic.create_agent("claude-sonnet-4-20250514"),
    reviewer_agent=openai.create_agent("gpt-4o"),
)

# Okay but less effective: same provider/model for both roles
same = openai.create_agent("gpt-4o")
workflow = IterativeDevWorkflow(
    developer_agent=same,
    reviewer_agent=same,
)
```

### 2. Set Appropriate Max Iterations

```python
# Simple tasks
workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=2)

# Complex tasks or bug fixes
workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=5)

# Production-critical code
workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=10)
```

### 3. Provide Context

```python
# Without context - vague
result = workflow.run("Implement login function")

# With context - specific
result = workflow.run(
    "Implement login function",
    context={
        'framework': 'Flask',
        'database': 'PostgreSQL',
        'auth_method': 'JWT tokens',
        'requirements': [
            'Rate limiting after 5 failed attempts',
            'Password must be bcrypt hashed',
            'Session expires after 24 hours'
        ]
    }
)
```

### 4. Monitor Costs

```python
result = workflow.run(task)

print(f"Total tokens: {result.total_dev_tokens + result.total_review_tokens:,}")
print(f"Estimated cost: ${result.total_cost:.4f}")
print(f"Cost per iteration: ${result.total_cost / result.total_iterations:.4f}")

# Set budgets
if result.total_cost > 1.0:  # $1 budget
    print("Warning: Expensive workflow!")
```

### 5. Save Results

```python
from startd8.iterative_workflow import save_workflow_result
from pathlib import Path

result = workflow.run(task)

# Save for later analysis
output_dir = Path("./workflow_results")
filepath = save_workflow_result(result, output_dir)

print(f"Saved to: {filepath}")

# Later: Load and analyze
import json
with open(filepath) as f:
    data = json.load(f)
    print(f"Previous run: {data['successful']}")
```

---

## Troubleshooting

### Issue: Workflow Never Passes

**Symptoms**: Reaches max iterations, always failing review

**Solutions:**
1. Check reviewer is too strict:
   ```python
   # Add more lenient review criteria
   result = workflow.run(task, context={'allow_minor_issues': True})
   ```

2. Increase max iterations:
   ```python
   workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=10)
   ```

3. Simplify the task:
   ```python
   # Instead of: "Build a complete REST API"
   # Try: "Build a single /users endpoint"
   ```

### Issue: Developer Not Fixing Issues

**Symptoms**: Same issues appear across iterations

**Solutions:**
1. Make feedback more specific:
   ```python
   # Customize review prompt to be more explicit
   review_prompt = """
   For each issue, provide:
   1. Exact line/function with problem
   2. What's wrong
   3. Specific fix needed
   """
   ```

2. Add examples to context:
   ```python
   result = workflow.run(task, context={
       'example_fix': 'Use `if not items: raise ValueError("Empty list")`'
   })
   ```

### Issue: High Token Usage/Cost

**Solutions:**
1. Reduce max iterations
2. Use smaller/cheaper models for initial iterations:
   ```python
   from startd8.providers import ProviderRegistry

   ProviderRegistry.discover()
   openai = ProviderRegistry.get_provider("openai")
   openai.validate_config({})

   # Cheaper model for drafts
   dev_agent = openai.create_agent("gpt-4o-mini")
   
   # Stronger model only for final review
   review_agent = openai.create_agent("gpt-4o")
   ```

3. Simplify prompts (remove verbose instructions)

### Issue: Timeout or Slow Performance

**Solutions:**
1. Use faster models (e.g., `claude-haiku-4-5-20251008`, `gpt-4o-mini`)
2. Reduce task complexity
3. Split into multiple smaller workflows

---

## Advanced Patterns

### Pattern 1: Multi-Stage Review

```python
# Stage 1: Functionality review
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

func_reviewer = anthropic.create_agent("claude-sonnet-4-20250514")
func_workflow = IterativeDevWorkflow(dev, func_reviewer, max_iterations=3)
result1 = func_workflow.run(task)

if result1.successful:
    # Stage 2: Security review
    sec_reviewer = openai.create_agent("gpt-4o")  # Different provider/model
    sec_workflow = IterativeDevWorkflow(
        dev,
        sec_reviewer,
        max_iterations=2,
        review_prompt_template=security_review_prompt
    )
    result2 = sec_workflow.run(
        f"Review and harden this code:\n{result1.final_code}"
    )
```

### Pattern 2: Test-Driven Development

```python
# First: Generate tests
test_task = "Write pytest tests for email validation function"
test_result = workflow.run(test_task)

# Then: Implement to pass tests
impl_task = f"""
Implement email validation function that passes these tests:

{test_result.final_code}
"""
impl_result = workflow.run(impl_task)
```

### Pattern 3: Incremental Complexity

```python
tasks = [
    "Implement basic email validation (format only)",
    "Add DNS lookup validation",
    "Add disposable email detection",
    "Add comprehensive error messages"
]

code = ""
for task in tasks:
    if code:
        task = f"{task}\n\nBuild upon:\n{code}"
    
    result = workflow.run(task)
    if result.successful:
        code = result.final_code
    else:
        print(f"Failed at: {task}")
        break
```

---

## Metrics & Analysis

### Analyzing Results

```python
result = workflow.run(task)

# Success metrics
print(f"Success Rate: {int(result.successful)}") 
print(f"Iterations Needed: {result.total_iterations}")
print(f"Final Score: {result.final_review.score}/100")

# Performance metrics
print(f"Total Time: {result.total_time_ms/1000:.2f}s")
print(f"Avg Time per Iteration: {result.total_time_ms/result.total_iterations/1000:.2f}s")

# Cost metrics
print(f"Total Cost: ${result.total_cost:.4f}")
print(f"Cost per Iteration: ${result.total_cost/result.total_iterations:.4f}")

# Quality progression
for i, iteration in enumerate(result.iterations, 1):
    if iteration.feedback:
        print(f"Iteration {i}: Score {iteration.feedback.score}/100, Issues: {len(iteration.feedback.issues)}")
```

### Comparing Workflows

```python
from startd8.providers import ProviderRegistry

results = []

ProviderRegistry.discover()
anthropic = ProviderRegistry.get_provider("anthropic")
openai = ProviderRegistry.get_provider("openai")
anthropic.validate_config({})
openai.validate_config({})

dev_agent = anthropic.create_agent("claude-sonnet-4-20250514", name="dev")
review_agent = openai.create_agent("gpt-4o", name="review")

for agent_pair in [(dev_agent, review_agent), (review_agent, dev_agent), (dev_agent, dev_agent)]:
    workflow = IterativeDevWorkflow(*agent_pair, max_iterations=3)
    result = workflow.run(task)
    results.append({
        'pair': f"{agent_pair[0].name} + {agent_pair[1].name}",
        'successful': result.successful,
        'iterations': result.total_iterations,
        'cost': result.total_cost
    })

# Find best combination
best = min(results, key=lambda r: (not r['successful'], r['cost']))
print(f"Best combo: {best['pair']}")
```

---

## Integration with Other Features

### With Job Queue

```python
from startd8.job_queue import JobQueue, create_job_file
from startd8.iterative_workflow import IterativeDevWorkflow

# Create job
job_file = create_job_file(
    output_path=Path("./jobs/implement_feature.json"),
    content="Implement user registration with email verification"
)

# Process with iterative workflow
workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=3)
result = workflow.run(job_file.prompt.content)

# Save result
save_workflow_result(result, Path("./results"))
```

### With Document Enhancement

```python
# Generate initial doc
doc_task = "Write API documentation for user registration endpoint"
doc_result = workflow.run(doc_task)

# Enhance with document chain
from startd8.document_enhancement import DocumentEnhancementChain
# ... enhance the generated doc
```

---

## FAQ

**Q: Can I use the same agent for both developer and reviewer?**  
A: Yes, but it's less effective. Different models provide better review diversity.

**Q: What if I want more than 2 agents in the loop?**  
A: Chain multiple workflows or extend the class. Example: Dev → Review → Security Review → Performance Review.

**Q: How do I handle non-code tasks?**  
A: Works for any text-based iterative task (writing, analysis, planning, etc.). Just customize the prompts.

**Q: Can I pause and resume?**  
A: Not directly, but you can save `IterativeWorkflowResult` and create a new workflow starting from the last iteration's output.

**Q: What's the difference vs regular agent distribution?**  
A: Regular distribution runs agents independently. Iterative workflow has agents collaborate with feedback loops.

**Q: How much does this cost?**  
A: Depends on models and iterations. Example: 3 iterations with an Anthropic dev agent and an OpenAI review agent on a ~500-token task ≈ $0.10-0.50.

---

## Next Steps

1. **Try the examples**: Run `examples/iterative_dev_workflow_example.py`
2. **Customize prompts**: Create domain-specific templates
3. **Monitor results**: Use callbacks to track progress
4. **Save workflows**: Build a library of successful patterns
5. **Integrate**: Combine with job queues, pipelines, etc.

---

**Happy Iterating!** 🔄

*Last Updated: December 7, 2025*
