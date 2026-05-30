"""
Code generator implementations for Prime Contractor.

These generators implement the CodeGenerator protocol and can be used
with PrimeContractorWorkflow.
"""

from .primary_contractor import PrimaryContractorCodeGenerator, LeadContractorCodeGenerator

__all__ = [
    "PrimaryContractorCodeGenerator",
    "LeadContractorCodeGenerator",  # Backward-compat alias
]
