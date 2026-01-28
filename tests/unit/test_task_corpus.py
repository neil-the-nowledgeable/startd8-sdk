"""
Unit tests for task corpus models and loader
"""

import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from startd8.evaluation import (
    Capability,
    EvaluationCriteria,
    EvaluationRun,
    Task,
    TaskCategory,
    TaskCorpus,
    TaskDifficulty,
    TaskFilter,
    TaskResult,
    TaskVariable,
    TaskLoader,
    load_default_corpus,
    BUILTIN_CORPUS_DIR,
)


class TestTaskVariable:
    """Test TaskVariable model validation"""

    def test_valid_variable(self):
        """Test creating a valid variable"""
        var = TaskVariable(
            name="PROJECT_NAME",
            description="The name of the project",
            default="myproject",
            required=True,
        )
        assert var.name == "PROJECT_NAME"
        assert var.default == "myproject"

    def test_variable_name_must_be_uppercase(self):
        """Test that variable names must be uppercase"""
        with pytest.raises(ValidationError):
            TaskVariable(name="lowercase", description="test")

    def test_variable_name_allows_underscores(self):
        """Test that variable names can contain underscores"""
        var = TaskVariable(name="PROJECT_FILE_PATH", description="test")
        assert var.name == "PROJECT_FILE_PATH"

    def test_is_optional_property(self):
        """Test is_optional property"""
        required_var = TaskVariable(name="REQUIRED", required=True)
        assert not required_var.is_optional

        optional_with_default = TaskVariable(
            name="WITH_DEFAULT", required=True, default="value"
        )
        assert optional_with_default.is_optional

        optional_not_required = TaskVariable(name="NOT_REQUIRED", required=False)
        assert optional_not_required.is_optional


class TestEvaluationCriteria:
    """Test EvaluationCriteria model validation"""

    def test_valid_criteria(self):
        """Test creating valid criteria"""
        criteria = EvaluationCriteria(
            name="correctness",
            description="Code produces correct output",
            weight=0.5,
            required=True,
        )
        assert criteria.name == "correctness"
        assert criteria.weight == 0.5

    def test_weight_bounds(self):
        """Test weight must be between 0 and 1"""
        with pytest.raises(ValidationError):
            EvaluationCriteria(name="test", description="test", weight=1.5)

        with pytest.raises(ValidationError):
            EvaluationCriteria(name="test", description="test", weight=-0.1)

    def test_name_is_lowercased(self):
        """Test that criteria names are lowercased"""
        criteria = EvaluationCriteria(name="CORRECTNESS", description="test")
        assert criteria.name == "correctness"


class TestTask:
    """Test Task model validation"""

    def test_valid_task(self):
        """Test creating a valid task"""
        task = Task(
            id="design-rest-api",
            name="REST API Design",
            category=TaskCategory.DESIGN,
            difficulty=TaskDifficulty.MEDIUM,
            prompt_template="Design an API for {{DOMAIN}}",
            variables=[TaskVariable(name="DOMAIN", description="Domain")],
            capabilities_tested=[Capability.API_DESIGN],
        )
        assert task.id == "design-rest-api"
        assert task.category == TaskCategory.DESIGN

    def test_task_id_format(self):
        """Test task ID format validation"""
        # Valid IDs
        Task(
            id="valid-id",
            name="Test",
            category=TaskCategory.CODING,
            difficulty=TaskDifficulty.EASY,
            prompt_template="Test",
        )

        # Invalid: uppercase
        with pytest.raises(ValidationError):
            Task(
                id="Invalid-ID",
                name="Test",
                category=TaskCategory.CODING,
                difficulty=TaskDifficulty.EASY,
                prompt_template="Test",
            )

        # Invalid: starts with number
        with pytest.raises(ValidationError):
            Task(
                id="123-task",
                name="Test",
                category=TaskCategory.CODING,
                difficulty=TaskDifficulty.EASY,
                prompt_template="Test",
            )

    def test_render_prompt_basic(self):
        """Test basic prompt rendering"""
        task = Task(
            id="test-task",
            name="Test",
            category=TaskCategory.CODING,
            difficulty=TaskDifficulty.EASY,
            prompt_template="Write code in {{LANGUAGE}} for {{PROJECT}}",
            variables=[
                TaskVariable(name="LANGUAGE", description="Language"),
                TaskVariable(name="PROJECT", description="Project"),
            ],
        )
        rendered = task.render_prompt({"LANGUAGE": "Python", "PROJECT": "my-app"})
        assert rendered == "Write code in Python for my-app"

    def test_render_prompt_with_defaults(self):
        """Test prompt rendering uses defaults"""
        task = Task(
            id="test-task",
            name="Test",
            category=TaskCategory.CODING,
            difficulty=TaskDifficulty.EASY,
            prompt_template="Write code in {{LANGUAGE}}",
            variables=[
                TaskVariable(name="LANGUAGE", description="Language", default="Python")
            ],
        )
        rendered = task.render_prompt({})
        assert rendered == "Write code in Python"

    def test_render_prompt_missing_required(self):
        """Test render_prompt raises for missing required variables"""
        task = Task(
            id="test-task",
            name="Test",
            category=TaskCategory.CODING,
            difficulty=TaskDifficulty.EASY,
            prompt_template="Write code in {{LANGUAGE}}",
            variables=[TaskVariable(name="LANGUAGE", description="Language", required=True)],
        )
        with pytest.raises(ValueError) as exc_info:
            task.render_prompt({})
        assert "LANGUAGE" in str(exc_info.value)

    def test_get_missing_variables(self):
        """Test get_missing_variables method"""
        task = Task(
            id="test-task",
            name="Test",
            category=TaskCategory.CODING,
            difficulty=TaskDifficulty.EASY,
            prompt_template="{{A}} {{B}} {{C}}",
            variables=[
                TaskVariable(name="A", description="A", required=True),
                TaskVariable(name="B", description="B", required=True, default="default"),
                TaskVariable(name="C", description="C", required=False),
            ],
        )
        missing = task.get_missing_variables({})
        assert missing == ["A"]  # Only A is required without default

        missing = task.get_missing_variables({"A": "value"})
        assert missing == []


