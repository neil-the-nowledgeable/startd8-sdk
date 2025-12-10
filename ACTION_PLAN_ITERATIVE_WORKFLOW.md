# Action Plan: Iterative Workflow Improvements

**Created**: December 7, 2025  
**Based on**: Code Review (CODE_REVIEW_ITERATIVE_WORKFLOW.md)  
**Timeline**: 3 weeks  
**Estimated Effort**: 40-52 hours

---

## Executive Summary

This action plan addresses the findings from the senior developer code review of the iterative workflow implementation. It is organized into three phases:

1. **Week 1**: Critical Fixes (Must-have for production)
2. **Week 2**: Testing (Quality assurance)
3. **Week 3**: Polish & Hardening (Production-ready)

---

## Phase 1: Critical Fixes (Week 1)

**Timeline**: Days 1-5  
**Effort**: 16-20 hours  
**Priority**: 🔴 CRITICAL

### Task 1.1: Granular Exception Handling

**File**: `src/startd8/iterative_workflow.py`  
**Effort**: 4 hours  
**Priority**: 🔴 CRITICAL

#### Current Problem
```python
except Exception as e:
    logger.error(f"Error in iteration {iteration_num}: {e}", exc_info=True)
    iteration.status = IterationStatus.FAILED
    break  # Swallows ALL errors
```

#### Action Items

- [ ] **1.1.1** Import specific exception types
  ```python
  from startd8.exceptions import APIError, ValidationError, ConfigurationError
  ```

- [ ] **1.1.2** Replace broad exception handling in `run()` method (line ~306)
  ```python
  try:
      # Dev phase
      dev_response = self.developer_agent.generate(dev_prompt)
      # Review phase  
      review_response = self.reviewer_agent.generate(review_prompt)
      
  except APIError as e:
      logger.warning(f"API error in iteration {iteration_num}: {e}")
      if e.retry_after and iteration_num < self.max_iterations:
          logger.info(f"Retrying after {e.retry_after}s...")
          import time
          time.sleep(e.retry_after)
          continue  # Retry same iteration
      else:
          iteration.status = IterationStatus.FAILED
          iteration.error = f"API Error: {e}"
          result.status = WorkflowStatus.FAILED
          break
          
  except ValidationError as e:
      logger.error(f"Validation error in iteration {iteration_num}: {e}")
      iteration.status = IterationStatus.FAILED
      iteration.error = f"Validation Error: {e}"
      result.status = WorkflowStatus.FAILED
      break
      
  except ConfigurationError as e:
      logger.error(f"Configuration error: {e}")
      iteration.status = IterationStatus.FAILED
      iteration.error = f"Config Error: {e}"
      result.status = WorkflowStatus.FAILED
      break
      
  except Exception as e:
      logger.error(f"Unexpected error in iteration {iteration_num}: {e}", exc_info=True)
      iteration.status = IterationStatus.FAILED
      iteration.error = f"Unexpected: {e}"
      result.status = WorkflowStatus.FAILED
      # Re-raise unexpected errors for visibility
      raise
  ```

- [ ] **1.1.3** Add `error` field to `Iteration` dataclass
  ```python
  @dataclass
  class Iteration:
      # ... existing fields ...
      error: Optional[str] = None  # Add this
  ```

- [ ] **1.1.4** Test error handling with mock exceptions

#### Acceptance Criteria
- [ ] API errors are caught and logged separately
- [ ] Validation errors fail fast with clear message
- [ ] Unexpected errors are re-raised (not swallowed)
- [ ] Each error type has specific handling logic
- [ ] Retry logic works for transient API errors

---

### Task 1.2: Robust Review Parsing

**File**: `src/startd8/iterative_workflow.py`  
**Effort**: 4 hours  
**Priority**: 🔴 CRITICAL

#### Current Problem
```python
# Fragile string splitting
if line.startswith('PASS/FAIL:'):
    verdict = line.split(':', 1)[1].strip().upper()
    passed = 'PASS' in verdict  # Breaks on variations
```

#### Action Items

- [ ] **1.2.1** Add regex import and patterns at top of file
  ```python
  import re
  
  # Review parsing patterns
  PASS_FAIL_PATTERN = re.compile(
      r'PASS/FAIL\s*:\s*(PASS|FAIL|✓|✗|YES|NO)',
      re.IGNORECASE
  )
  SCORE_PATTERN = re.compile(r'SCORE\s*:?\s*(\d+)', re.IGNORECASE)
  ISSUES_PATTERN = re.compile(
      r'ISSUES\s*:(.*?)(?=SUGGESTIONS:|REVIEW:|$)',
      re.DOTALL | re.IGNORECASE
  )
  SUGGESTIONS_PATTERN = re.compile(
      r'SUGGESTIONS\s*:(.*?)(?=REVIEW:|$)',
      re.DOTALL | re.IGNORECASE
  )
  ```

