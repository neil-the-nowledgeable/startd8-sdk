"""Tests for REQ-PLI-601: Cross-language dependency ordering.

Validates that ``_file_type_priority()`` and ``_inject_build_order_dependencies()``
correctly add implicit build-order edges within same-service task groups.
"""

from startd8.seeds.derivation import (
    _extract_service_dir,
    _file_type_priority,
    _inject_build_order_dependencies,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: str, target_files: list, depends_on: list | None = None):
    """Create a minimal task dict matching derivation schema."""
    return {
        "task_id": task_id,
        "title": f"Task {task_id}",
        "task_type": "task",
        "story_points": 2,
        "priority": "medium",
        "labels": [],
        "depends_on": list(depends_on or []),
        "config": {
            "task_description": f"Implement {task_id}",
            "requirements_text": "",
            "context": {
                "feature_id": f"F-{task_id}",
                "target_files": list(target_files),
                "estimated_loc": 50,
            },
        },
    }


def _get_deps(tasks, task_id):
    """Return the depends_on list for a task by ID."""
    for t in tasks:
        if t["task_id"] == task_id:
            return t["depends_on"]
    raise KeyError(task_id)


# ---------------------------------------------------------------------------
# _file_type_priority unit tests
# ---------------------------------------------------------------------------

class TestFileTypePriority:
    """Unit tests for _file_type_priority covering each priority tier."""

    def test_proto_files(self):
        assert _file_type_priority("src/protos/demo.proto") == 0
        assert _file_type_priority("api/v1/service.proto") == 0

    def test_config_files(self):
        assert _file_type_priority("src/svc/application.yml") == 1
        assert _file_type_priority("src/svc/application.yaml") == 1
        assert _file_type_priority("src/svc/application.properties") == 1
        assert _file_type_priority("Services/appsettings.json") == 1
        assert _file_type_priority("Services/appsettings.Development.json") == 1

    def test_source_files(self):
        assert _file_type_priority("src/svc/main.go") == 2
        assert _file_type_priority("src/svc/Server.java") == 2
        assert _file_type_priority("src/svc/Service.cs") == 2
        assert _file_type_priority("src/svc/app.py") == 2
        assert _file_type_priority("src/svc/index.js") == 2
        assert _file_type_priority("src/svc/index.ts") == 2
        assert _file_type_priority("src/svc/App.tsx") == 2

    def test_test_files(self):
        assert _file_type_priority("src/svc/main_test.go") == 3
        assert _file_type_priority("src/svc/test_server.py") == 3

    def test_build_files(self):
        assert _file_type_priority("src/svc/go.mod") == 4
        assert _file_type_priority("src/svc/go.sum") == 4
        assert _file_type_priority("src/svc/build.gradle") == 4
        assert _file_type_priority("src/svc/pom.xml") == 4
        assert _file_type_priority("src/svc/package.json") == 4
        assert _file_type_priority("src/svc/requirements.txt") == 4
        assert _file_type_priority("src/svc/pyproject.toml") == 4
        assert _file_type_priority("src/svc/MyApp.csproj") == 4
        assert _file_type_priority("src/svc/MyApp.sln") == 4

    def test_deployment_files(self):
        assert _file_type_priority("src/svc/Dockerfile") == 6
        assert _file_type_priority("src/svc/dockerfile") == 6
        assert _file_type_priority("src/svc/deploy-service.yaml") == 6

    def test_wrapper_files(self):
        assert _file_type_priority("src/svc/gradle-wrapper.properties") == 5

    def test_data_files(self):
        assert _file_type_priority("src/svc/data.json") == 7
        assert _file_type_priority("src/svc/config.xml") == 7
        assert _file_type_priority("src/svc/data.csv") == 7

    def test_default_priority(self):
        assert _file_type_priority("src/svc/README.md") == 5
        assert _file_type_priority("src/svc/Makefile") == 5


# ---------------------------------------------------------------------------
# _extract_service_dir tests
# ---------------------------------------------------------------------------

class TestExtractServiceDir:

    def test_src_prefix(self):
        assert _extract_service_dir("src/cartservice/main.go") == "cartservice"

    def test_no_src_prefix(self):
        assert _extract_service_dir("cartservice/main.go") == "cartservice"

    def test_top_level_file(self):
        assert _extract_service_dir("main.go") == ""

    def test_deep_path(self):
        assert _extract_service_dir("src/emailservice/internal/handler.go") == "emailservice"


# ---------------------------------------------------------------------------
# _inject_build_order_dependencies integration tests
# ---------------------------------------------------------------------------

