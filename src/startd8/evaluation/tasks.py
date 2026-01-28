"""
Task Corpus Models for Evaluation System

Defines the data models for evaluation tasks, filters, and results.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskCategory(str, Enum):
    """Categories of evaluation tasks"""
    DESIGN = "design"
    CODING = "coding"
    TESTING = "testing"
    REVIEW = "review"
    DOCUMENTATION = "documentation"


class TaskDifficulty(str, Enum):
    """Difficulty levels for tasks"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Capability(str, Enum):
    """Capabilities that tasks can test"""
    REASONING = "reasoning"
    CODE_GENERATION = "code_generation"
    CODE_ANALYSIS = "code_analysis"
    ARCHITECTURE = "architecture"
    API_DESIGN = "api_design"
    DATABASE_DESIGN = "database_design"
    TESTING_STRATEGY = "testing_strategy"
    DOCUMENTATION = "documentation"
    DEBUGGING = "debugging"
    OPTIMIZATION = "optimization"
    SECURITY_ANALYSIS = "security_analysis"
    REFACTORING = "refactoring"
    ALGORITHM_DESIGN = "algorithm_design"
    SYSTEM_DESIGN = "system_design"


class TaskVariable(BaseModel):
    """A variable placeholder in a task prompt template"""
    name: str = Field(description="Variable name (e.g., 'LANGUAGE')")
    description: str = Field(default="", description="Help text for the variable")
    default: Optional[str] = Field(default=None, description="Default value if not provided")
    required: bool = Field(default=True, description="Whether this variable must be provided")
    options: List[str] = Field(default_factory=list, description="Valid options for the variable")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate variable name format"""
        if not v or not v.strip():
            raise ValueError("Variable name cannot be empty")
        if not re.match(r'^[A-Z][A-Z0-9_]*$', v):
            raise ValueError(
                f"Variable name '{v}' must be uppercase with underscores (e.g., 'PROJECT_NAME')"
            )
        return v.strip()

    @property
    def is_optional(self) -> bool:
        """Check if variable is optional (has default or not required)"""
        return self.default is not None or not self.required


class EvaluationCriteria(BaseModel):
    """Criteria for evaluating task responses"""
    name: str = Field(description="Criteria name (e.g., 'correctness')")
    description: str = Field(description="What this criterion measures")
    weight: float = Field(default=1.0, description="Weight for scoring (0.0-1.0)", ge=0.0, le=1.0)
    required: bool = Field(default=True, description="Whether this criterion must be met")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate criteria name"""
        if not v or not v.strip():
            raise ValueError("Criteria name cannot be empty")
        return v.strip().lower()


class Task(BaseModel):
    """An evaluation task definition"""
    id: str = Field(description="Unique task identifier (e.g., 'design-rest-api')")
    name: str = Field(description="Human-readable task name")
    description: str = Field(default="", description="Detailed task description")
    category: TaskCategory = Field(description="Task category")
    difficulty: TaskDifficulty = Field(description="Task difficulty level")
    prompt_template: str = Field(description="Prompt template with {{VARIABLE}} placeholders")
    variables: List[TaskVariable] = Field(default_factory=list, description="Template variables")
    capabilities_tested: List[Capability] = Field(
        default_factory=list, description="Capabilities this task evaluates"
    )
    evaluation_criteria: List[EvaluationCriteria] = Field(
        default_factory=list, description="Criteria for evaluating responses"
    )
    reference_solution: Optional[str] = Field(
        default=None, description="Optional reference solution for comparison"
    )
    tags: List[str] = Field(default_factory=list, description="Additional categorization tags")
    version: str = Field(default="1.0.0", description="Task version")

    model_config = ConfigDict(use_enum_values=True)

    @field_validator('id')
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate task ID format"""
        if not v or not v.strip():
            raise ValueError("Task ID cannot be empty")
        if not re.match(r'^[a-z][a-z0-9-]*$', v):
            raise ValueError(
                f"Task ID '{v}' must be lowercase with hyphens (e.g., 'design-rest-api')"
            )
        return v.strip()

    @field_validator('prompt_template')
    @classmethod
    def validate_prompt_template(cls, v: str) -> str:
        """Validate prompt template is not empty"""
        if not v or not v.strip():
            raise ValueError("Prompt template cannot be empty")
        return v.strip()

    @field_validator('version')
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate semver format"""
        semver_pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$'
        if not re.match(semver_pattern, v):
            raise ValueError(
                f"Version '{v}' does not match semver format (e.g., '1.0.0', '1.0.0-alpha')"
            )
        return v

    def render_prompt(self, variable_values: Optional[Dict[str, str]] = None) -> str:
        """
        Render the prompt template with provided variable values.

        Args:
            variable_values: Dictionary mapping variable names to values

        Returns:
            Rendered prompt string

        Raises:
            ValueError: If required variables are missing
        """
        values = variable_values or {}
        missing = self.get_missing_variables(values)
        if missing:
            raise ValueError(f"Missing required variables: {', '.join(missing)}")

        result = self.prompt_template
        for var in self.variables:
            placeholder = f"{{{{{var.name}}}}}"
            value = values.get(var.name, var.default or "")
            result = result.replace(placeholder, value)

        return result

    def get_missing_variables(self, provided: Optional[Dict[str, str]] = None) -> List[str]:
        """
        Get list of required variables that are not provided.

        Args:
            provided: Dictionary of provided variable values

        Returns:
            List of missing required variable names
        """
        provided = provided or {}
        missing = []
        for var in self.variables:
            if var.required and var.name not in provided and var.default is None:
                missing.append(var.name)
        return missing