class TestTaskFilter:
    """Test TaskFilter matching"""

    @pytest.fixture
    def sample_task(self):
        """Create a sample task for testing"""
        return Task(
            id="test-task",
            name="Test Task",
            category=TaskCategory.CODING,
            difficulty=TaskDifficulty.MEDIUM,
            prompt_template="Test",
            capabilities_tested=[Capability.CODE_GENERATION, Capability.REASONING],
            tags=["python", "algorithms"],
        )

    def test_empty_filter_matches_all(self, sample_task):
        """Test that empty filter matches all tasks"""
        filter = TaskFilter()
        assert filter.matches(sample_task)

    def test_category_filter(self, sample_task):
        """Test filtering by category"""
        filter_match = TaskFilter(categories=[TaskCategory.CODING])
        assert filter_match.matches(sample_task)

        filter_no_match = TaskFilter(categories=[TaskCategory.DESIGN])
        assert not filter_no_match.matches(sample_task)

    def test_difficulty_filter(self, sample_task):
        """Test filtering by difficulty"""
        filter_match = TaskFilter(difficulties=[TaskDifficulty.MEDIUM])
        assert filter_match.matches(sample_task)

        filter_no_match = TaskFilter(difficulties=[TaskDifficulty.HARD])
        assert not filter_no_match.matches(sample_task)

    def test_capabilities_filter(self, sample_task):
        """Test filtering by capabilities (any match)"""
        filter_match = TaskFilter(capabilities=[Capability.CODE_GENERATION])
        assert filter_match.matches(sample_task)

        filter_no_match = TaskFilter(capabilities=[Capability.ARCHITECTURE])
        assert not filter_no_match.matches(sample_task)

    def test_tags_filter(self, sample_task):
        """Test filtering by tags (any match)"""
        filter_match = TaskFilter(tags=["python"])
        assert filter_match.matches(sample_task)

        filter_no_match = TaskFilter(tags=["javascript"])
        assert not filter_no_match.matches(sample_task)

    def test_ids_filter(self, sample_task):
        """Test filtering by task IDs"""
        filter_match = TaskFilter(ids=["test-task"])
        assert filter_match.matches(sample_task)

        filter_no_match = TaskFilter(ids=["other-task"])
        assert not filter_no_match.matches(sample_task)

    def test_combined_filters(self, sample_task):
        """Test multiple filters combined (AND logic)"""
        filter_all_match = TaskFilter(
            categories=[TaskCategory.CODING],
            difficulties=[TaskDifficulty.MEDIUM],
            tags=["python"],
        )
        assert filter_all_match.matches(sample_task)

        filter_partial_mismatch = TaskFilter(
            categories=[TaskCategory.CODING],
            difficulties=[TaskDifficulty.HARD],  # Doesn't match
        )
        assert not filter_partial_mismatch.matches(sample_task)


