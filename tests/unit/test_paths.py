"""Mirror guard for the SDK-level .startd8 store root (startd8.paths).

Pins the store-dir name + the root helper + the two conventional roots to their historical literals,
so the single SDK-wide home can't silently drift. This is the one definition of ``.startd8`` the whole
SDK (and the kickoff subsystem's re-export) builds on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8 import paths

pytestmark = pytest.mark.unit


def test_dirname_and_root_helper():
    assert paths.STARTD8_DIRNAME == ".startd8"
    assert paths.startd8_dir(Path("/x")) == Path("/x/.startd8")
    assert paths.startd8_dir("/x") == Path("/x/.startd8")  # str base too


def test_conventional_roots_unchanged():
    assert paths.default_data_dir() == Path.cwd() / ".startd8"
    assert paths.default_config_dir() == Path.home() / ".startd8"


def test_corpus_paths_unchanged():
    assert paths.controlled_corpus_path(Path("/x")) == Path("/x/.startd8/controlled-corpus.json")
    assert paths.corpus_content_dir(Path("/x")) == Path("/x/.startd8/corpus-content")


def test_kickoff_reexports_the_same_home():
    # the kickoff feature group re-exports the SDK home — one definition, not a duplicate
    from startd8.kickoff_experience import paths as kp

    assert kp.STARTD8_DIRNAME == paths.STARTD8_DIRNAME
    assert kp.startd8_dir is paths.startd8_dir
