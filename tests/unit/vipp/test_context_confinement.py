# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""FR-QW-3 — ``vipp.context.ensure_posting`` confines the project root before any write.

Consistent with VIPP's already-confined serialize/apply paths (which reject symlinked roots). FDE is
intentionally NOT hardened (it has no confined-write system), so this lives only under the vipp suite.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from startd8.concierge.safe_write import SafeWriteError
from startd8.vipp.context import ensure_posting


def test_ensure_posting_rejects_symlinked_root_before_any_write(tmp_path):
    base = Path(os.path.realpath(tmp_path))
    target = base / "real"
    target.mkdir()
    link = base / "link"
    os.symlink(target, link)

    with pytest.raises(SafeWriteError):
        ensure_posting(link, sdk_version="9.9.9")
    # Nothing was written into the real target through the symlink.
    assert not (target / ".startd8").exists()


def test_ensure_posting_normal_root_unchanged(tmp_path):
    root = Path(os.path.realpath(tmp_path))
    ctx = ensure_posting(root, sdk_version="9.9.9")
    assert Path(ctx).is_file()
    assert (root / ".startd8" / "vipp" / "vipp-context.json").is_file()
    # Idempotent: a second call still succeeds (restamps SDK metadata).
    ctx2 = ensure_posting(root, sdk_version="9.9.9")
    assert ctx == ctx2


def test_ensure_posting_rejects_nonexistent_root(tmp_path):
    missing = Path(os.path.realpath(tmp_path)) / "nope"
    with pytest.raises(SafeWriteError):
        ensure_posting(missing, sdk_version="9.9.9")
