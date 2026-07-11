#!/usr/bin/env python3
"""
Test script to verify all agent configurations work correctly.
This script checks for the agent_name attribute issue and other configuration problems.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from startd8.agents import (
    MockAgent,
    ClaudeAgent,
    GPT4Agent,
    GeminiAgent,
    OpenAICompatibleAgent,
    ComposerAgent,
    BaseAgent
)

def test_agent_name_property(agent_class, agent_name, **kwargs):
    """Test that an agent has the agent_name property"""
    try:
        agent = agent_class(name=agent_name, **kwargs)
        
        # Test both .name and .agent_name
        assert hasattr(agent, 'name'), f"{agent_class.__name__} missing 'name' attribute"
        assert hasattr(agent, 'agent_name'), f"{agent_class.__name__} missing 'agent_name' property"
        
        # Test that they return the same value
        assert agent.name == agent_name, f"{agent_class.__name__}.name mismatch"
        assert agent.agent_name == agent_name, f"{agent_class.__name__}.agent_name mismatch"
        assert agent.name == agent.agent_name, f"{agent_class.__name__}: name != agent_name"
        
        print(f"✓ {agent_class.__name__}: name='{agent.name}', agent_name='{agent.agent_name}'")
        return True
    except Exception as e:
        print(f"✗ {agent_class.__name__}: {type(e).__name__}: {e}")
        return False

def main():
    """Run all agent configuration tests"""
    print("=" * 60)
    print("Agent Configuration Test")
    print("=" * 60)
    print()
    
    results = []
    
    # Test MockAgent (always works)
    print("Testing MockAgent...")
    results.append(("MockAgent", test_agent_name_property(MockAgent, "test-mock", model="test-model")))
    print()
    
    # Test ClaudeAgent (may fail if anthropic not installed or no API key)
    print("Testing ClaudeAgent...")
    try:
        results.append(("ClaudeAgent", test_agent_name_property(
            ClaudeAgent, 
            "test-claude",
            model="claude-sonnet-4-20250514"
        )))
    except ImportError as e:
        print(f"⚠ ClaudeAgent: {e} (skipping)")
        results.append(("ClaudeAgent", None))
    except Exception as e:
        print(f"✗ ClaudeAgent: {e}")
        results.append(("ClaudeAgent", False))
    print()
    
    # Test GPT4Agent (may fail if openai not installed or no API key)
    print("Testing GPT4Agent...")
    try:
        results.append(("GPT4Agent", test_agent_name_property(
            GPT4Agent,
            "test-gpt4",
            model="gpt-4-turbo-preview"
        )))
    except ImportError as e:
        print(f"⚠ GPT4Agent: {e} (skipping)")
        results.append(("GPT4Agent", None))
    except Exception as e:
        print(f"✗ GPT4Agent: {e}")
        results.append(("GPT4Agent", False))
    print()
    
    # Test GeminiAgent (may fail if google-genai not installed or no API key)
    print("Testing GeminiAgent...")
    try:
        results.append(("GeminiAgent", test_agent_name_property(
            GeminiAgent,
            "test-gemini",
            model="gemini-1.5-flash",
            api_key="test-key"  # Dummy key for initialization test
        )))
    except ImportError as e:
        print(f"⚠ GeminiAgent: {e} (skipping)")
        results.append(("GeminiAgent", None))
    except Exception as e:
        print(f"✗ GeminiAgent: {e}")
        results.append(("GeminiAgent", False))
    print()
    
    # Test OpenAICompatibleAgent (may fail if openai not installed)
    print("Testing OpenAICompatibleAgent...")
    try:
        results.append(("OpenAICompatibleAgent", test_agent_name_property(
            OpenAICompatibleAgent,
            "test-openai-compat",
            model="test-model",
            base_url="http://localhost:11434/v1"  # Ollama default
        )))
    except ImportError as e:
        print(f"⚠ OpenAICompatibleAgent: {e} (skipping)")
        results.append(("OpenAICompatibleAgent", None))
    except Exception as e:
        print(f"✗ OpenAICompatibleAgent: {e}")
        results.append(("OpenAICompatibleAgent", False))
    print()
    
    # Test ComposerAgent (may fail if openai not installed)
    print("Testing ComposerAgent...")
    try:
        results.append(("ComposerAgent", test_agent_name_property(
            ComposerAgent,
            "test-composer",
            model="composer"
        )))
    except ImportError as e:
        print(f"⚠ ComposerAgent: {e} (skipping)")
        results.append(("ComposerAgent", None))
    except Exception as e:
        print(f"✗ ComposerAgent: {e}")
        results.append(("ComposerAgent", False))
    print()
    
    # Test SkillAgent if available
    try:
        from startd8.skills.agent import SkillAgent
        print("Testing SkillAgent...")
        # SkillAgent requires skill_id, so we'll test with a dummy one
        # It will fail at runtime but should pass initialization
        try:
            agent = SkillAgent(skill_id="test-skill", name="test-skill-agent")
            assert hasattr(agent, 'name')
            assert hasattr(agent, 'agent_name')
            assert agent.name == "test-skill-agent"
            assert agent.agent_name == "test-skill-agent"
            print(f"✓ SkillAgent: name='{agent.name}', agent_name='{agent.agent_name}'")
            results.append(("SkillAgent", True))
        except Exception as e:
            print(f"✗ SkillAgent: {e}")
            results.append(("SkillAgent", False))
    except ImportError:
        print("⚠ SkillAgent: Not available (skipping)")
        results.append(("SkillAgent", None))
    print()
    
    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)
    
    for agent_name, result in results:
        if result is True:
            print(f"✓ {agent_name}: PASSED")
        elif result is False:
            print(f"✗ {agent_name}: FAILED")
        else:
            print(f"⚠ {agent_name}: SKIPPED")
    
    print()
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")
    
    if failed > 0:
        print("\n❌ Some agents failed configuration tests!")
        return 1
    elif passed == 0:
        print("\n⚠ No agents were tested (all skipped)")
        return 0
    else:
        print("\n✓ All tested agents passed configuration checks!")
        return 0

if __name__ == "__main__":
    sys.exit(main())

