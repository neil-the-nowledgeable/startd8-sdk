import importlib
import importlib.util
import json
from pathlib import Path
from typing import Optional, Dict
import types
import sys

import pytest


if importlib.util.find_spec("startd8") is None:
    pytest.skip(
        "Startd8 SDK not installed; skipping tasks runner integration tests.",
        allow_module_level=True,
    )


def _write_task_list(path: Path, with_dependency: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dep_block = ""
    if with_dependency:
        dep_block = """
### TASK-002: Second Task 🟡
**Status:** 🔓 Open
**Dependencies:** TASK-001

Body for task 2.
"""
    content = f"""# Minimal Task List

### TASK-001: First Task 🟡
**Status:** 🔓 Open
**Dependencies:** 

Body for task 1.
{dep_block}
"""
    path.write_text(content, encoding="utf-8")
    return path


class _FakeAgent:
    def __init__(self, name: str = "mock", model: str = "mock-model") -> None:
        self.name = name
        self.model = model

    def generate(self, prompt: str):
        # Choose file path based on which task is in the prompt for determinism
        file_name = "task2.txt" if "TASK-002" in prompt else "task1.txt"
        return (
            f'<write_file path="{file_name}">content for {file_name}</write_file>',
            0,
            {},
        )


class _FakeProvider:
    name = "mock"
    display_name = "Mock Provider"
    supported_models = ["mock-model"]

    def create_agent(self, model: str, name: Optional[str] = None, **kwargs):
        return _FakeAgent(name=name or self.name, model=model)


def _reload_mcp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    env_overrides: Optional[Dict[str, str]] = None,
):
    env = {
        "PROJECT_ROOT": str(tmp_path),
        "TASK_LIST_PATH": str(tmp_path / "MASTER_TASK_LIST.md"),
        "TASK_LOG_ENABLED": "false",
        "ALLOWED_AGENTS": "mock",
        "DEFAULT_AGENT": "mock",
        "AUTO_MAX_DEPTH": "5",
        "AUTO_MAX_TASKS": "10",
        "STARTD8_SDK_PATH": "/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/src",
    }
    if env_overrides:
        env.update(env_overrides)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Provide a lightweight stub for mcp.FastMCP to avoid dependency during tests.
    if "mcp.server.fastmcp" not in sys.modules:
        class _StubFastMCP:
            def __init__(self, *args, **kwargs):
                pass

            def tool(self, *args, **kwargs):
                def decorator(fn):
                    return fn
                return decorator

            def resource(self, *args, **kwargs):
                def decorator(fn):
                    return fn
                return decorator

            def run(self):
                return None

        mcp_mod = types.ModuleType("mcp")
        server_mod = types.ModuleType("mcp.server")
        fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
        fastmcp_mod.FastMCP = _StubFastMCP
        server_mod.fastmcp = fastmcp_mod
        mcp_mod.server = server_mod
        sys.modules["mcp"] = mcp_mod
        sys.modules["mcp.server"] = server_mod
        sys.modules["mcp.server.fastmcp"] = fastmcp_mod

    import startd8_mcp

    importlib.reload(startd8_mcp)
    return startd8_mcp


def _patch_provider_registry(monkeypatch: pytest.MonkeyPatch, mcp_module):
    modules = mcp_module._get_task_modules()
    provider_registry = modules["ProviderRegistry"]
    monkeypatch.setattr(provider_registry, "discover", lambda *a, **k: None)
    monkeypatch.setattr(provider_registry, "get_provider", lambda name: _FakeProvider() if name == "mock" else None)
    # Relax path validation for tests to keep paths under tmp project root
    from startd8.execution import actions as exec_actions
    monkeypatch.setattr(
        exec_actions,
        "validate_task_file_path",
        lambda path, project_root, **kwargs: (Path(project_root) / path).resolve(),
    )
    return modules


