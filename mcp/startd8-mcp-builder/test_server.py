#!/usr/bin/env python3
"""
Quick test script for Startd8 MCP Server

Tests the core functionality without needing to run the full MCP server.
"""

import asyncio
from startd8_mcp import (
    startd8_list_skills,
    startd8_get_skill_info,
    ListSkillsInput,
    GetSkillInput,
    ResponseFormat
)


async def test_list_skills():
    """Test listing skills."""
    print("=" * 70)
    print("TEST: List Skills (Markdown)")
    print("=" * 70)
    
    result = await startd8_list_skills(
        ListSkillsInput(
            response_format=ResponseFormat.MARKDOWN,
            include_details=False
        )
    )
    print(result)
    print()


async def test_list_skills_detailed():
    """Test listing skills with details."""
    print("=" * 70)
    print("TEST: List Skills with Details (JSON)")
    print("=" * 70)
    
    result = await startd8_list_skills(
        ListSkillsInput(
            response_format=ResponseFormat.JSON,
            include_details=True
        )
    )
    print(result)
    print()


async def test_get_skill_info():
    """Test getting skill info."""
    print("=" * 70)
    print("TEST: Get Skill Info (mcp-builder)")
    print("=" * 70)
    
    result = await startd8_get_skill_info(
        GetSkillInput(
            skill_name="mcp-builder",
            response_format=ResponseFormat.MARKDOWN
        )
    )
    print(result[:1000] + "..." if len(result) > 1000 else result)
    print()


async def test_get_skill_info_not_found():
    """Test getting info for non-existent skill."""
    print("=" * 70)
    print("TEST: Get Skill Info (non-existent)")
    print("=" * 70)
    
    result = await startd8_get_skill_info(
        GetSkillInput(
            skill_name="this-skill-does-not-exist",
            response_format=ResponseFormat.MARKDOWN
        )
    )
    print(result)
    print()


async def main():
    """Run all tests."""
    print("\n🧪 Startd8 MCP Server Tests\n")
    
    await test_list_skills()
    await test_list_skills_detailed()
    await test_get_skill_info()
    await test_get_skill_info_not_found()
    
    print("=" * 70)
    print("✅ All tests completed")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