class TestInjectBuildOrderDependencies:

    def test_proto_before_go_source(self):
        """Proto task should be a dependency of Go source task."""
        tasks = [
            _make_task("T1", ["src/svc/demo.proto"]),
            _make_task("T2", ["src/svc/main.go"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        assert "T1" in _get_deps(result, "T2")

    def test_source_before_build_file(self):
        """.java task should be a dependency of build.gradle task."""
        tasks = [
            _make_task("T1", ["src/svc/Server.java"]),
            _make_task("T2", ["src/svc/build.gradle"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        assert "T1" in _get_deps(result, "T2")

    def test_build_file_before_dockerfile(self):
        """go.mod task should be a dependency of Dockerfile task."""
        tasks = [
            _make_task("T1", ["src/svc/go.mod"]),
            _make_task("T2", ["src/svc/Dockerfile"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        assert "T1" in _get_deps(result, "T2")

    def test_config_before_source(self):
        """application.yml task should be a dependency of .java task."""
        tasks = [
            _make_task("T1", ["src/svc/application.yml"]),
            _make_task("T2", ["src/svc/Application.java"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        assert "T1" in _get_deps(result, "T2")

    def test_cross_service_independence(self):
        """Tasks in different service dirs should get no implicit deps."""
        tasks = [
            _make_task("T1", ["src/cart/demo.proto"]),
            _make_task("T2", ["src/email/main.go"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        assert _get_deps(result, "T1") == []
        assert _get_deps(result, "T2") == []

    def test_explicit_deps_preserved(self):
        """Existing depends_on should not be overwritten."""
        tasks = [
            _make_task("T1", ["src/svc/main.go"]),
            _make_task("T2", ["src/svc/go.mod"], depends_on=["T1"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        deps_t2 = _get_deps(result, "T2")
        # T1 should still be in depends_on (was explicit)
        assert "T1" in deps_t2

    def test_no_cycles_introduced(self):
        """After injection, no cycles should exist."""
        tasks = [
            _make_task("T1", ["src/svc/demo.proto"]),
            _make_task("T2", ["src/svc/main.go"], depends_on=["T1"]),
            _make_task("T3", ["src/svc/go.mod"]),
            _make_task("T4", ["src/svc/Dockerfile"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        # Verify acyclicity via topological sort attempt
        adj = {t["task_id"]: set(t["depends_on"]) for t in result}
        visited = set()
        temp = set()

        def _visit(n):
            if n in temp:
                raise AssertionError(f"Cycle detected at {n}")
            if n in visited:
                return
            temp.add(n)
            for dep in adj.get(n, set()):
                _visit(dep)
            temp.remove(n)
            visited.add(n)

        for node in adj:
            _visit(node)

    def test_test_file_after_source(self):
        """Test file task should depend on source file task."""
        tasks = [
            _make_task("T1", ["src/svc/server.go"]),
            _make_task("T2", ["src/svc/server_test.go"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        assert "T1" in _get_deps(result, "T2")

    def test_mixed_language_project(self):
        """Go + Java + Dockerfile should be ordered correctly within same service."""
        tasks = [
            _make_task("T1", ["src/svc/demo.proto"]),
            _make_task("T2", ["src/svc/main.go"]),
            _make_task("T3", ["src/svc/Server.java"]),
            _make_task("T4", ["src/svc/Dockerfile"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        # Proto (0) before source (2) before Dockerfile (6)
        assert "T1" in _get_deps(result, "T2")
        assert "T1" in _get_deps(result, "T3")
        assert "T1" in _get_deps(result, "T4")
        # Source before Dockerfile
        assert "T2" in _get_deps(result, "T4") or "T3" in _get_deps(result, "T4")

    def test_single_task_service(self):
        """No deps added for a lone task in a service."""
        tasks = [
            _make_task("T1", ["src/svc/main.go"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        assert _get_deps(result, "T1") == []

    def test_same_priority_no_edge(self):
        """Two source files at the same priority tier should not get implicit ordering."""
        tasks = [
            _make_task("T1", ["src/svc/server.go"]),
            _make_task("T2", ["src/svc/handler.go"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        assert _get_deps(result, "T1") == []
        assert _get_deps(result, "T2") == []

    def test_does_not_duplicate_existing_edge(self):
        """If an explicit dep already captures the ordering, don't add it again."""
        tasks = [
            _make_task("T1", ["src/svc/demo.proto"]),
            _make_task("T2", ["src/svc/main.go"], depends_on=["T1"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        deps = _get_deps(result, "T2")
        assert deps.count("T1") == 1

    def test_does_not_contradict_reverse_explicit_dep(self):
        """If an explicit dep goes from lower to higher priority, don't contradict."""
        # Unusual but possible: go.mod explicitly depends on Dockerfile
        tasks = [
            _make_task("T1", ["src/svc/Dockerfile"]),
            _make_task("T2", ["src/svc/go.mod"], depends_on=["T1"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        # T1 (Dockerfile, prio 6) should NOT get a dep on T2 (go.mod, prio 4)
        # because T2 already depends on T1
        assert "T2" not in _get_deps(result, "T1")

    def test_empty_tasks(self):
        """Empty task list should return empty."""
        assert _inject_build_order_dependencies([]) == []

    def test_tasks_without_target_files_skipped(self):
        """Tasks with no target_files should be left alone."""
        tasks = [
            {
                "task_id": "T1",
                "depends_on": [],
                "config": {"context": {"target_files": []}},
            },
            _make_task("T2", ["src/svc/main.go"]),
        ]
        result = _inject_build_order_dependencies(tasks)
        assert _get_deps(result, "T1") == []