@pytest.mark.asyncio
async def test_tasks_run_dry_run_includes_diffs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=False)
    mcp_module = _reload_mcp(monkeypatch, tmp_path)
    modules = _patch_provider_registry(monkeypatch, mcp_module)

    params = mcp_module.TaskRunInput(
        id="TASK-001",
        file=str(task_file),
        auto=False,
        dry_run=True,
        agent="mock",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] is None
    assert result["schema_version"] == 1
    assert result["dry_run"] is True
    assert result["execution_order"] == ["TASK-001"]
    assert result["results"][0]["diffs"], "Expected diff payload in dry run"
    # Ensure file paths stay under project root
    for diff in result["results"][0]["diffs"]:
        assert Path(diff["path"]).resolve().is_relative_to(Path(tmp_path).resolve())


@pytest.mark.asyncio
async def test_tasks_run_auto_deps_depth_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=True)
    mcp_module = _reload_mcp(
        monkeypatch,
        tmp_path,
        env_overrides={"AUTO_MAX_DEPTH": "0"},
    )
    modules = _patch_provider_registry(monkeypatch, mcp_module)

    params = mcp_module.TaskRunInput(
        id="TASK-002",
        file=str(task_file),
        auto=True,
        dry_run=True,
        agent="mock",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] == "failed_precondition"
    assert "depth" in result["message"]
    assert "order" in result.get("data", {})


@pytest.mark.asyncio
async def test_tasks_run_apply_writes_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=True)
    mcp_module = _reload_mcp(monkeypatch, tmp_path)
    modules = _patch_provider_registry(monkeypatch, mcp_module)

    params = mcp_module.TaskRunInput(
        id="TASK-002",
        file=str(task_file),
        auto=True,
        dry_run=False,
        agent="mock",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] is None
    assert result["dry_run"] is False
    # Both tasks should have been applied in order
    assert result["execution_order"] == ["TASK-001", "TASK-002"]
    for expected in ["task1.txt", "task2.txt"]:
        assert (Path(tmp_path) / expected).exists(), f"Expected {expected} to be written"


@pytest.mark.asyncio
async def test_tasks_run_blocked_task(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=False)
    # Mark task blocked
    blocked_text = task_file.read_text(encoding="utf-8").replace("**Status:** 🔓 Open", "**Status:** 🚫 Blocked")
    task_file.write_text(blocked_text, encoding="utf-8")
    mcp_module = _reload_mcp(monkeypatch, tmp_path)
    _patch_provider_registry(monkeypatch, mcp_module)

    params = mcp_module.TaskRunInput(
        id="TASK-001",
        file=str(task_file),
        auto=False,
        dry_run=True,
        agent="mock",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] == "failed_precondition"
    assert result["data"]["task"] == "TASK-001"


@pytest.mark.asyncio
async def test_tasks_run_agent_not_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=False)
    mcp_module = _reload_mcp(monkeypatch, tmp_path, env_overrides={"ALLOWED_AGENTS": "mock"})
    _patch_provider_registry(monkeypatch, mcp_module)

    params = mcp_module.TaskRunInput(
        id="TASK-001",
        file=str(task_file),
        auto=False,
        dry_run=True,
        agent="other",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] == "invalid_params"
    assert "allowed_agents" in result.get("data", {})


@pytest.mark.asyncio
async def test_tasks_run_invalid_action_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=False)
    mcp_module = _reload_mcp(monkeypatch, tmp_path)

    # Patch provider to emit a disallowed extension
    class _BadAgent(_FakeAgent):
        def generate(self, prompt: str):
            return ('<write_file path="escape/evil.exe">nope</write_file>', 0, {})

    class _BadProvider(_FakeProvider):
        def create_agent(self, model: str, name: Optional[str] = None, **kwargs):
            return _BadAgent(name=name or self.name, model=model)

    modules = _patch_provider_registry(monkeypatch, mcp_module)
    provider_registry = modules["ProviderRegistry"]
    monkeypatch.setattr(provider_registry, "get_provider", lambda name: _BadProvider())

    params = mcp_module.TaskRunInput(
        id="TASK-001",
        file=str(task_file),
        auto=False,
        dry_run=True,
        agent="mock",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] == "invalid_params"
    assert "Invalid action path" in result["message"]


