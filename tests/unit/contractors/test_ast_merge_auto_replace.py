"""Tests for ASTMergeStrategy auto-replace when source overlaps target (INV-4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.contractors.adapters.contextcore import ASTMergeStrategy, MergeStatus


@pytest.fixture
def tmp_merge_dir(tmp_path: Path) -> Path:
    return tmp_path


class TestAutoReplace:
    """When source class/function names overlap target >50%, auto-switch to replace."""

    def _write(self, d: Path, name: str, content: str) -> Path:
        p = d / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_overlapping_classes_trigger_replace(self, tmp_merge_dir: Path) -> None:
        """Source redefines same class — replace mode keeps source version."""
        target = self._write(
            tmp_merge_dir,
            "target.py",
            'class Greeter:\n    def greet(self):\n        return "old"\n',
        )
        source = self._write(
            tmp_merge_dir,
            "source.py",
            'class Greeter:\n    def greet(self):\n        return "new"\n',
        )
        merger = ASTMergeStrategy()
        result = merger.merge(source, target)
        assert result.status == MergeStatus.SUCCESS
        content = target.read_text(encoding="utf-8")
        # Replace mode: source's "new" version should be in the file
        assert '"new"' in content
        # Target's "old" version should NOT be in the file
        assert '"old"' not in content

    def test_overlapping_functions_trigger_replace(self, tmp_merge_dir: Path) -> None:
        """Source redefines same functions — replace mode keeps source."""
        target = self._write(
            tmp_merge_dir,
            "target.py",
            'def foo():\n    return 1\n\ndef bar():\n    return 2\n',
        )
        source = self._write(
            tmp_merge_dir,
            "source.py",
            'def foo():\n    return 10\n\ndef bar():\n    return 20\n',
        )
        merger = ASTMergeStrategy()
        result = merger.merge(source, target)
        assert result.status == MergeStatus.SUCCESS
        content = target.read_text(encoding="utf-8")
        assert "return 10" in content
        assert "return 20" in content
        assert "return 1\n" not in content

    def test_no_overlap_stays_additive(self, tmp_merge_dir: Path) -> None:
        """Disjoint names — additive merge adds source definitions."""
        target = self._write(
            tmp_merge_dir,
            "target.py",
            'class Alpha:\n    pass\n',
        )
        source = self._write(
            tmp_merge_dir,
            "source.py",
            'class Beta:\n    pass\n',
        )
        merger = ASTMergeStrategy()
        result = merger.merge(source, target)
        assert result.status == MergeStatus.SUCCESS
        content = target.read_text(encoding="utf-8")
        # Both classes present (additive)
        assert "Alpha" in content
        assert "Beta" in content

    def test_explicit_replace_mode_always_replaces(self, tmp_merge_dir: Path) -> None:
        """Explicit replace mode replaces regardless of overlap."""
        target = self._write(
            tmp_merge_dir,
            "target.py",
            'class Alpha:\n    pass\n',
        )
        source = self._write(
            tmp_merge_dir,
            "source.py",
            'class Beta:\n    pass\n',
        )
        merger = ASTMergeStrategy(merge_mode="replace")
        result = merger.merge(source, target)
        assert result.status == MergeStatus.SUCCESS
        content = target.read_text(encoding="utf-8")
        assert "Beta" in content
        assert "Alpha" not in content

    def test_main_guard_not_duplicated(self, tmp_merge_dir: Path) -> None:
        """__main__ guard in both files should not appear twice after merge."""
        main_block = 'if __name__ == "__main__":\n    main()\n'
        target = self._write(
            tmp_merge_dir,
            "target.py",
            f'def main():\n    print("old")\n\n{main_block}',
        )
        source = self._write(
            tmp_merge_dir,
            "source.py",
            f'def main():\n    print("new")\n\n{main_block}',
        )
        merger = ASTMergeStrategy()
        result = merger.merge(source, target)
        assert result.status == MergeStatus.SUCCESS
        content = target.read_text(encoding="utf-8")
        # Replace mode triggered — only one __main__ guard
        assert content.count("__main__") == 1

    def test_partial_overlap_below_threshold_stays_additive(
        self, tmp_merge_dir: Path
    ) -> None:
        """Less than 50% overlap — stays in additive mode."""
        target = self._write(
            tmp_merge_dir,
            "target.py",
            'class Alpha:\n    pass\n',
        )
        source = self._write(
            tmp_merge_dir,
            "source.py",
            (
                'class Alpha:\n    pass\n\n'
                'class Beta:\n    pass\n\n'
                'class Gamma:\n    pass\n'
            ),
        )
        merger = ASTMergeStrategy()
        result = merger.merge(source, target)
        content = target.read_text(encoding="utf-8")
        # 1/3 overlap (33%) < 50% → additive: Alpha kept from target, Beta+Gamma added
        assert "Alpha" in content
        assert "Beta" in content
        assert "Gamma" in content