class TaskFilter(BaseModel):
    """Filter for selecting tasks from a corpus"""
    categories: Optional[List[TaskCategory]] = Field(
        default=None, description="Filter by categories"
    )
    difficulties: Optional[List[TaskDifficulty]] = Field(
        default=None, description="Filter by difficulties"
    )
    capabilities: Optional[List[Capability]] = Field(
        default=None, description="Filter by capabilities tested"
    )
    tags: Optional[List[str]] = Field(
        default=None, description="Filter by tags (any match)"
    )
    ids: Optional[List[str]] = Field(
        default=None, description="Filter by specific task IDs"
    )

    model_config = ConfigDict(use_enum_values=True)

    def matches(self, task: Task) -> bool:
        """
        Check if a task matches this filter.

        Args:
            task: Task to check

        Returns:
            True if task matches all specified filter criteria
        """
        # Category filter
        if self.categories is not None:
            task_category = task.category if isinstance(task.category, str) else task.category.value
            if task_category not in [c if isinstance(c, str) else c.value for c in self.categories]:
                return False

        # Difficulty filter
        if self.difficulties is not None:
            task_difficulty = task.difficulty if isinstance(task.difficulty, str) else task.difficulty.value
            if task_difficulty not in [d if isinstance(d, str) else d.value for d in self.difficulties]:
                return False

        # Capabilities filter (task must have at least one matching capability)
        if self.capabilities is not None:
            task_caps = [c if isinstance(c, str) else c.value for c in task.capabilities_tested]
            filter_caps = [c if isinstance(c, str) else c.value for c in self.capabilities]
            if not any(cap in task_caps for cap in filter_caps):
                return False

        # Tags filter (task must have at least one matching tag)
        if self.tags is not None:
            if not any(tag in task.tags for tag in self.tags):
                return False

        # IDs filter
        if self.ids is not None:
            if task.id not in self.ids:
                return False

        return True


