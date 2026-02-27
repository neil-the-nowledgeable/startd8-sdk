# [STARTD8-SKELETON]

from __future__ import annotations

from typing import Optional


class BaseProcessor:
    """
    Base class for data processing.
    """
    def __init__(self, config: dict) -> None:
        raise NotImplementedError

    def process(self, data: str) -> Optional[str]:
        raise NotImplementedError

    @staticmethod
    def validate(data: str) -> bool:
        raise NotImplementedError


__all__ = ["BaseProcessor"]
