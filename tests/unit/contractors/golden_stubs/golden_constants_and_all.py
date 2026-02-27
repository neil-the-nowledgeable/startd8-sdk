# [STARTD8-SKELETON]

from __future__ import annotations


DEFAULT_TIMEOUT: float = ...


MAX_RETRIES: int = ...


def get_config() -> dict:
    raise NotImplementedError


__all__ = ["DEFAULT_TIMEOUT", "MAX_RETRIES", "get_config"]
