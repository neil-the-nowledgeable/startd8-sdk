"""Data models for proto skeleton generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class ProtoRpc:
    name: str
    request: str
    response: str


@dataclass(frozen=True)
class ProtoService:
    name: str
    rpcs: Tuple[ProtoRpc, ...]


@dataclass(frozen=True)
class ProtoDocument:
    package: str
    services: Tuple[ProtoService, ...]
    go_package: Optional[str] = None


@dataclass(frozen=True)
class GrpcServiceSpec:
    proto: str
    service: str
    language: str
    out: str
    stub_module: Optional[str] = None
