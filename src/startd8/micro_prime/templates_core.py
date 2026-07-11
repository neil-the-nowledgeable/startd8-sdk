# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Core template models (extracted from templates.py, Tier-2)."""

from __future__ import annotations

from dataclasses import dataclass  # noqa: F401
from typing import Callable, Optional  # noqa: F401


@dataclass(frozen=True)
class CodeTemplate:
    """Deterministic code template entry."""

    name: str
    match_fn: Callable[
        [ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]],
        bool,
    ]
    render_fn: Callable[
        [ForwardElementSpec, ForwardFileSpec, list[InterfaceContract]],
        str,
    ]


@dataclass(frozen=True)
class TemplateMatch:
    """Template match result."""

    name: str
    code: str
