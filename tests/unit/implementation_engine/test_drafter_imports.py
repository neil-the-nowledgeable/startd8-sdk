"""Tests for L1: import completeness instruction in draft system prompts."""

import pytest

from startd8.implementation_engine.drafter import get_drafter_system_prompt

_IMPORT_INSTRUCTION_MARKER = "CRITICAL"
_IMPORT_INSTRUCTION_PHRASE = "import statements"


class TestDraftSystemPromptImportInstruction:
    def test_create_mode_has_import_instruction(self):
        prompt, mode = get_drafter_system_prompt()
        assert mode == "create"
        assert _IMPORT_INSTRUCTION_MARKER in prompt
        assert _IMPORT_INSTRUCTION_PHRASE in prompt

    def test_edit_mode_has_import_instruction(self):
        files = {"app.py": "line\n" * 10}
        prompt, mode = get_drafter_system_prompt(files)
        assert mode == "edit"
        assert _IMPORT_INSTRUCTION_MARKER in prompt
        assert _IMPORT_INSTRUCTION_PHRASE in prompt

    def test_search_replace_mode_has_import_instruction(self):
        files = {"app.py": "line\n" * 60}
        prompt, mode = get_drafter_system_prompt(files)
        assert mode == "search_replace"
        assert _IMPORT_INSTRUCTION_MARKER in prompt
        assert _IMPORT_INSTRUCTION_PHRASE in prompt

    def test_skeleton_fill_mode_has_import_instruction(self):
        prompt, mode = get_drafter_system_prompt(skeleton_fill=True)
        assert mode == "skeleton_fill"
        assert _IMPORT_INSTRUCTION_MARKER in prompt
        assert _IMPORT_INSTRUCTION_PHRASE in prompt

    def test_instruction_mentions_cause(self):
        """The instruction should explain WHY imports matter."""
        prompt, _ = get_drafter_system_prompt()
        assert "#1 cause" in prompt or "generation failure" in prompt