@pytest.mark.asyncio
async def test_tasks_run_unknown_dependency(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=False)
    content = task_file.read_text(encoding="utf-8")
    content += """
### TASK-999: Third Task 🟡
**Status:** 🔓 Open
**Dependencies:** TASK-404

Body for task 3.
"""
    task_file.write_text(content, encoding="utf-8")
    mcp_module = _reload_mcp(monkeypatch, tmp_path)
    _patch_provider_registry(monkeypatch, mcp_module)

    params = mcp_module.TaskRunInput(
        id="TASK-999",
        file=str(task_file),
        auto=False,
        dry_run=True,
        agent="mock",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] == "invalid_params"
    assert "Unknown dependency" in result["message"]


@pytest.mark.asyncio
async def test_tasks_run_cycle_detection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = tmp_path / "MASTER_TASK_LIST.md"
    task_file.write_text(
        """# Cyclic Tasks

### TASK-001: One 🟡
**Status:** 🔓 Open
**Dependencies:** TASK-002

Body.

### TASK-002: Two 🟡
**Status:** 🔓 Open
**Dependencies:** TASK-001

Body.
""",
        encoding="utf-8",
    )
    mcp_module = _reload_mcp(monkeypatch, tmp_path)
    _patch_provider_registry(monkeypatch, mcp_module)

    params = mcp_module.TaskRunInput(
        id="TASK-001",
        file=str(task_file),
        auto=True,
        dry_run=True,
        agent="mock",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] == "invalid_params"
    assert "cycle" in result.get("data", {})


@pytest.mark.asyncio
async def test_tasks_run_parser_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=False)
    mcp_module = _reload_mcp(monkeypatch, tmp_path)
    _patch_provider_registry(monkeypatch, mcp_module)

    class _BadParser:
        def __init__(self, *a, **k):
            pass

        def parse(self, *a, **k):
            raise ValueError("bad xml")

    monkeypatch.setattr(mcp_module, "ActionParser", _BadParser)

    params = mcp_module.TaskRunInput(
        id="TASK-001",
        file=str(task_file),
        auto=False,
        dry_run=True,
        agent="mock",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] == "invalid_params"
    assert "Parser error" in result["message"]


@pytest.mark.asyncio
async def test_tasks_run_apply_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=False)
    mcp_module = _reload_mcp(monkeypatch, tmp_path)
    _patch_provider_registry(monkeypatch, mcp_module)

    class _BadApplyResult:
        success = False
        message = "boom"
        modified_files = ["bad.txt"]

    class _OkResult:
        success = True
        message = ""
        modified_files = ["ok.txt"]

    class _BadApplicator:
        def __init__(self, *a, **k):
            pass

        def apply_actions(self, *a, dry_run: bool = False):
            return _OkResult() if dry_run else _BadApplyResult()

    monkeypatch.setattr(mcp_module, "ActionApplicator", _BadApplicator)

    params = mcp_module.TaskRunInput(
        id="TASK-001",
        file=str(task_file),
        auto=False,
        dry_run=False,
        agent="mock",
    )
    raw = await mcp_module.tasks_run(params)
    result = json.loads(raw)

    assert result["error"] == "internal"
    assert "files" in result.get("data", {})


@pytest.mark.asyncio
async def test_tasks_status_includes_runnable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    task_file = _write_task_list(tmp_path / "MASTER_TASK_LIST.md", with_dependency=False)
    mcp_module = _reload_mcp(monkeypatch, tmp_path)
    raw = await mcp_module.tasks_status(mcp_module.TaskStatusInput(file=str(task_file)))
    payload = json.loads(raw)
    assert "runnable" in payload["counts"]