- [ ] **1.2.2** Create custom exception for parse errors
  ```python
  class ReviewParseError(Exception):
      """Error parsing review feedback"""
      pass
  ```

- [ ] **1.2.3** Rewrite `_parse_review_feedback()` method
  ```python
  def _parse_review_feedback(self, review_text: str) -> ReviewFeedback:
      """
      Parse review response with robust regex handling.
      
      Handles variations in format and provides fallbacks.
      """
      # Extract PASS/FAIL
      pass_match = PASS_FAIL_PATTERN.search(review_text)
      if pass_match:
          verdict = pass_match.group(1).upper()
          passed = verdict in ('PASS', '✓', 'YES')
      else:
          logger.warning("Could not parse PASS/FAIL from review, assuming FAIL")
          passed = False
      
      # Extract SCORE
      score = None
      score_match = SCORE_PATTERN.search(review_text)
      if score_match:
          try:
              score = int(score_match.group(1))
              # Clamp to valid range
              if score < 0 or score > 100:
                  logger.warning(f"Score {score} out of range, clamping to 0-100")
                  score = max(0, min(100, score))
          except ValueError:
              logger.warning(f"Invalid score format: {score_match.group(1)}")
      
      # Extract ISSUES
      issues = []
      issues_match = ISSUES_PATTERN.search(review_text)
      if issues_match:
          issues_text = issues_match.group(1)
          # Find bullet points (-, •, *, numbered)
          issue_items = re.findall(r'[-•*]\s*(.+?)(?=\n[-•*]|\n\n|$)', issues_text, re.DOTALL)
          issues = [item.strip() for item in issue_items if item.strip()]
      
      # Extract SUGGESTIONS
      suggestions = []
      suggestions_match = SUGGESTIONS_PATTERN.search(review_text)
      if suggestions_match:
          suggestions_text = suggestions_match.group(1)
          suggestion_items = re.findall(r'[-•*]\s*(.+?)(?=\n[-•*]|\n\n|$)', suggestions_text, re.DOTALL)
          suggestions = [item.strip() for item in suggestion_items if item.strip()]
      
      # Validation warning
      if not passed and not issues:
          logger.warning(
              "Review marked as FAIL but no issues listed - "
              "may indicate parsing error or unclear review"
          )
      
      return ReviewFeedback(
          passed=passed,
          issues=issues,
          suggestions=suggestions,
          score=score,
          review_text=review_text
      )
  ```

- [ ] **1.2.4** Add fallback JSON parsing (optional enhancement)
  ```python
  def _try_parse_json_review(self, review_text: str) -> Optional[ReviewFeedback]:
      """Try to parse review as JSON if present"""
      try:
          # Look for JSON block in response
          json_match = re.search(r'\{[^{}]*\}', review_text, re.DOTALL)
          if json_match:
              data = json.loads(json_match.group(0))
              return ReviewFeedback(
                  passed=data.get('passed', False),
                  issues=data.get('issues', []),
                  suggestions=data.get('suggestions', []),
                  score=data.get('score'),
                  review_text=review_text
              )
      except (json.JSONDecodeError, KeyError, TypeError):
          pass
      return None
  ```

- [ ] **1.2.5** Update `_parse_review_feedback()` to try JSON first
  ```python
  def _parse_review_feedback(self, review_text: str) -> ReviewFeedback:
      # Try JSON first (more reliable)
      json_result = self._try_parse_json_review(review_text)
      if json_result:
          return json_result
      
      # Fallback to regex parsing
      return self._parse_review_feedback_regex(review_text)
  ```

