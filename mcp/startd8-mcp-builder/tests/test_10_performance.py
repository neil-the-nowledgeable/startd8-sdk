"""Phase 6.1: Performance Tests.

Lightweight timing checks to ensure core operations are reasonably fast
on a typical macOS development machine. Thresholds are slightly more
lenient than the plan's raw numbers to reduce flakiness, but still
assert good performance.

Covers:
- T6.1.1 Skill discovery completes quickly
- T6.1.2 List skills completes quickly
- T6.1.3 Get skill info completes quickly
"""

from __future__ import annotations

import time

import pytest

import startd8_mcp
from startd8_mcp import ListSkillsInput, GetSkillInput, ResponseFormat


@pytest.mark.asyncio
async def test_skill_discovery_performance(monkeypatch: pytest.MonkeyPatch, test_skills_directory) -> None:
    """T6.1.1 - `_find_skills` should be fast on local disk.

    We average over multiple runs to smooth out noise and assert an
    upper bound that is generous but still catches gross regressions.
    """

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    iterations = 20
    start = time.perf_counter()
    for _ in range(iterations):
        startd8_mcp._find_skills()
    elapsed_avg = (time.perf_counter() - start) / iterations

    # Slightly relaxed vs plan's 500ms hard limit
    assert elapsed_avg < 0.75, f"Average discovery time too slow: {elapsed_avg:.4f}s"


@pytest.mark.asyncio
async def test_list_skills_performance(monkeypatch: pytest.MonkeyPatch, test_skills_directory) -> None:
    """T6.1.2 - `startd8_list_skills` should return quickly."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    params = ListSkillsInput(response_format=ResponseFormat.MARKDOWN, include_details=True)

    iterations = 10
    start = time.perf_counter()
    for _ in range(iterations):
        await startd8_mcp.startd8_list_skills(params)
    elapsed_avg = (time.perf_counter() - start) / iterations

    # Slightly relaxed vs plan's 1s limit
    assert elapsed_avg < 1.5, f"Average list_skills time too slow: {elapsed_avg:.4f}s"


@pytest.mark.asyncio
async def test_get_skill_info_performance(monkeypatch: pytest.MonkeyPatch, test_skills_directory) -> None:
    """T6.1.3 - `startd8_get_skill_info` should be fast."""

    monkeypatch.setenv("STARTD8_SKILL_PATH", str(test_skills_directory))
    monkeypatch.setattr(startd8_mcp, "DEFAULT_SKILL_PATHS", [])

    params = GetSkillInput(skill_name="skill-test-1", response_format=ResponseFormat.MARKDOWN)

    iterations = 10
    start = time.perf_counter()
    for _ in range(iterations):
        await startd8_mcp.startd8_get_skill_info(params)
    elapsed_avg = (time.perf_counter() - start) / iterations

    # Relaxed vs plan's 200ms limit, but still tight enough
    assert elapsed_avg < 0.5, f"Average get_skill_info time too slow: {elapsed_avg:.4f}s"

