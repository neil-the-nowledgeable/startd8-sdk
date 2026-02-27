# [STARTD8-SKELETON]

from __future__ import annotations

import asyncio


async def fetch_data(url: str, *args, **kwargs) -> dict:
    raise NotImplementedError


async def send_request(method: str, *, timeout: int = 30) -> str:
    raise NotImplementedError


__all__ = ["fetch_data", "send_request"]
