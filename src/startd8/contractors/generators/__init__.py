"""
Code generator implementations for Prime Contractor.

These generators implement the CodeGenerator protocol and can be used
with PrimeContractorWorkflow.
"""

from .lead_contractor import LeadContractorCodeGenerator

__all__ = [
    "LeadContractorCodeGenerator",
]
