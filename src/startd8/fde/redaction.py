# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Inbound prose redaction (FR-23 / R3-S2) — strip secrets before any LLM submission.

A deterministic, dependency-free pass over plan/requirements text. Returns the redacted text
plus a manifest of what was stripped (surfaced under ``## Redaction manifest`` in the preflight
report). Conservative by design: false positives are cheaper than leaking a credential.
"""

from __future__ import annotations

import re
from typing import List, Tuple

# (description, compiled pattern) — match value, replace with a placeholder.
_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")),
    ("openai_api_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{20,}")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{12,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    (
        "generic_secret_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9._\-/+]{8,}['\"]?"
        ),
    ),
    (
        "dotenv_line",
        re.compile(
            r"(?im)^\s*[A-Z][A-Z0-9_]*_(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*\S+$"
        ),
    ),
]


def redact(text: str) -> Tuple[str, List[str]]:
    """Return (redacted_text, manifest). Manifest lists "<description> ×<count>" entries."""
    manifest: List[str] = []
    redacted = text
    for desc, pat in _PATTERNS:
        matches = pat.findall(redacted)
        if matches:
            manifest.append(f"{desc} ×{len(matches)}")
            redacted = pat.sub(f"«REDACTED:{desc}»", redacted)
    return redacted, manifest
