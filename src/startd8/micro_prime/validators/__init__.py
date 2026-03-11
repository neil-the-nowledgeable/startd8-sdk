"""Micro Prime validators for non-Python file types."""

from startd8.micro_prime.validators.dockerfile import (
    DockerfileValidationResult,
    validate_dockerfile,
)

__all__ = ["DockerfileValidationResult", "validate_dockerfile"]
