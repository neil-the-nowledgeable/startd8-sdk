"""Agent configuration testing helpers.

Extracted verbatim from ``tui_improved.py`` (Pass A refactor).
"""

import os
from typing import Dict, Any

from ..agents import ClaudeAgent, GPT4Agent


class AgentConfigTester:
    """Test agent configurations"""

    @staticmethod
    def test_claude() -> Dict[str, Any]:
        """Test Claude configuration"""
        result = {
            'name': 'Claude',
            'configured': False,
            'working': False,
            'error': None
        }

        # Check API key
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            result['error'] = 'ANTHROPIC_API_KEY not set'
            return result

        result['configured'] = True

        # Try to initialize
        try:
            agent = ClaudeAgent()
            result['working'] = True
        except Exception as e:
            result['error'] = str(e)

        return result

    @staticmethod
    def test_gpt4() -> Dict[str, Any]:
        """Test GPT-4 configuration"""
        result = {
            'name': 'GPT-4',
            'configured': False,
            'working': False,
            'error': None
        }

        # Check API key
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            result['error'] = 'OPENAI_API_KEY not set'
            return result

        result['configured'] = True

        # Try to initialize
        try:
            agent = GPT4Agent()
            result['working'] = True
        except (ImportError, AttributeError) as e:
            # Log import/attribute errors
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.debug(f"GPT-4 agent initialization failed (import/attribute): {e}", exc_info=True, extra={"operation": "test_gpt4"})
            result['error'] = f"Initialization error: {e}"
        except Exception as e:
            # Log unexpected errors
            from ..logging_config import get_logger
            logger = get_logger(__name__)
            logger.warning(f"GPT-4 agent test failed: {e}", exc_info=True, extra={"operation": "test_gpt4"})
            result['error'] = str(e)

        return result

    @staticmethod
    def test_all() -> Dict[str, Dict[str, Any]]:
        """Test all agent configurations"""
        return {
            'claude': AgentConfigTester.test_claude(),
            'gpt4': AgentConfigTester.test_gpt4(),
            'mock': {
                'name': 'Mock',
                'configured': True,
                'working': True,
                'error': None
            }
        }
