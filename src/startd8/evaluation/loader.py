"""
Task Loader - Load evaluation tasks from built-in and user directories
"""

from pathlib import Path
from ..paths import default_config_dir
from typing import Dict, List, Optional
import logging

import yaml

from .tasks import (
    Capability,
    EvaluationCriteria,
    Task,
    TaskCategory,
    TaskCorpus,
    TaskDifficulty,
    TaskVariable,
)

logger = logging.getLogger(__name__)

# Directory constants
BUILTIN_CORPUS_DIR = Path(__file__).parent / "corpus"
USER_CORPUS_DIR = default_config_dir() / "evaluation"


class TaskLoader:
    """Load and manage evaluation tasks from various sources"""

    def __init__(
        self,
        builtin_dir: Optional[Path] = None,
        user_dir: Optional[Path] = None,
        project_dir: Optional[Path] = None,
    ):
        """
        Initialize task loader.

        Args:
            builtin_dir: Directory for built-in tasks (defaults to package corpus/)
            user_dir: Directory for user tasks (defaults to ~/.startd8/evaluation/)
            project_dir: Optional project-specific tasks directory (.startd8/evaluation/)
        """
        self.builtin_dir = builtin_dir or BUILTIN_CORPUS_DIR
        self.user_dir = user_dir or USER_CORPUS_DIR
        self.project_dir = project_dir
        self._cache: Optional[TaskCorpus] = None

    def load_builtin_tasks(self) -> Dict[str, Task]:
        """
        Load all built-in tasks from package corpus directory.

        Returns:
            Dictionary mapping task ID to Task
        """
        tasks: Dict[str, Task] = {}

        if not self.builtin_dir.exists():
            logger.warning(f"Built-in corpus directory not found: {self.builtin_dir}")
            return tasks

        for file_path in self.builtin_dir.glob("*.yaml"):
            try:
                loaded = self._load_tasks_from_file(file_path)
                for task in loaded:
                    tasks[task.id] = task
                    logger.debug(f"Loaded built-in task: {task.id}")
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        return tasks

    def load_user_tasks(self) -> Dict[str, Task]:
        """
        Load all user-defined tasks from ~/.startd8/evaluation/.

        Returns:
            Dictionary mapping task ID to Task
        """
        tasks: Dict[str, Task] = {}

        if not self.user_dir.exists():
            return tasks

        for file_path in self.user_dir.glob("*.yaml"):
            try:
                loaded = self._load_tasks_from_file(file_path)
                for task in loaded:
                    tasks[task.id] = task
                    logger.debug(f"Loaded user task: {task.id}")
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        return tasks

    def load_project_tasks(self) -> Dict[str, Task]:
        """
        Load tasks from project directory (.startd8/evaluation/).

        Returns:
            Dictionary mapping task ID to Task
        """
        tasks: Dict[str, Task] = {}

        if not self.project_dir:
            return tasks

        eval_dir = self.project_dir / ".startd8" / "evaluation"
        if not eval_dir.exists():
            return tasks

        for file_path in eval_dir.glob("*.yaml"):
            try:
                loaded = self._load_tasks_from_file(file_path)
                for task in loaded:
                    tasks[task.id] = task
                    logger.debug(f"Loaded project task: {task.id}")
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        return tasks

    def load_corpus(self, refresh: bool = False) -> TaskCorpus:
        """
        Load the combined task corpus with priority override.

        Priority order: project > user > builtin (later overrides earlier)

        Args:
            refresh: If True, reload from files even if cached

        Returns:
            TaskCorpus with all loaded tasks
        """
        if self._cache is not None and not refresh:
            return self._cache

        # Load in priority order (builtin first, then overrides)
        all_tasks: Dict[str, Task] = {}

        builtin = self.load_builtin_tasks()
        all_tasks.update(builtin)

        user = self.load_user_tasks()
        all_tasks.update(user)

        project = self.load_project_tasks()
        all_tasks.update(project)

        self._cache = TaskCorpus(
            name="default",
            description="Combined task corpus from builtin, user, and project sources",
            tasks=all_tasks,
        )

        return self._cache

    def load_from_file(self, path: Path) -> List[Task]:
        """
        Load tasks from a single YAML file.

        Args:
            path: Path to the YAML file

        Returns:
            List of loaded tasks

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file format is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"Task file not found: {path}")

        return self._load_tasks_from_file(path)

    def _load_tasks_from_file(self, file_path: Path) -> List[Task]:
        """
        Load tasks from a YAML file.

        Expected format:
        ```yaml
        tasks:
          - id: task-id
            name: Task Name
            category: design
            ...
        ```

        Args:
            file_path: Path to the YAML file

        Returns:
            List of Task objects
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty or invalid task file: {file_path}")

        tasks_data = data.get("tasks", [])
        if not tasks_data:
            raise ValueError(f"No 'tasks' key found in file: {file_path}")

        tasks = []
        for task_data in tasks_data:
            task = self._parse_task(task_data)
            tasks.append(task)

        return tasks

    def _parse_task(self, data: Dict) -> Task:
        """
        Parse a task from dictionary data.

        Args:
            data: Task data dictionary

        Returns:
            Task object
        """
        # Parse variables
        variables = []
        for var_data in data.get("variables", []):
            variables.append(TaskVariable(**var_data))

        # Parse evaluation criteria
        criteria = []
        for crit_data in data.get("evaluation_criteria", []):
            criteria.append(EvaluationCriteria(**crit_data))

        # Parse capabilities (convert strings to enum values)
        capabilities = []
        for cap in data.get("capabilities_tested", []):
            if isinstance(cap, str):
                try:
                    capabilities.append(Capability(cap))
                except ValueError:
                    logger.warning(f"Unknown capability: {cap}")
            else:
                capabilities.append(cap)

        # Parse category
        category = data.get("category", "coding")
        if isinstance(category, str):
            category = TaskCategory(category)

        # Parse difficulty
        difficulty = data.get("difficulty", "medium")
        if isinstance(difficulty, str):
            difficulty = TaskDifficulty(difficulty)

        return Task(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            category=category,
            difficulty=difficulty,
            prompt_template=data["prompt_template"],
            variables=variables,
            capabilities_tested=capabilities,
            evaluation_criteria=criteria,
            reference_solution=data.get("reference_solution"),
            tags=data.get("tags", []),
            version=data.get("version", "1.0.0"),
        )

    def clear_cache(self) -> None:
        """Clear the cached corpus."""
        self._cache = None


def load_default_corpus() -> TaskCorpus:
    """
    Convenience function to load the default task corpus.

    Returns:
        TaskCorpus with all available tasks
    """
    loader = TaskLoader()
    return loader.load_corpus()
