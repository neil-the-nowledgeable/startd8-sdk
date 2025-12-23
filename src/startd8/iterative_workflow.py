"""
Iterative Development Workflow

Implements a dev-review-fix loop where:
1. Developer agent implements a task
2. Reviewer agent reviews the code and tests functionality
3. If issues found, sends back to developer with feedback
4. Loop continues until code passes review or max iterations reached
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import json
import uuid

from .agents import BaseAgent
from .models import TokenUsage
from .logging_config import get_logger

logger = get_logger(__name__)


class IterationStatus(str, Enum):
    """Status of a single iteration"""
    PENDING = "pending"
    DEVELOPING = "developing"
    REVIEWING = "reviewing"
    FIXING = "fixing"
    PASSED = "passed"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    """Overall workflow status"""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED_SUCCESS = "completed_success"
    COMPLETED_MAX_ITERATIONS = "completed_max_iterations"
    FAILED = "failed"


@dataclass
class ReviewFeedback:
    """Feedback from reviewer agent"""
    passed: bool
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    score: Optional[int] = None  # 0-100 quality score
    review_text: str = ""
    
    def has_critical_issues(self) -> bool:
        """Check if there are critical issues"""
        return not self.passed and len(self.issues) > 0


@dataclass
class Iteration:
    """Single iteration in the dev-review loop"""
    iteration_number: int
    status: IterationStatus
    
    # Developer phase
    dev_prompt: str = ""
    dev_response: str = ""
    dev_agent_name: str = ""
    dev_time_ms: int = 0
    dev_tokens: Optional[TokenUsage] = None
    
    # Review phase
    review_prompt: str = ""
    review_response: str = ""
    review_agent_name: str = ""
    review_time_ms: int = 0
    review_tokens: Optional[TokenUsage] = None
    feedback: Optional[ReviewFeedback] = None
    
    # Metadata
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    
    def is_complete(self) -> bool:
        """Check if iteration is complete"""
        return self.status in (IterationStatus.PASSED, IterationStatus.FAILED)
    
    def total_time_ms(self) -> int:
        """Get total time for this iteration"""
        return self.dev_time_ms + self.review_time_ms


@dataclass
class IterativeWorkflowResult:
    """Result of the complete iterative workflow"""
    workflow_id: str
    task_description: str
    status: WorkflowStatus
    
    iterations: List[Iteration] = field(default_factory=list)
    
    final_code: str = ""
    final_review: Optional[ReviewFeedback] = None
    
    total_iterations: int = 0
    successful: bool = False
    
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    
    # Aggregated metrics
    total_time_ms: int = 0
    total_dev_tokens: int = 0
    total_review_tokens: int = 0
    total_cost: float = 0.0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get workflow summary"""
        return {
            'workflow_id': self.workflow_id,
            'task': self.task_description[:100],
            'status': self.status,
            'successful': self.successful,
            'total_iterations': self.total_iterations,
            'total_time_seconds': self.total_time_ms / 1000,
            'total_tokens': self.total_dev_tokens + self.total_review_tokens,
            'total_cost': self.total_cost,
            'iterations_summary': [
                {
                    'iteration': i.iteration_number,
                    'status': i.status,
                    'passed_review': i.feedback.passed if i.feedback else None,
                    'issues_count': len(i.feedback.issues) if i.feedback else 0
                }
                for i in self.iterations
            ]
        }