class TestTaskCorpus:
    """Test TaskCorpus operations"""

    @pytest.fixture
    def sample_tasks(self):
        """Create sample tasks for testing"""
        return [
            Task(
                id="coding-task-1",
                name="Coding Task 1",
                category=TaskCategory.CODING,
                difficulty=TaskDifficulty.EASY,
                prompt_template="Test 1",
                capabilities_tested=[Capability.CODE_GENERATION],
                tags=["python"],
            ),
            Task(
                id="design-task-1",
                name="Design Task 1",
                category=TaskCategory.DESIGN,
                difficulty=TaskDifficulty.MEDIUM,
                prompt_template="Test 2",
                capabilities_tested=[Capability.ARCHITECTURE],
                tags=["api"],
            ),
            Task(
                id="coding-task-2",
                name="Coding Task 2",
                category=TaskCategory.CODING,
                difficulty=TaskDifficulty.HARD,
                prompt_template="Test 3",
                capabilities_tested=[Capability.ALGORITHM_DESIGN],
                tags=["algorithms"],
            ),
        ]

    def test_add_and_get_task(self, sample_tasks):
        """Test adding and retrieving tasks"""
        corpus = TaskCorpus(name="test")
        corpus.add_task(sample_tasks[0])

        retrieved = corpus.get_task("coding-task-1")
        assert retrieved is not None
        assert retrieved.name == "Coding Task 1"

        assert corpus.get_task("nonexistent") is None

    def test_list_tasks(self, sample_tasks):
        """Test listing tasks with filter"""
        corpus = TaskCorpus(name="test")
        for task in sample_tasks:
            corpus.add_task(task)

        # List all
        all_tasks = corpus.list_tasks()
        assert len(all_tasks) == 3

        # Filter by category
        coding_tasks = corpus.list_tasks(TaskFilter(categories=[TaskCategory.CODING]))
        assert len(coding_tasks) == 2

    def test_get_by_category(self, sample_tasks):
        """Test getting tasks by category"""
        corpus = TaskCorpus(name="test")
        for task in sample_tasks:
            corpus.add_task(task)

        coding_tasks = corpus.get_by_category(TaskCategory.CODING)
        assert len(coding_tasks) == 2

        design_tasks = corpus.get_by_category(TaskCategory.DESIGN)
        assert len(design_tasks) == 1

    def test_summary(self, sample_tasks):
        """Test corpus summary statistics"""
        corpus = TaskCorpus(name="test", description="Test corpus")
        for task in sample_tasks:
            corpus.add_task(task)

        summary = corpus.summary()
        assert summary["name"] == "test"
        assert summary["total_tasks"] == 3
        assert summary["by_category"]["coding"] == 2
        assert summary["by_category"]["design"] == 1
        assert "python" in summary["tags"]

    def test_merge(self, sample_tasks):
        """Test merging corpora"""
        corpus1 = TaskCorpus(name="corpus1")
        corpus1.add_task(sample_tasks[0])

        corpus2 = TaskCorpus(name="corpus2")
        corpus2.add_task(sample_tasks[1])
        corpus2.add_task(sample_tasks[2])

        corpus1.merge(corpus2)
        assert len(corpus1.tasks) == 3

    def test_merge_with_overwrite(self, sample_tasks):
        """Test merging with overwrite"""
        task1 = sample_tasks[0]
        task1_modified = Task(
            id=task1.id,
            name="Modified Name",
            category=task1.category,
            difficulty=task1.difficulty,
            prompt_template="Modified",
        )

        corpus1 = TaskCorpus(name="corpus1")
        corpus1.add_task(task1)

        corpus2 = TaskCorpus(name="corpus2")
        corpus2.add_task(task1_modified)

        # Without overwrite
        corpus1.merge(corpus2, overwrite=False)
        assert corpus1.get_task(task1.id).name == "Coding Task 1"

        # With overwrite
        corpus1.merge(corpus2, overwrite=True)
        assert corpus1.get_task(task1.id).name == "Modified Name"


class TestTaskResult:
    """Test TaskResult model"""

    def test_valid_result(self):
        """Test creating a valid task result"""
        result = TaskResult(
            task_id="test-task",
            agent_name="anthropic:claude-sonnet-4-20250514",
            model="claude-sonnet-4-20250514",
            prompt="Test prompt",
            response="Test response",
            response_time_ms=1500,
            score=0.85,
            criteria_scores={"correctness": 0.9, "clarity": 0.8},
        )
        assert result.task_id == "test-task"
        assert result.score == 0.85

    def test_score_bounds(self):
        """Test score must be between 0 and 1"""
        with pytest.raises(ValidationError):
            TaskResult(
                task_id="test",
                agent_name="test",
                model="test",
                prompt="test",
                response="test",
                response_time_ms=100,
                score=1.5,
            )


