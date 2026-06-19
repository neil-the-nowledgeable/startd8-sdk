# GENERATED from prisma/schema.prisma (+ contexts.yaml) — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-context-integration
# Source of truth: the Prisma schema and the contexts manifest.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba
# contexts-sha256: 074ccef8b51da9de39da42467d525aa1967723ddaaa0844f34156d15d1826547

from __future__ import annotations

import os
import re

from clients.email_client import EmailClient


"""Outbound context client registry (Role 3 P2 integration seam).

For entities owned by remote producer contexts (prisma/contexts.yaml), use the
typed factories below — NOT direct SQLModel/session access via app.tables.
Integration glue may compose these clients; provenance constants are embedded per producer.
"""


def _context_env_key(producer_id: str) -> str:
    """Env override: STARTD8_CONTEXT_<ID>_BASE_URL."""
    safe = re.sub(r"[^0-9A-Z_]", "_", producer_id.upper())
    return f"STARTD8_CONTEXT_{safe}_BASE_URL"

_PRODUCER_EMAIL_ID = 'email'
_CONTRACT_SHA_EMAIL = '299289569c938de0f8096dc6e5460a18dda169ec9d1872d4683d7eb76628ac24'
_DEFAULT_BASE_EMAIL = 'http://email:8080'

def get_email_client() -> EmailClient:
    """Factory for outbound producer 'email' (clients/email_client.py)."""
    override = (os.environ.get(_context_env_key(_PRODUCER_EMAIL_ID)) or '').strip()
    base = override or _DEFAULT_BASE_EMAIL
    return EmailClient(base.rstrip('/'))