class IterativeDevWorkflow:
    """
    Iterative development workflow with code review feedback loop.
    
    Pattern:
    1. Dev Agent: Implement task
    2. Review Agent: Review code, test functionality
    3. If issues found: Send feedback to Dev Agent
    4. Dev Agent: Fix issues based on feedback
    5. Repeat steps 2-4 until passed or max iterations
    """
    
    # Default prompts
    DEFAULT_DEV_PROMPT_TEMPLATE = """You are an expert software developer. Your task is to implement the following:

{task_description}

{iteration_context}

Requirements:
- Write clean, well-documented code
- Follow best practices
- Include error handling
- Make it production-ready

{feedback_section}

Please provide your complete implementation."""

    DEFAULT_REVIEW_PROMPT_TEMPLATE = """You are an expert code reviewer and QA engineer. Review the following implementation:

TASK:
{task_description}

IMPLEMENTATION:
{implementation}

Your review should:
1. Check if the implementation fulfills the requirements
2. Test the functionality (if possible)
3. Identify any bugs, errors, or issues
4. Check code quality, readability, and best practices
5. Provide specific, actionable feedback

Format your response as:
PASS/FAIL: [Your verdict]
SCORE: [0-100]
ISSUES:
- [List any critical issues]
SUGGESTIONS:
- [List improvement suggestions]
REVIEW:
[Detailed review text]"""

    def __init__(
        self,
        developer_agent: BaseAgent,
        reviewer_agent: BaseAgent,
        max_iterations: int = 3,
        dev_prompt_template: Optional[str] = None,
        review_prompt_template: Optional[str] = None,
        on_iteration_complete: Optional[Callable[[Iteration], None]] = None
    ):
        """
        Initialize iterative workflow.
        
        Args:
            developer_agent: Agent that implements tasks
            reviewer_agent: Agent that reviews implementations
            max_iterations: Maximum number of dev-review cycles
            dev_prompt_template: Custom developer prompt template
            review_prompt_template: Custom reviewer prompt template
            on_iteration_complete: Callback after each iteration
        """
        self.developer_agent = developer_agent
        self.reviewer_agent = reviewer_agent
        self.max_iterations = max_iterations
        
        self.dev_prompt_template = dev_prompt_template or self.DEFAULT_DEV_PROMPT_TEMPLATE
        self.review_prompt_template = review_prompt_template or self.DEFAULT_REVIEW_PROMPT_TEMPLATE
        
        self.on_iteration_complete = on_iteration_complete
    
    def run(self, task_description: str, context: Optional[Dict[str, Any]] = None) -> IterativeWorkflowResult:
        """
        Run the iterative development workflow.
        
        Args:
            task_description: Description of the task to implement
            context: Optional context (existing code, requirements, etc.)
            
        Returns:
            IterativeWorkflowResult with complete workflow history
        """
        workflow_id = f"iter-workflow-{uuid.uuid4().hex[:12]}"
        result = IterativeWorkflowResult(
            workflow_id=workflow_id,
            task_description=task_description,
            status=WorkflowStatus.IN_PROGRESS
        )
        
        logger.info(f"Starting iterative workflow {workflow_id}", extra={
            'workflow_id': workflow_id,
            'task': task_description[:100],
            'max_iterations': self.max_iterations
        })
        
        current_implementation = ""
        previous_feedback: Optional[ReviewFeedback] = None
        
        for iteration_num in range(1, self.max_iterations + 1):
            logger.info(f"Starting iteration {iteration_num}/{self.max_iterations}")
            
            iteration = Iteration(
                iteration_number=iteration_num,
                status=IterationStatus.PENDING
            )
            
            try:
                # Phase 1: Development
                iteration.status = IterationStatus.DEVELOPING
                dev_prompt = self._build_dev_prompt(
                    task_description,
                    iteration_num,
                    previous_feedback,
                    current_implementation,
                    context
                )
                iteration.dev_prompt = dev_prompt
                
                logger.debug(
                    f"Sending task to developer agent: {self.developer_agent.agent_name}",
                    extra={
                        "iteration": iteration_num,
                        "workflow_id": result.workflow_id,
                        "task": task_description[:100] if task_description else None
                    }
                )
                try:
                    dev_response = self.developer_agent.generate(dev_prompt)
                except Exception as e:
                    from .exceptions import APIError, AgentError
                    logger.error(
                        f"Developer agent failed in iteration {iteration_num}: {e}",
                        exc_info=True,
                        extra={
                            "iteration": iteration_num,
                            "workflow_id": result.workflow_id,
                            "agent_name": self.developer_agent.agent_name,
                            "task": task_description[:100] if task_description else None
                        }
                    )
                    # Re-raise to be caught by outer exception handler
                    raise
                
                iteration.dev_response = dev_response.response
                iteration.dev_agent_name = self.developer_agent.agent_name
                iteration.dev_time_ms = dev_response.response_time_ms
                iteration.dev_tokens = dev_response.token_usage
                
                current_implementation = dev_response.response
                
                # Phase 2: Review
                iteration.status = IterationStatus.REVIEWING
                review_prompt = self._build_review_prompt(
                    task_description,
                    current_implementation,
                    context
                )
                iteration.review_prompt = review_prompt
                
                logger.debug(
                    f"Sending to reviewer agent: {self.reviewer_agent.agent_name}",
                    extra={
                        "iteration": iteration_num,
                        "workflow_id": result.workflow_id,
                        "task": task_description[:100] if task_description else None
                    }
                )
                try:
                    review_response = self.reviewer_agent.generate(review_prompt)
                except Exception as e:
                    from .exceptions import APIError, AgentError
                    logger.error(
                        f"Reviewer agent failed in iteration {iteration_num}: {e}",
                        exc_info=True,
                        extra={
                            "iteration": iteration_num,
                            "workflow_id": result.workflow_id,
                            "agent_name": self.reviewer_agent.agent_name,
                            "task": task_description[:100] if task_description else None
                        }
                    )
                    # Re-raise to be caught by outer exception handler
                    raise
                
                iteration.review_response = review_response.response
                iteration.review_agent_name = self.reviewer_agent.agent_name
                iteration.review_time_ms = review_response.response_time_ms
                iteration.review_tokens = review_response.token_usage
                
                # Parse review feedback
                feedback = self._parse_review_feedback(review_response.response)
                iteration.feedback = feedback
                
                # Update iteration status based on review
                if feedback.passed:
                    iteration.status = IterationStatus.PASSED
                    iteration.completed_at = datetime.now(timezone.utc)
                    result.iterations.append(iteration)
                    
                    # Success! Exit loop
                    result.status = WorkflowStatus.COMPLETED_SUCCESS
                    result.successful = True
                    result.final_code = current_implementation
                    result.final_review = feedback
                    
                    logger.info(f"Workflow completed successfully on iteration {iteration_num}")
                    
                    if self.on_iteration_complete:
                        self.on_iteration_complete(iteration)
                    
                    break
                else:
                    # Failed review - prepare for next iteration
                    iteration.status = IterationStatus.FIXING
                    iteration.completed_at = datetime.now(timezone.utc)
                    result.iterations.append(iteration)
                    
                    previous_feedback = feedback
                    
                    logger.info(
                        f"Iteration {iteration_num} failed review with {len(feedback.issues)} issues",
                        extra={'issues': feedback.issues[:3]}
                    )
                    
                    if self.on_iteration_complete:
                        self.on_iteration_complete(iteration)
                    
                    # Check if this was the last iteration
                    if iteration_num >= self.max_iterations:
                        result.status = WorkflowStatus.COMPLETED_MAX_ITERATIONS
                        result.successful = False
                        result.final_code = current_implementation
                        result.final_review = feedback
                        
                        logger.warning(f"Workflow reached max iterations ({self.max_iterations})")
                        break
                    
            except Exception as e:
                # Import specific exception types for better error handling
                from .exceptions import APIError, AgentError, ConfigurationError
                
                # Log error with full workflow context
                logger.error(
                    f"Error in iteration {iteration_num}: {e}",
                    exc_info=True,
                    extra={
                        "iteration": iteration_num,
                        "workflow_id": result.workflow_id,
                        "task": task_description[:100] if task_description else None,
                        "developer_agent": self.developer_agent.agent_name,
                        "reviewer_agent": self.reviewer_agent.agent_name,
                        "error_type": type(e).__name__
                    }
                )
                
                iteration.status = IterationStatus.FAILED
                iteration.completed_at = datetime.now(timezone.utc)
                result.iterations.append(iteration)
                
                result.status = WorkflowStatus.FAILED
                result.successful = False
                
                # Re-raise specific exceptions to allow proper error handling upstream
                # Generic exceptions are wrapped but still re-raised
                if isinstance(e, (APIError, AgentError, ConfigurationError)):
                    raise  # Re-raise specific exceptions
                else:
                    # Wrap unexpected errors in AgentError for consistency
                    from .exceptions import AgentError
                    raise AgentError(
                        f"Unexpected error in iteration {iteration_num}: {e}",
                        agent_name=self.developer_agent.agent_name,
                        original_error=e
                    ) from e
                
                if self.on_iteration_complete:
                    self.on_iteration_complete(iteration)
                
                break
        
        # Finalize result
        result.completed_at = datetime.now(timezone.utc)
        result.total_iterations = len(result.iterations)
        
        # Calculate aggregated metrics
        for iteration in result.iterations:
            result.total_time_ms += iteration.total_time_ms()
            if iteration.dev_tokens:
                result.total_dev_tokens += iteration.dev_tokens.total
            if iteration.review_tokens:
                result.total_review_tokens += iteration.review_tokens.total
        
        # Calculate cost (simplified)
        total_tokens = result.total_dev_tokens + result.total_review_tokens
        result.total_cost = (total_tokens / 1_000_000) * 5.0  # Rough estimate
        
        logger.info(
            f"Workflow {workflow_id} completed",
            extra={
                'status': result.status,
                'successful': result.successful,
                'iterations': result.total_iterations,
                'total_time_ms': result.total_time_ms
            }
        )
        
        return result
    
    def _build_dev_prompt(
        self,
        task_description: str,
        iteration_num: int,
        previous_feedback: Optional[ReviewFeedback],
        current_implementation: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for developer agent"""
        
        # Iteration context
        if iteration_num == 1:
            iteration_context = "This is the initial implementation."
        else:
            iteration_context = f"This is iteration {iteration_num}. Your previous implementation failed review."
        
        # Feedback section
        if previous_feedback and not previous_feedback.passed:
            feedback_lines = ["PREVIOUS REVIEW FEEDBACK:", ""]
            
            if previous_feedback.issues:
                feedback_lines.append("ISSUES TO FIX:")
                for issue in previous_feedback.issues:
                    feedback_lines.append(f"  • {issue}")
                feedback_lines.append("")
            
            if previous_feedback.suggestions:
                feedback_lines.append("SUGGESTIONS:")
                for suggestion in previous_feedback.suggestions:
                    feedback_lines.append(f"  • {suggestion}")
                feedback_lines.append("")
            
            if current_implementation:
                feedback_lines.append("YOUR PREVIOUS IMPLEMENTATION:")
                feedback_lines.append("```")
                feedback_lines.append(current_implementation)
                feedback_lines.append("```")
                feedback_lines.append("")
            
            feedback_lines.append("Please fix the issues and improve based on the feedback.")
            
            feedback_section = "\n".join(feedback_lines)
        else:
            feedback_section = ""
        
        # Add context if provided
        if context:
            context_str = "\n\nADDITIONAL CONTEXT:\n" + json.dumps(context, indent=2)
            task_description = task_description + context_str
        
        return self.dev_prompt_template.format(
            task_description=task_description,
            iteration_context=iteration_context,
            feedback_section=feedback_section
        )
    
    def _build_review_prompt(
        self,
        task_description: str,
        implementation: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for reviewer agent"""
        
        if context:
            context_str = "\n\nCONTEXT:\n" + json.dumps(context, indent=2)
            task_description = task_description + context_str
        
        return self.review_prompt_template.format(
            task_description=task_description,
            implementation=implementation
        )
    
    def _parse_review_feedback(self, review_text: str) -> ReviewFeedback:
        """
        Parse review response into structured feedback.
        
        Expected format:
        PASS/FAIL: [verdict]
        SCORE: [0-100]
        ISSUES:
        - issue 1
        - issue 2
        SUGGESTIONS:
        - suggestion 1
        REVIEW:
        [detailed text]
        """
        lines = review_text.split('\n')
        
        passed = False
        score = None
        issues = []
        suggestions = []
        current_section = None
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('PASS/FAIL:'):
                verdict = line.split(':', 1)[1].strip().upper()
                passed = 'PASS' in verdict
            
            elif line.startswith('SCORE:'):
                try:
                    score = int(line.split(':', 1)[1].strip())
                except (ValueError, IndexError):
                    score = None
            
            elif line.startswith('ISSUES:'):
                current_section = 'issues'
            
            elif line.startswith('SUGGESTIONS:'):
                current_section = 'suggestions'
            
            elif line.startswith('REVIEW:'):
                current_section = 'review'
            
            elif line.startswith('-') or line.startswith('•'):
                item = line.lstrip('-•').strip()
                if item:
                    if current_section == 'issues':
                        issues.append(item)
                    elif current_section == 'suggestions':
                        suggestions.append(item)
        
        return ReviewFeedback(
            passed=passed,
            issues=issues,
            suggestions=suggestions,
            score=score,
            review_text=review_text
        )


def save_workflow_result(result: IterativeWorkflowResult, output_dir: Path) -> Path:
    """
    Save workflow result to JSON file.
    
    Args:
        result: Workflow result to save
        output_dir: Directory to save result
        
    Returns:
        Path to saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{result.workflow_id}.json"
    filepath = output_dir / filename
    
    # Convert to dict for JSON serialization
    data = {
        'workflow_id': result.workflow_id,
        'task_description': result.task_description,
        'status': result.status,
        'successful': result.successful,
        'total_iterations': result.total_iterations,
        'created_at': result.created_at.isoformat(),
        'completed_at': result.completed_at.isoformat() if result.completed_at else None,
        'total_time_ms': result.total_time_ms,
        'total_cost': result.total_cost,
        'final_code': result.final_code,
        'final_review': {
            'passed': result.final_review.passed,
            'score': result.final_review.score,
            'issues': result.final_review.issues,
            'suggestions': result.final_review.suggestions
        } if result.final_review else None,
        'iterations': [
            {
                'iteration_number': i.iteration_number,
                'status': i.status,
                'dev_agent': i.dev_agent_name,
                'review_agent': i.review_agent_name,
                'dev_time_ms': i.dev_time_ms,
                'review_time_ms': i.review_time_ms,
                'feedback': {
                    'passed': i.feedback.passed,
                    'score': i.feedback.score,
                    'issues': i.feedback.issues,
                    'suggestions': i.feedback.suggestions
                } if i.feedback else None
            }
            for i in result.iterations
        ]
    }
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"Saved workflow result to {filepath}")
    return filepath
