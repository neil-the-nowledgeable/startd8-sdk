# [STARTD8-SKELETON]

from __future__ import annotations

from pathlib import Path
import os


def compute(x: int, y: int = 0) -> str:
    raise NotImplementedError


def process(data: str) -> None:
    raise NotImplementedError


__all__ = ["compute", "process"]
