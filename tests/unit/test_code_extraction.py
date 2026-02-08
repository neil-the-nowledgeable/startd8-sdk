"""Tests for startd8.utils.code_extraction — multi-file extraction."""

import pytest

from startd8.utils.code_extraction import extract_multi_file_code


# ---------------------------------------------------------------------------
# Strategy 1: file-path comment markers
# ---------------------------------------------------------------------------

class TestFilePathCommentMarkers:
    """LLM output uses // path/file.ext or # path/file.py markers."""

    def test_two_typescript_files(self):
        response = (
            "Here is the implementation:\n\n"
            "// src/components/MigrationQueue.tsx\n"
            "```tsx\n"
            "import React from 'react';\n"
            "export const MigrationQueue = () => <div>Queue</div>;\n"
            "```\n\n"
            "// src/hooks/useBatchMigration.ts\n"
            "```ts\n"
            "export function useBatchMigration() {\n"
            "  return { migrate: () => {} };\n"
            "}\n"
            "```\n"
        )
        targets = [
            "src/components/MigrationQueue.tsx",
            "src/hooks/useBatchMigration.ts",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        assert "MigrationQueue" in result["src/components/MigrationQueue.tsx"]
        assert "useBatchMigration" in result["src/hooks/useBatchMigration.ts"]
        # Ensure content is NOT the same for both
        assert (
            result["src/components/MigrationQueue.tsx"]
            != result["src/hooks/useBatchMigration.ts"]
        )

    def test_python_hash_markers(self):
        response = (
            "# app/models.py\n"
            "```python\n"
            "class User:\n"
            "    pass\n"
            "```\n\n"
            "# app/views.py\n"
            "```python\n"
            "def index():\n"
            "    return 'hello'\n"
            "```\n"
        )
        targets = ["app/models.py", "app/views.py"]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        assert "class User" in result["app/models.py"]
        assert "def index" in result["app/views.py"]


# ---------------------------------------------------------------------------
# Strategy 2: fenced blocks with filename in lang tag or first-line comment
# ---------------------------------------------------------------------------

class TestFencedBlockFilenameHints:
    """LLM output uses ```filename.ext as the language tag."""

    def test_filename_as_language_tag(self):
        response = (
            "```MigrationQueue.tsx\n"
            "import React from 'react';\n"
            "export const MigrationQueue = () => <div/>;\n"
            "```\n\n"
            "```useBatchMigration.ts\n"
            "export function useBatchMigration() { return {}; }\n"
            "```\n"
        )
        targets = [
            "src/components/MigrationQueue.tsx",
            "src/hooks/useBatchMigration.ts",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        assert "MigrationQueue" in result["src/components/MigrationQueue.tsx"]
        assert "useBatchMigration" in result["src/hooks/useBatchMigration.ts"]

    def test_first_line_comment_hint(self):
        response = (
            "```tsx\n"
            "// MigrationQueue.tsx\n"
            "import React from 'react';\n"
            "export const MigrationQueue = () => <div/>;\n"
            "```\n\n"
            "```ts\n"
            "// useBatchMigration.ts\n"
            "export function useBatchMigration() { return {}; }\n"
            "```\n"
        )
        targets = [
            "src/components/MigrationQueue.tsx",
            "src/hooks/useBatchMigration.ts",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        # The filename comment should be stripped from the code
        assert "// MigrationQueue.tsx" not in result["src/components/MigrationQueue.tsx"]
        assert "import React" in result["src/components/MigrationQueue.tsx"]


# ---------------------------------------------------------------------------
# Fallback / edge cases
# ---------------------------------------------------------------------------

class TestFallbackBehavior:
    """When splitting fails, returns empty dict."""

    def test_empty_response(self):
        assert extract_multi_file_code("", ["a.py"]) == {}

    def test_empty_target_files(self):
        assert extract_multi_file_code("some code", []) == {}

    def test_single_block_no_markers(self):
        """Single code block with no file markers — can't split."""
        response = (
            "```python\n"
            "def hello(): pass\n"
            "```\n"
        )
        result = extract_multi_file_code(response, ["a.py", "b.py"])
        assert result == {}

    def test_partial_match_returns_empty(self):
        """If only one of two target files is found, return empty dict."""
        response = (
            "// src/a.py\n"
            "```python\n"
            "x = 1\n"
            "```\n"
        )
        result = extract_multi_file_code(response, ["src/a.py", "src/b.py"])
        assert result == {}

    def test_single_target_file_returns_empty(self):
        """Single target file — function isn't designed for this case."""
        response = "```python\ndef hello(): pass\n```\n"
        # With a single target file the caller should use extract_code_from_response
        # This function requires markers to split, so returns empty
        result = extract_multi_file_code(response, ["hello.py"])
        assert result == {}


class TestCaseInsensitiveMatching:
    """Basename matching is case-insensitive."""

    def test_case_mismatch_still_matches(self):
        response = (
            "// migrationqueue.tsx\n"
            "```tsx\n"
            "export const MQ = () => <div/>;\n"
            "```\n\n"
            "// usebatchmigration.ts\n"
            "```ts\n"
            "export function ubm() {}\n"
            "```\n"
        )
        targets = [
            "src/MigrationQueue.tsx",
            "src/useBatchMigration.ts",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