class TestEvaluationRun:
    """Test EvaluationRun model"""

    def test_run_with_results(self):
        """Test evaluation run with results"""
        run = EvaluationRun(corpus_name="test-corpus")

        result1 = TaskResult(
            task_id="task-1",
            agent_name="agent",
            model="model",
            prompt="p",
            response="r",
            response_time_ms=1000,
            score=0.8,
            cost_estimate=0.01,
        )
        result2 = TaskResult(
            task_id="task-2",
            agent_name="agent",
            model="model",
            prompt="p",
            response="r",
            response_time_ms=2000,
            score=0.9,
            cost_estimate=0.02,
        )

        run.add_result(result1)
        run.add_result(result2)

        assert run.total_tasks == 2
        assert run.tasks_scored == 2
        assert abs(run.average_score - 0.85) < 0.0001  # Float comparison
        assert run.total_time_ms == 3000
        assert abs(run.total_cost - 0.03) < 0.0001  # Float comparison

    def test_run_completion(self):
        """Test marking run as complete"""
        run = EvaluationRun(corpus_name="test")
        assert run.completed_at is None

        run.complete()
        assert run.completed_at is not None


class TestTaskLoader:
    """Test TaskLoader"""

    def test_load_from_yaml_file(self):
        """Test loading tasks from a YAML file"""
        yaml_content = """
tasks:
  - id: test-task
    name: Test Task
    category: coding
    difficulty: easy
    prompt_template: "Write code for {{PROJECT}}"
    variables:
      - name: PROJECT
        description: Project name
        required: true
    capabilities_tested:
      - code_generation
    evaluation_criteria:
      - name: correctness
        description: Code works correctly
        weight: 0.5
    tags:
      - test
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            temp_path = Path(f.name)

        try:
            loader = TaskLoader()
            tasks = loader.load_from_file(temp_path)

            assert len(tasks) == 1
            task = tasks[0]
            assert task.id == "test-task"
            assert task.category == TaskCategory.CODING
            assert len(task.variables) == 1
            assert task.variables[0].name == "PROJECT"
            assert Capability.CODE_GENERATION in [
                c if isinstance(c, Capability) else Capability(c)
                for c in task.capabilities_tested
            ]
        finally:
            temp_path.unlink()

    def test_load_corpus_caching(self):
        """Test that corpus loading is cached"""
        loader = TaskLoader()
        corpus1 = loader.load_corpus()
        corpus2 = loader.load_corpus()
        assert corpus1 is corpus2

        corpus3 = loader.load_corpus(refresh=True)
        assert corpus3 is not corpus1

    def test_builtin_corpus_dir_exists(self):
        """Test that builtin corpus directory exists"""
        assert BUILTIN_CORPUS_DIR.exists(), f"Builtin corpus dir not found: {BUILTIN_CORPUS_DIR}"


class TestLoadDefaultCorpus:
    """Test the convenience function"""

    def test_load_default_corpus(self):
        """Test loading the default corpus"""
        corpus = load_default_corpus()

        assert corpus is not None
        assert isinstance(corpus, TaskCorpus)
        assert corpus.name == "default"

        # Should have tasks from all categories
        summary = corpus.summary()
        assert summary["total_tasks"] > 0

    def test_default_corpus_has_all_categories(self):
        """Test that default corpus has tasks from all categories"""
        corpus = load_default_corpus()

        categories_present = set()
        for task in corpus.tasks.values():
            cat = task.category if isinstance(task.category, str) else task.category.value
            categories_present.add(cat)

        expected = {"design", "coding", "testing", "review", "documentation"}
        assert categories_present == expected, f"Missing categories: {expected - categories_present}"

    def test_default_corpus_task_count(self):
        """Test that default corpus has expected number of tasks"""
        corpus = load_default_corpus()

        # Should have 25 tasks (5 per category)
        assert len(corpus.tasks) == 25


class TestTaskValidation:
    """Test task prompt rendering and variable validation"""

    def test_complex_prompt_rendering(self):
        """Test rendering a complex prompt with multiple variables"""
        task = Task(
            id="complex-task",
            name="Complex Task",
            category=TaskCategory.CODING,
            difficulty=TaskDifficulty.MEDIUM,
            prompt_template="""
Implement a {{FEATURE}} in {{LANGUAGE}}.

Requirements:
- Use {{FRAMEWORK}} framework
- Target {{AUDIENCE}} developers

Output format: {{FORMAT}}
""",
            variables=[
                TaskVariable(name="FEATURE", description="Feature", required=True),
                TaskVariable(name="LANGUAGE", description="Language", default="Python"),
                TaskVariable(name="FRAMEWORK", description="Framework", default="FastAPI"),
                TaskVariable(name="AUDIENCE", description="Audience", required=False, default="junior"),
                TaskVariable(name="FORMAT", description="Format", required=True),
            ],
        )

        rendered = task.render_prompt({
            "FEATURE": "rate limiter",
            "FORMAT": "code with comments",
        })

        assert "rate limiter" in rendered
        assert "Python" in rendered  # Default
        assert "FastAPI" in rendered  # Default
        assert "junior" in rendered  # Optional default
        assert "code with comments" in rendered
