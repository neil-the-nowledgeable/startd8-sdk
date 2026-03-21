"""Security Prime — orchestration layer for Anzen security validation.

Wires ``query_prime/security/verify_file()`` into the generation pipeline
with scoring, Kaizen feedback, and OTel instrumentation.

Query Prime owns detection (injection, credentials, lifecycle).
Security Prime owns the gate verdict (scoring, allowlist, Kaizen, OTel).

Public API::

    from startd8.security_prime import (
        compute_security_score,
        generate_security_hint,
        derive_security_contract,
        enrich_security_fields,
        SecurityScoreResult,
    )
"""

from startd8.security_prime.scorer import (
    SecurityScoreResult,
    compute_security_score,
    compute_aggregate_score,
)
from startd8.security_prime.kaizen import generate_security_hint
from startd8.security_prime.contract import derive_security_contract
from startd8.security_prime.enrichment import enrich_security_fields, enrich_gen_context

__all__ = [
    "SecurityScoreResult",
    "compute_security_score",
    "compute_aggregate_score",
    "generate_security_hint",
    "derive_security_contract",
    "enrich_security_fields",
    "enrich_gen_context",
]
