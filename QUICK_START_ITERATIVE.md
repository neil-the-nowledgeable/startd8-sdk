# Quick Start: Iterative Dev-Review-Fix Workflow

## 🚀 **5-Minute Getting Started**

### **Step 1: Import**

```python
from startd8.agents import ClaudeAgent, GPT4Agent
from startd8.iterative_workflow import IterativeDevWorkflow
```

### **Step 2: Create Workflow**

```python
workflow = IterativeDevWorkflow(
    developer_agent=ClaudeAgent(),  # Agent that codes
    reviewer_agent=GPT4Agent(),      # Agent that reviews
    max_iterations=3                 # Maximum attempts
)
```

### **Step 3: Run**

```python
task = "Implement a function to validate email addresses"
result = workflow.run(task)

if result.successful:
    print("✓ Task completed!")
    print(result.final_code)
else:
    print(f"⚠ Failed after {result.total_iterations} attempts")
```

### **That's it!** 🎉

---

## **What Happens Automatically**

```
┌─────────────┐
│  Your Task  │
└──────┬──────┘
       │
       ▼
┌─────────────────┐  Iteration 1
│  Dev: Codes it  │
└────────┬────────┘
         │
         ▼
┌──────────────────┐
│  Review: Checks  │  
└────────┬─────────┘
         │
    ┌────┴────┐
    │ Issues? │
    └─┬────┬──┘
   No │    │ Yes
      │    ▼
      │  ┌─────────────────┐  Iteration 2
      │  │  Dev: Fixes it  │
      │  └────────┬────────┘
      │           │
      │           ▼
      │  ┌──────────────────┐
      │  │  Review: Checks  │
      │  └────────┬─────────┘
      │           │
      │      ┌────┴────┐
      │      │ Pass?   │
      │      └─┬───────┘
      │        │ Yes
      ▼        ▼
   ┌──────────────┐
   │    DONE!     │
   └──────────────┘
```

---

## **Common Patterns**

### **Pattern 1: Bug Fix**

```python
buggy_code = """
def divide(a, b):
    return a / b  # Bug: No zero check!
"""

workflow = IterativeDevWorkflow(claude, gpt4, max_iterations=3)
result = workflow.run(f"Fix this code:\n{buggy_code}")

# Automatic: Reviewer finds bug → Dev fixes → Pass!
```

### **Pattern 2: With Progress**

```python
def show_progress(iteration):
    print(f"Iteration {iteration.iteration_number}: {iteration.status}")

workflow = IterativeDevWorkflow(
    claude, gpt4, 
    max_iterations=3,
    on_iteration_complete=show_progress  # Add callback
)
```

### **Pattern 3: Custom Review**

```python
security_review = """
Check for security issues:
- SQL injection
- Input validation
- Authentication
"""

workflow = IterativeDevWorkflow(
    claude, gpt4,
    review_prompt_template=security_review
)
```

### **Pattern 4: Mock (No API Keys)**

```python
from startd8.agents import MockAgent

# Perfect for testing!
workflow = IterativeDevWorkflow(
    MockAgent(), MockAgent(),
    max_iterations=2
)

result = workflow.run("Test task")  # Always succeeds
```

---

## **Check Results**

```python
# Success?
result.successful  # True/False

# How many tries?
result.total_iterations  # 1, 2, 3...

# Final code
result.final_code  # The implementation

# Review details
result.final_review.score  # 0-100
result.final_review.issues  # List of issues (if any)
result.final_review.suggestions  # List of improvements

# Metrics
result.total_time_ms  # Time taken
result.total_cost  # Estimated cost in USD
```

---

## **Full Example**

```python
from startd8.agents import ClaudeAgent, GPT4Agent
from startd8.iterative_workflow import IterativeDevWorkflow

# Setup
dev = ClaudeAgent()
reviewer = GPT4Agent()

workflow = IterativeDevWorkflow(
    developer_agent=dev,
    reviewer_agent=reviewer,
    max_iterations=3
)

# Task
task = """
Implement `validate_email(email: str) -> bool` that:
1. Validates email format
2. Handles None and empty strings
3. Returns True/False
4. Includes docstring
"""

# Run
result = workflow.run(task)

# Results
if result.successful:
    print(f"✓ Completed in {result.total_iterations} iteration(s)")
    print(f"Score: {result.final_review.score}/100")
    print(f"Cost: ${result.total_cost:.4f}")
    print(f"\nFinal Code:\n{result.final_code}")
else:
    print(f"✗ Failed after {result.total_iterations} attempts")
    print(f"Remaining issues: {len(result.final_review.issues)}")
    for issue in result.final_review.issues:
        print(f"  - {issue}")
```

---

## **Run Examples**

```bash
python examples/iterative_dev_workflow_example.py
```

Choose:
- **Example 1**: Simple function
- **Example 2**: Bug fix
- **Example 3**: Mock agents (no API keys!)
- **Example 4**: Custom prompts

---

## **Tips**

💡 **Use different agents** - Claude dev + GPT-4 review works great  
💡 **Start with 3 iterations** - Adjust based on complexity  
💡 **Add context** - Pass requirements, frameworks, examples  
💡 **Monitor costs** - Check `result.total_cost` for large tasks  
💡 **Save results** - Use `save_workflow_result()` for analysis  

---

## **More Info**

📖 **Full docs**: `docs/ITERATIVE_DEV_WORKFLOW.md`  
📋 **Summary**: `ITERATIVE_WORKFLOW_SUMMARY.md`  
💻 **Examples**: `examples/iterative_dev_workflow_example.py`  

---

**Happy Coding!** 🔄✨