class TaskCorpus(BaseModel):
    """A collection of evaluation tasks"""
    name: str = Field(description="Corpus name")
    description: str = Field(default="", description="Corpus description")
    tasks: Dict[str, Task] = Field(default_factory=dict, description="Tasks by ID")

    def add_task(self, task: Task) -> None:
        """
        Add a task to the corpus.

        Args:
            task: Task to add
        """
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get a task by ID.

        Args:
            task_id: Task identifier

        Returns:
            Task if found, None otherwise
        """
        return self.tasks.get(task_id)

    def list_tasks(self, filter: Optional[TaskFilter] = None) -> List[Task]:
        """
        List tasks, optionally filtered.

        Args:
            filter: Optional filter to apply

        Returns:
            List of matching tasks
        """
        tasks = list(self.tasks.values())
        if filter is not None:
            tasks = [t for t in tasks if filter.matches(t)]
        return sorted(tasks, key=lambda t: (t.category, t.difficulty, t.name))

    def get_by_category(self, category: TaskCategory) -> List[Task]:
        """
        Get all tasks in a category.

        Args:
            category: Category to filter by

        Returns:
            List of tasks in the category
        """
        category_value = category if isinstance(category, str) else category.value
        return [
            t for t in self.tasks.values()
            if (t.category if isinstance(t.category, str) else t.category.value) == category_value
        ]

    def summary(self) -> Dict[str, Any]:
        """
        Get a summary of the corpus.

        Returns:
            Dictionary with corpus statistics
        """
        tasks = list(self.tasks.values())

        # Count by category
        by_category: Dict[str, int] = {}
        for task in tasks:
            cat = task.category if isinstance(task.category, str) else task.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

        # Count by difficulty
        by_difficulty: Dict[str, int] = {}
        for task in tasks:
            diff = task.difficulty if isinstance(task.difficulty, str) else task.difficulty.value
            by_difficulty[diff] = by_difficulty.get(diff, 0) + 1

        # Collect all capabilities
        all_capabilities: set = set()
        for task in tasks:
            for cap in task.capabilities_tested:
                cap_value = cap if isinstance(cap, str) else cap.value
                all_capabilities.add(cap_value)

        # Collect all tags
        all_tags: set = set()
        for task in tasks:
            all_tags.update(task.tags)

        return {
            "name": self.name,
            "description": self.description,
            "total_tasks": len(tasks),
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "capabilities": sorted(all_capabilities),
            "tags": sorted(all_tags),
        }

    def merge(self, other: "TaskCorpus", overwrite: bool = False) -> "TaskCorpus":
        """
        Merge another corpus into this one.

        Args:
            other: Corpus to merge from
            overwrite: If True, overwrite existing tasks with same ID

        Returns:
            Self for chaining
        """
        for task_id, task in other.tasks.items():
            if overwrite or task_id not in self.tasks:
                self.tasks[task_id] = task
        return self


class TaskResult(BaseModel):
    """Result of running a single task against an agent"""
    task_id: str = Field(description="Task identifier")
    agent_name: str = Field(description="Agent that ran the task")
    model: str = Field(description="Model used")
    prompt: str = Field(description="Rendered prompt sent to agent")
    response: str = Field(description="Agent's response")
    response_time_ms: int = Field(description="Response time in milliseconds", ge=0)
    token_usage: Optional[Dict[str, int]] = Field(
        default=None, description="Token usage (input, output, total)"
    )
    cost_estimate: Optional[float] = Field(
        default=None, description="Estimated cost in USD"
    )
    score: Optional[float] = Field(
        default=None, description="Overall evaluation score (0.0-1.0)", ge=0.0, le=1.0
    )
    criteria_scores: Dict[str, float] = Field(
        default_factory=dict, description="Scores by evaluation criteria"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the result was recorded"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(use_enum_values=True)


class EvaluationRun(BaseModel):
    """A complete evaluation run across multiple tasks"""
    run_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique run identifier"
    )
    corpus_name: str = Field(description="Name of the corpus used")
    results: List[TaskResult] = Field(default_factory=list, description="Results from each task")
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Run start time"
    )
    completed_at: Optional[datetime] = Field(default=None, description="Run completion time")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Run metadata")

    model_config = ConfigDict(use_enum_values=True)

    def add_result(self, result: TaskResult) -> None:
        """Add a task result to this run."""
        self.results.append(result)

    def complete(self) -> None:
        """Mark the run as complete."""
        self.completed_at = datetime.now(timezone.utc)

    @property
    def total_tasks(self) -> int:
        """Total number of tasks run."""
        return len(self.results)

    @property
    def tasks_scored(self) -> int:
        """Number of tasks with scores."""
        return sum(1 for r in self.results if r.score is not None)

    @property
    def average_score(self) -> Optional[float]:
        """Average score across scored tasks."""
        scored = [r.score for r in self.results if r.score is not None]
        if not scored:
            return None
        return sum(scored) / len(scored)

    @property
    def total_time_ms(self) -> int:
        """Total response time across all tasks."""
        return sum(r.response_time_ms for r in self.results)

    @property
    def total_cost(self) -> float:
        """Total estimated cost across all tasks."""
        return sum(r.cost_estimate or 0.0 for r in self.results)

    def summary_by_category(self) -> Dict[str, Dict[str, Any]]:
        """
        Get summary statistics grouped by task category.

        Returns:
            Dictionary mapping category to statistics
        """
        by_category: Dict[str, List[TaskResult]] = {}
        for result in self.results:
            # Extract category from task_id prefix
            category = result.task_id.split("-")[0] if "-" in result.task_id else "unknown"
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(result)

        summaries = {}
        for category, results in by_category.items():
            scores = [r.score for r in results if r.score is not None]
            summaries[category] = {
                "count": len(results),
                "scored": len(scores),
                "average_score": sum(scores) / len(scores) if scores else None,
                "total_time_ms": sum(r.response_time_ms for r in results),
                "total_cost": sum(r.cost_estimate or 0.0 for r in results),
            }
        return summaries

    def summary_by_agent(self) -> Dict[str, Dict[str, Any]]:
        """
        Get summary statistics grouped by agent.

        Returns:
            Dictionary mapping agent name to statistics
        """
        by_agent: Dict[str, List[TaskResult]] = {}
        for result in self.results:
            if result.agent_name not in by_agent:
                by_agent[result.agent_name] = []
            by_agent[result.agent_name].append(result)

        summaries = {}
        for agent, results in by_agent.items():
            scores = [r.score for r in results if r.score is not None]
            summaries[agent] = {
                "count": len(results),
                "scored": len(scores),
                "average_score": sum(scores) / len(scores) if scores else None,
                "total_time_ms": sum(r.response_time_ms for r in results),
                "total_cost": sum(r.cost_estimate or 0.0 for r in results),
            }
        return summaries