#### Acceptance Criteria
- [ ] Handles "PASS", "Pass", "pass", "✓" variations
- [ ] Handles "SCORE: 85", "Score:85", "SCORE = 85" variations
- [ ] Extracts issues from bullet points (-, •, *)
- [ ] Logs warnings for parsing issues (doesn't fail silently)
- [ ] Falls back gracefully when format is unexpected

---

### Task 1.3: Input Validation

**File**: `src/startd8/iterative_workflow.py`  
**Effort**: 2 hours  
**Priority**: 🟡 IMPORTANT

#### Action Items

- [ ] **1.3.1** Add validation method
  ```python
  def _validate_inputs(
      self,
      task_description: str,
      context: Optional[Dict[str, Any]]
  ) -> None:
      """
      Validate workflow inputs.
      
      Raises:
          ValueError: If inputs are invalid
      """
      # Task description validation
      if not task_description:
          raise ValueError("Task description cannot be empty")
      
      if not task_description.strip():
          raise ValueError("Task description cannot be only whitespace")
      
      if len(task_description) > 100_000:  # 100KB limit
          raise ValueError(
              f"Task description too long ({len(task_description)} chars, max 100,000)"
          )
      
      # Context validation
      if context:
          try:
              # Ensure it's JSON serializable
              json.dumps(context)
          except (TypeError, ValueError) as e:
              raise ValueError(f"Context must be JSON serializable: {e}")
          
          # Size check
          context_str = json.dumps(context)
          if len(context_str) > 50_000:  # 50KB limit
              raise ValueError(
                  f"Context too large ({len(context_str)} chars, max 50,000)"
              )
  ```

- [ ] **1.3.2** Add suspicious pattern detection
  ```python
  SUSPICIOUS_PATTERNS = [
      'ignore all previous',
      'ignore above',
      'disregard instructions',
      'new instructions:',
      'jailbreak',
      'sudo mode',
      'developer mode',
  ]
  
  def _check_suspicious_content(self, text: str) -> List[str]:
      """Check for potentially malicious patterns"""
      found = []
      text_lower = text.lower()
      for pattern in SUSPICIOUS_PATTERNS:
          if pattern in text_lower:
              found.append(pattern)
      return found
  
  def _validate_inputs(self, task_description: str, ...):
      # ... existing validation ...
      
      # Check for suspicious patterns
      suspicious = self._check_suspicious_content(task_description)
      if suspicious:
          logger.warning(
              f"Suspicious patterns detected in task: {suspicious}. "
              "Proceeding with caution."
          )
  ```

- [ ] **1.3.3** Call validation at start of `run()`
  ```python
  def run(self, task_description: str, context: Optional[Dict[str, Any]] = None):
      # Validate inputs first
      self._validate_inputs(task_description, context)
      
      # ... rest of method ...
  ```

- [ ] **1.3.4** Add dataclass validation
  ```python
  @dataclass
  class Iteration:
      iteration_number: int
      status: IterationStatus
      # ... other fields ...
      
      def __post_init__(self):
          if self.iteration_number < 1:
              raise ValueError(f"iteration_number must be >= 1, got {self.iteration_number}")
          if self.dev_time_ms < 0:
              raise ValueError(f"dev_time_ms must be >= 0, got {self.dev_time_ms}")
          if self.review_time_ms < 0:
              raise ValueError(f"review_time_ms must be >= 0, got {self.review_time_ms}")
  ```

#### Acceptance Criteria
- [ ] Empty task descriptions raise ValueError
- [ ] Oversized inputs raise ValueError
- [ ] Non-serializable context raises ValueError
- [ ] Suspicious patterns are logged as warnings
- [ ] Dataclass fields are validated

---

### Task 1.4: Timeout Handling

**File**: `src/startd8/iterative_workflow.py`  
**Effort**: 3 hours  
**Priority**: 🟡 IMPORTANT

#### Action Items

- [ ] **1.4.1** Add timeout configuration
  ```python
  def __init__(
      self,
      developer_agent: BaseAgent,
      reviewer_agent: BaseAgent,
      max_iterations: int = 3,
      timeout_per_iteration: int = 300,  # 5 minutes default
      dev_prompt_template: Optional[str] = None,
      review_prompt_template: Optional[str] = None,
      on_iteration_complete: Optional[Callable[[Iteration], None]] = None
  ):
      # ... existing init ...
      self.timeout_per_iteration = timeout_per_iteration
  ```

- [ ] **1.4.2** Create timeout context manager
  ```python
  import signal
  from contextlib import contextmanager
  
  class TimeoutError(Exception):
      """Operation timed out"""
      pass
  
  @contextmanager
  def timeout(seconds: int, operation: str = "Operation"):
      """
      Context manager for operation timeout.
      
      Args:
          seconds: Timeout in seconds
          operation: Description for error message
          
      Raises:
          TimeoutError: If operation exceeds timeout
      """
      def timeout_handler(signum, frame):
          raise TimeoutError(f"{operation} timed out after {seconds}s")
      
      # Set handler
      original_handler = signal.signal(signal.SIGALRM, timeout_handler)
      signal.alarm(seconds)
      
      try:
          yield
      finally:
          # Restore
          signal.alarm(0)
          signal.signal(signal.SIGALRM, original_handler)
  ```

- [ ] **1.4.3** Add cross-platform timeout (for Windows)
  ```python
  import threading
  from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
  
  def run_with_timeout(func, timeout_seconds: int, *args, **kwargs):
      """
      Run function with timeout (cross-platform).
      
      Works on both Unix and Windows.
      """
      with ThreadPoolExecutor(max_workers=1) as executor:
          future = executor.submit(func, *args, **kwargs)
          try:
              return future.result(timeout=timeout_seconds)
          except FutureTimeoutError:
              raise TimeoutError(f"Operation timed out after {timeout_seconds}s")
  ```

- [ ] **1.4.4** Apply timeout to agent calls
  ```python
  def run(self, task_description: str, ...):
      for iteration_num in range(1, self.max_iterations + 1):
          try:
              # Dev phase with timeout
              logger.debug(f"Sending task to developer agent (timeout: {self.timeout_per_iteration}s)")
              dev_response = run_with_timeout(
                  self.developer_agent.generate,
                  self.timeout_per_iteration,
                  dev_prompt
              )
              
              # Review phase with timeout
              logger.debug(f"Sending to reviewer agent (timeout: {self.timeout_per_iteration}s)")
              review_response = run_with_timeout(
                  self.reviewer_agent.generate,
                  self.timeout_per_iteration,
                  review_prompt
              )
              
          except TimeoutError as e:
              logger.error(f"Iteration {iteration_num} timed out: {e}")
              iteration.status = IterationStatus.FAILED
              iteration.error = str(e)
              result.status = WorkflowStatus.FAILED
              break
  ```

#### Acceptance Criteria
- [ ] Default timeout is 5 minutes per iteration
- [ ] Timeout is configurable via `__init__`
- [ ] Timeout errors are caught and logged
- [ ] Works on both Unix and Windows
- [ ] Iteration marked as FAILED on timeout

---

### Task 1.5: Cost Controls

**File**: `src/startd8/iterative_workflow.py`  
**Effort**: 2 hours  
**Priority**: 🟡 IMPORTANT

#### Action Items

- [ ] **1.5.1** Add cost configuration
  ```python
  def __init__(
      self,
      # ... existing params ...
      max_cost_usd: Optional[float] = None,  # None = no limit
      warn_cost_usd: Optional[float] = None,  # Warn threshold
  ):
      self.max_cost_usd = max_cost_usd
      self.warn_cost_usd = warn_cost_usd
  ```

- [ ] **1.5.2** Add cost tracking helper
  ```python
  def _calculate_current_cost(self, result: IterativeWorkflowResult) -> float:
      """Calculate current cost from iterations"""
      total_tokens = result.total_dev_tokens + result.total_review_tokens
      # Default estimate: $5 per 1M tokens (adjust based on models)
      return (total_tokens / 1_000_000) * 5.0
  ```

- [ ] **1.5.3** Add cost checking after each iteration
  ```python
  def run(self, task_description: str, ...):
      for iteration_num in range(...):
          # ... iteration logic ...
          
          # Update running totals
          if iteration.dev_tokens:
              result.total_dev_tokens += iteration.dev_tokens.total
          if iteration.review_tokens:
              result.total_review_tokens += iteration.review_tokens.total
          
          # Check cost limits
          current_cost = self._calculate_current_cost(result)
          
          if self.warn_cost_usd and current_cost > self.warn_cost_usd:
              logger.warning(
                  f"Cost warning: ${current_cost:.4f} exceeds warn threshold ${self.warn_cost_usd:.4f}"
              )
          
          if self.max_cost_usd and current_cost > self.max_cost_usd:
              logger.error(
                  f"Cost limit exceeded: ${current_cost:.4f} > ${self.max_cost_usd:.4f}. "
                  "Stopping workflow."
              )
              result.status = WorkflowStatus.FAILED
              result.final_code = current_implementation
              result.final_review = iteration.feedback
              break
  ```

- [ ] **1.5.4** Add cost estimate before run
  ```python
  def estimate_cost(self, task_description: str, max_iterations: int = None) -> Dict[str, float]:
      """
      Estimate cost for workflow before running.
      
      Returns:
          Dict with min, max, expected cost estimates
      """
      iters = max_iterations or self.max_iterations
      
      # Rough estimates per iteration
      tokens_per_dev_call = 4000   # ~1K prompt + 3K response
      tokens_per_review_call = 3000  # Similar
      tokens_per_iteration = tokens_per_dev_call + tokens_per_review_call
      
      cost_per_million = 5.0  # Rough average
      
      return {
          'min_cost': (tokens_per_iteration / 1_000_000) * cost_per_million,
          'max_cost': (tokens_per_iteration * iters / 1_000_000) * cost_per_million,
          'expected_cost': (tokens_per_iteration * 2 / 1_000_000) * cost_per_million,  # Usually 2 iterations
      }
  ```

#### Acceptance Criteria
- [ ] `max_cost_usd` stops workflow when exceeded
- [ ] `warn_cost_usd` logs warning but continues
- [ ] Cost is calculated after each iteration
- [ ] `estimate_cost()` provides pre-run estimates
- [ ] Cost data included in result object

---

## Phase 2: Testing (Week 2)

**Timeline**: Days 6-10  
**Effort**: 16-20 hours  
**Priority**: 🔴 CRITICAL

### Task 2.1: Core Workflow Tests

**File**: `tests/unit/test_iterative_workflow.py` (NEW)  
**Effort**: 8 hours

#### Action Items

- [ ] **2.1.1** Create test file structure
  ```python
  """
  Unit tests for iterative workflow
  """
  
  import pytest
  from pathlib import Path
  from unittest.mock import Mock, patch
  
  from startd8.iterative_workflow import (
      IterativeDevWorkflow,
      IterativeWorkflowResult,
      Iteration,
      IterationStatus,
      WorkflowStatus,
      ReviewFeedback,
  )
  from startd8.agents import MockAgent
  from startd8.exceptions import APIError, ValidationError
  ```

- [ ] **2.1.2** Test successful workflow (first iteration)
  ```python
  class TestIterativeWorkflow:
      """Test IterativeDevWorkflow class"""
      
      def test_successful_first_iteration(self):
          """Workflow succeeds on first try"""
          # Setup mock agents
          dev = MockAgent(agent_name="mock-dev")
          reviewer = MockAgent(agent_name="mock-reviewer")
          
          workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=3)
          result = workflow.run("Implement a simple function")
          
          assert result.successful
          assert result.total_iterations == 1
          assert result.status == WorkflowStatus.COMPLETED_SUCCESS
          assert result.final_code is not None
          assert len(result.final_code) > 0
  ```

- [ ] **2.1.3** Test workflow with failures and fixes
  ```python
      def test_fails_then_succeeds(self):
          """Workflow fails initially but succeeds after fixes"""
          # Create mock that fails first 2 times
          dev = MockAgent(fail_first_n=2)
          reviewer = MockAgent()
          
          workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=5)
          result = workflow.run("Test task")
          
          assert result.successful
          assert result.total_iterations == 3  # Failed 2, passed on 3rd
          
          # Check iteration history
          assert len(result.iterations) == 3
          assert not result.iterations[0].feedback.passed
          assert not result.iterations[1].feedback.passed
          assert result.iterations[2].feedback.passed
  ```

- [ ] **2.1.4** Test max iterations reached
  ```python
      def test_max_iterations_reached(self):
          """Workflow stops at max iterations"""
          # Mock that never passes
          dev = MockAgent(should_always_fail_review=True)
          reviewer = MockAgent()
          
          workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=3)
          result = workflow.run("Test task")
          
          assert not result.successful
          assert result.total_iterations == 3
          assert result.status == WorkflowStatus.COMPLETED_MAX_ITERATIONS
  ```

- [ ] **2.1.5** Test callback invocation
  ```python
      def test_callback_called_each_iteration(self):
          """Callback is called after each iteration"""
          callback_calls = []
          
          def track_callback(iteration):
              callback_calls.append(iteration.iteration_number)
          
          workflow = IterativeDevWorkflow(
              MockAgent(),
              MockAgent(),
              max_iterations=3,
              on_iteration_complete=track_callback
          )
          
          result = workflow.run("Test")
          
          assert len(callback_calls) == result.total_iterations
          assert callback_calls == list(range(1, result.total_iterations + 1))
  ```

- [ ] **2.1.6** Test context passing
  ```python
      def test_context_passed_to_prompts(self):
          """Context is included in prompts"""
          dev = MockAgent()
          reviewer = MockAgent()
          
          # Capture prompts
          captured_prompts = []
          original_generate = dev.generate
          def capture_generate(prompt):
              captured_prompts.append(prompt)
              return original_generate(prompt)
          dev.generate = capture_generate
          
          workflow = IterativeDevWorkflow(dev, reviewer)
          result = workflow.run(
              "Implement feature",
              context={'framework': 'Flask', 'version': '2.0'}
          )
          
          # Check context was included
          assert any('Flask' in p for p in captured_prompts)
          assert any('2.0' in p for p in captured_prompts)
  ```

- [ ] **2.1.7** Test error handling
  ```python
      def test_api_error_handling(self):
          """API errors are handled gracefully"""
          dev = MockAgent()
          reviewer = MockAgent()
          
          # Make dev raise API error
          dev.generate = Mock(side_effect=APIError("Rate limited", retry_after=60))
          
          workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=2)
          
          with pytest.raises(APIError):  # Or handle differently based on implementation
              workflow.run("Test")
      
      def test_validation_error_handling(self):
          """Validation errors fail fast"""
          workflow = IterativeDevWorkflow(MockAgent(), MockAgent())
          
          with pytest.raises(ValueError):
              workflow.run("")  # Empty task
          
          with pytest.raises(ValueError):
              workflow.run("   ")  # Whitespace only
  ```

- [ ] **2.1.8** Test metrics calculation
  ```python
      def test_metrics_calculated_correctly(self):
          """Total time and tokens are calculated correctly"""
          dev = MockAgent()
          reviewer = MockAgent()
          
          workflow = IterativeDevWorkflow(dev, reviewer, max_iterations=3)
          result = workflow.run("Test")
          
          # Calculate expected totals
          expected_time = sum(i.total_time_ms() for i in result.iterations)
          expected_dev_tokens = sum(
              i.dev_tokens.total for i in result.iterations if i.dev_tokens
          )
          expected_review_tokens = sum(
              i.review_tokens.total for i in result.iterations if i.review_tokens
          )
          
          assert result.total_time_ms == expected_time
          assert result.total_dev_tokens == expected_dev_tokens
          assert result.total_review_tokens == expected_review_tokens
  ```

---

### Task 2.2: Review Parsing Tests

**File**: `tests/unit/test_iterative_workflow.py`  
**Effort**: 4 hours

#### Action Items

- [ ] **2.2.1** Test standard format parsing
  ```python
  class TestReviewParsing:
      """Test review feedback parsing"""
      
      def test_parse_standard_format(self):
          """Parse standard review format"""
          workflow = IterativeDevWorkflow(MockAgent(), MockAgent())
          
          review_text = """
          PASS/FAIL: PASS
          SCORE: 85
          ISSUES:
          - None
          SUGGESTIONS:
          - Consider adding more tests
          REVIEW:
          Good implementation overall.
          """
          
          feedback = workflow._parse_review_feedback(review_text)
          
          assert feedback.passed == True
          assert feedback.score == 85
          assert len(feedback.suggestions) == 1
  ```

- [ ] **2.2.2** Test format variations
  ```python
      @pytest.mark.parametrize("text,expected_passed", [
          ("PASS/FAIL: PASS", True),
          ("PASS/FAIL: Pass", True),
          ("PASS/FAIL: pass", True),
          ("PASS/FAIL: ✓", True),
          ("PASS/FAIL: FAIL", False),
          ("PASS/FAIL: Fail", False),
          ("PASS/FAIL: ✗", False),
          ("PASS/FAIL: NO", False),
      ])
      def test_pass_fail_variations(self, text, expected_passed):
          """Parse various PASS/FAIL formats"""
          workflow = IterativeDevWorkflow(MockAgent(), MockAgent())
          feedback = workflow._parse_review_feedback(text)
          assert feedback.passed == expected_passed
  ```

- [ ] **2.2.3** Test score parsing
  ```python
      @pytest.mark.parametrize("text,expected_score", [
          ("SCORE: 85", 85),
          ("SCORE:85", 85),
          ("Score: 100", 100),
          ("SCORE: 0", 0),
          ("Score 75", 75),
          ("No score here", None),
      ])
      def test_score_parsing(self, text, expected_score):
          """Parse various score formats"""
          workflow = IterativeDevWorkflow(MockAgent(), MockAgent())
          feedback = workflow._parse_review_feedback(text)
          assert feedback.score == expected_score
  ```

- [ ] **2.2.4** Test issue extraction
  ```python
      def test_issues_extraction(self):
          """Extract issues from bullet points"""
          workflow = IterativeDevWorkflow(MockAgent(), MockAgent())
          
          review_text = """
          PASS/FAIL: FAIL
          ISSUES:
          - Missing error handling
          - No type hints
          - Insufficient tests
          SUGGESTIONS:
          - Add docstrings
          """
          
          feedback = workflow._parse_review_feedback(review_text)
          
          assert len(feedback.issues) == 3
          assert "error handling" in feedback.issues[0].lower()
          assert "type hints" in feedback.issues[1].lower()
          assert "tests" in feedback.issues[2].lower()
      
      def test_bullet_point_variations(self):
          """Handle different bullet styles"""
          workflow = IterativeDevWorkflow(MockAgent(), MockAgent())
          
          for bullet in ['-', '•', '*']:
              review_text = f"""
              PASS/FAIL: FAIL
              ISSUES:
              {bullet} Issue one
              {bullet} Issue two
              """
              
              feedback = workflow._parse_review_feedback(review_text)
              assert len(feedback.issues) == 2
  ```

- [ ] **2.2.5** Test malformed input handling
  ```python
      def test_missing_sections(self):
          """Handle missing sections gracefully"""
          workflow = IterativeDevWorkflow(MockAgent(), MockAgent())
          
          # No PASS/FAIL
          feedback = workflow._parse_review_feedback("Just some text")
          assert feedback.passed == False  # Default to fail
          assert feedback.score is None
          assert feedback.issues == []
      
      def test_empty_input(self):
          """Handle empty input"""
          workflow = IterativeDevWorkflow(MockAgent(), MockAgent())
          feedback = workflow._parse_review_feedback("")
          
          assert feedback.passed == False
          assert feedback.score is None
  ```

---

### Task 2.3: Edge Case & Integration Tests

**File**: `tests/unit/test_iterative_workflow.py`  
**Effort**: 4 hours

#### Action Items

- [ ] **2.3.1** Test timeout handling
  ```python
  class TestTimeoutHandling:
      """Test timeout behavior"""
      
      def test_timeout_fails_iteration(self):
          """Timeout causes iteration to fail"""
          slow_agent = MockAgent(response_delay=10)  # 10 second delay
          
          workflow = IterativeDevWorkflow(
              slow_agent,
              MockAgent(),
              max_iterations=2,
              timeout_per_iteration=1  # 1 second timeout
          )
          
          result = workflow.run("Test")
          
          assert not result.successful
          assert "timeout" in result.iterations[0].error.lower()
  ```

- [ ] **2.3.2** Test cost limits
  ```python
  class TestCostControls:
      """Test cost limit behavior"""
      
      def test_max_cost_stops_workflow(self):
          """Workflow stops when max cost exceeded"""
          workflow = IterativeDevWorkflow(
              MockAgent(),
              MockAgent(),
              max_iterations=10,
              max_cost_usd=0.01  # Very low limit
          )
          
          result = workflow.run("Test")
          
          assert not result.successful
          assert result.total_iterations < 10  # Stopped early
      
      def test_warn_cost_logs_warning(self, caplog):
          """Warning logged when warn cost exceeded"""
          workflow = IterativeDevWorkflow(
              MockAgent(),
              MockAgent(),
              max_iterations=3,
              warn_cost_usd=0.001  # Very low threshold
          )
          
          result = workflow.run("Test")
          
          assert "Cost warning" in caplog.text
  ```

- [ ] **2.3.3** Test result serialization
  ```python
  class TestResultSerialization:
      """Test saving and loading results"""
      
      def test_save_and_load_result(self, tmp_path):
          """Result can be saved and loaded"""
          from startd8.iterative_workflow import save_workflow_result
          
          workflow = IterativeDevWorkflow(MockAgent(), MockAgent())
          result = workflow.run("Test")
          
          # Save
          filepath = save_workflow_result(result, tmp_path)
          assert filepath.exists()
          
          # Load and verify
          import json
          with open(filepath) as f:
              data = json.load(f)
          
          assert data['workflow_id'] == result.workflow_id
          assert data['successful'] == result.successful
          assert len(data['iterations']) == len(result.iterations)
  ```

- [ ] **2.3.4** Test with real prompt templates
  ```python
  class TestCustomPrompts:
      """Test custom prompt template handling"""
      
      def test_custom_dev_prompt(self):
          """Custom dev prompt is used"""
          custom_prompt = "CUSTOM: {task_description} {iteration_context} {feedback_section}"
          
          workflow = IterativeDevWorkflow(
              MockAgent(),
              MockAgent(),
              dev_prompt_template=custom_prompt
          )
          
          # Capture actual prompt
          captured = []
          original = workflow.developer_agent.generate
          workflow.developer_agent.generate = lambda p: (captured.append(p), original(p))[1]
          
          workflow.run("Test task")
          
          assert captured[0].startswith("CUSTOM:")
      
      def test_custom_review_prompt(self):
          """Custom review prompt is used"""
          custom_prompt = "REVIEW: {task_description}\nCODE: {implementation}"
          
          workflow = IterativeDevWorkflow(
              MockAgent(),
              MockAgent(),
              review_prompt_template=custom_prompt
          )
          
          # Similar capture test...
  ```

---

### Task 2.4: Test Coverage Report

**Effort**: 2 hours

#### Action Items

- [ ] **2.4.1** Run tests with coverage
  ```bash
  pytest tests/unit/test_iterative_workflow.py -v --cov=startd8.iterative_workflow --cov-report=html
  ```

- [ ] **2.4.2** Achieve minimum 80% coverage

- [ ] **2.4.3** Document any intentionally uncovered code

- [ ] **2.4.4** Add coverage badge to README

---

## Phase 3: Polish & Hardening (Week 3)

**Timeline**: Days 11-15  
**Effort**: 8-12 hours  
**Priority**: 🟢 IMPORTANT

### Task 3.1: Complete Type Hints

**File**: `src/startd8/iterative_workflow.py`  
**Effort**: 3 hours

#### Action Items

- [ ] **3.1.1** Add missing type hints to all methods
  ```python
  from typing import Dict, Any, Optional, Callable, List
  
  def _build_dev_prompt(
      self,
      task_description: str,
      iteration_num: int,
      previous_feedback: Optional[ReviewFeedback],
      current_implementation: str,
      context: Optional[Dict[str, Any]]
  ) -> str:
      ...
  
  def _parse_review_feedback(self, review_text: str) -> ReviewFeedback:
      ...
  
  def _validate_inputs(
      self,
      task_description: str,
      context: Optional[Dict[str, Any]]
  ) -> None:
      ...
  ```

- [ ] **3.1.2** Add type alias for callbacks
  ```python
  from typing import Callable, TypeAlias
  
  IterationCallback: TypeAlias = Callable[[Iteration], None]
  ProgressCallback: TypeAlias = Callable[[int, int], None]  # (current, total)
  ```

- [ ] **3.1.3** Run mypy and fix issues
  ```bash
  mypy src/startd8/iterative_workflow.py --strict
  ```

- [ ] **3.1.4** Add py.typed marker for PEP 561

---

### Task 3.2: Documentation Updates

**Effort**: 2 hours

#### Action Items

- [ ] **3.2.1** Update docstrings with complete examples
- [ ] **3.2.2** Add architecture diagram to docs
- [ ] **3.2.3** Add API reference section
- [ ] **3.2.4** Add changelog entry
- [ ] **3.2.5** Update README with workflow feature

---

### Task 3.3: Observability & Metrics

**Effort**: 3 hours

#### Action Items

- [ ] **3.3.1** Add structured logging with consistent format
  ```python
  def run(self, task_description: str, ...):
      logger.info(
          "workflow_started",
          extra={
              'event': 'workflow_started',
              'workflow_id': workflow_id,
              'task_length': len(task_description),
              'max_iterations': self.max_iterations,
          }
      )
      
      # ... later ...
      
      logger.info(
          "workflow_completed",
          extra={
              'event': 'workflow_completed',
              'workflow_id': workflow_id,
              'successful': result.successful,
              'iterations': result.total_iterations,
              'total_time_ms': result.total_time_ms,
              'total_cost': result.total_cost,
          }
      )
  ```

- [ ] **3.3.2** Add optional metrics collection
  ```python
  class WorkflowMetrics:
      """Collect workflow metrics"""
      
      def __init__(self):
          self.total_workflows = 0
          self.successful_workflows = 0
          self.total_iterations = 0
          self.total_cost = 0.0
          self.average_iterations = 0.0
      
      def record(self, result: IterativeWorkflowResult):
          self.total_workflows += 1
          if result.successful:
              self.successful_workflows += 1
          self.total_iterations += result.total_iterations
          self.total_cost += result.total_cost
          self.average_iterations = self.total_iterations / self.total_workflows
  ```

---

### Task 3.4: Performance Optimization

**Effort**: 2 hours

#### Action Items

- [ ] **3.4.1** Add optional caching
  ```python
  def __init__(self, ..., enable_cache: bool = False):
      self.enable_cache = enable_cache
      self._cache: Dict[str, Any] = {} if enable_cache else {}
  ```

- [ ] **3.4.2** Profile typical workflow and document benchmarks

- [ ] **3.4.3** Add async support (future enhancement)
  ```python
  async def run_async(self, task_description: str, ...) -> IterativeWorkflowResult:
      """Async version of run() for concurrent workflows"""
      # Future implementation
      pass
  ```

---

## Summary Checklist

### Week 1: Critical Fixes ✅

- [ ] Task 1.1: Granular exception handling (4h)
- [ ] Task 1.2: Robust review parsing (4h)
- [ ] Task 1.3: Input validation (2h)
- [ ] Task 1.4: Timeout handling (3h)
- [ ] Task 1.5: Cost controls (2h)

**Week 1 Total**: 15 hours

### Week 2: Testing ✅

- [ ] Task 2.1: Core workflow tests (8h)
- [ ] Task 2.2: Review parsing tests (4h)
- [ ] Task 2.3: Edge case & integration tests (4h)
- [ ] Task 2.4: Coverage report (2h)

**Week 2 Total**: 18 hours

### Week 3: Polish ✅

- [ ] Task 3.1: Complete type hints (3h)
- [ ] Task 3.2: Documentation updates (2h)
- [ ] Task 3.3: Observability & metrics (3h)
- [ ] Task 3.4: Performance optimization (2h)

**Week 3 Total**: 10 hours

---

## **Grand Total: 43 hours**

---

## Success Criteria

### Minimum for Production
- [ ] All critical fixes implemented (Week 1)
- [ ] Unit test coverage ≥ 80%
- [ ] No critical/high mypy errors
- [ ] All tests passing

### Nice to Have
- [ ] Test coverage ≥ 90%
- [ ] Full type hint coverage
- [ ] Performance benchmarks documented
- [ ] Async support

---

## Notes

- Start with Task 1.1 (exception handling) as it affects all other code
- Task 1.2 (review parsing) should be done before writing tests for it
- Testing tasks can be done in parallel with polish tasks
- Keep PR sizes manageable (one task per PR is ideal)

---

**Created**: December 7, 2025  
**Status**: Ready for Implementation  
**Estimated Completion**: 3 weeks
