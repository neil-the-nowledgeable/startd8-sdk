"""Tests for Dockerfile structural validator (Phase 4, REQ-MP-322)."""
import pytest

from startd8.micro_prime.validators.dockerfile import (
    DockerfileValidationResult,
    validate_dockerfile,
)


# ── PI-013 reference Dockerfile ─────────────────────────────────────

PI_013_DOCKERFILE = """\
# syntax=docker/dockerfile:1

##############################################
# Stage 1: builder — install Python dependencies
##############################################
FROM --platform=$BUILDPLATFORM python:3.14.2-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /loadgen

COPY requirements.txt .

RUN pip install --prefix="/install" -r requirements.txt

##############################################
# Stage 2: Final image — minimal runtime layer
##############################################
FROM python:3.14.2-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV GEVENT_SUPPORT=True

COPY --from=builder /install /usr/local

WORKDIR /loadgen

COPY locustfile.py .

ENTRYPOINT locust --host="http://${FRONTEND_ADDR}" --headless -u "${USERS:-10}" -r "${RATE:-1}" 2>&1
"""


# ── Valid Dockerfiles ────────────────────────────────────────────────


class TestValidDockerfiles:
    def test_valid_single_stage(self):
        content = 'FROM python:3.12-slim\nWORKDIR /app\nCMD ["python", "app.py"]'
        result = validate_dockerfile(content)
        assert result.valid
        assert result.errors == []
        assert result.stage_count == 1

    def test_valid_multi_stage(self):
        """PI-013 loadgenerator Dockerfile must be structurally valid."""
        result = validate_dockerfile(PI_013_DOCKERFILE)
        assert result.valid
        assert result.errors == []
        assert result.stage_count == 2

    def test_valid_with_comments(self):
        content = "# This is a comment\nFROM python:3.12\n# Another comment\nRUN echo hello"
        result = validate_dockerfile(content)
        assert result.valid

    def test_valid_with_parser_directive(self):
        content = "# syntax=docker/dockerfile:1\nFROM python:3.12-slim"
        result = validate_dockerfile(content)
        assert result.valid
        assert result.warnings == []

    def test_valid_arg_before_from(self):
        content = "ARG VERSION=3.12\nFROM python:${VERSION}-slim"
        result = validate_dockerfile(content)
        assert result.valid

    def test_valid_continuation_lines(self):
        content = "FROM python:3.12-slim\nRUN apt-get update && \\\n    apt-get install -y gcc"
        result = validate_dockerfile(content)
        assert result.valid

    def test_continuation_backslash_only_line(self):
        """R1-S5: Line with only backslash between continuation lines → no DV-002."""
        content = "FROM python:3.12-slim\nRUN echo hello && \\\n\\\n    echo world"
        result = validate_dockerfile(content)
        assert result.valid
        assert not any("DV-002" in w for w in result.warnings)


# ── Invalid Dockerfiles ──────────────────────────────────────────────


class TestInvalidDockerfiles:
    def test_no_from(self):
        content = "RUN echo hello"
        result = validate_dockerfile(content)
        assert not result.valid
        assert any("DV-001" in e for e in result.errors)

    def test_empty(self):
        result = validate_dockerfile("")
        assert not result.valid
        assert any("DV-003" in e for e in result.errors)

    def test_only_comments(self):
        result = validate_dockerfile("# just a comment")
        assert not result.valid
        assert any("DV-003" in e for e in result.errors)

    def test_blank_only(self):
        result = validate_dockerfile("\n\n\n")
        assert not result.valid
        assert any("DV-003" in e for e in result.errors)


# ── Warnings ─────────────────────────────────────────────────────────


class TestWarnings:
    def test_unknown_directive(self):
        content = "FROM python:3.12\nFOOBAR something"
        result = validate_dockerfile(content)
        assert result.valid  # warnings don't affect validity
        assert any("DV-002" in w for w in result.warnings)

    def test_parser_directive_after_content(self):
        content = "FROM python:3.12\n# syntax=docker/dockerfile:1"
        result = validate_dockerfile(content)
        assert any("DV-005" in w for w in result.warnings)


# ── Best-practice advisories ─────────────────────────────────────────


class TestAdvisories:
    def test_no_user(self):
        content = 'FROM python:3.12-slim\nCMD ["python", "app.py"]'
        result = validate_dockerfile(content)
        assert any("DV-BP-002" in a for a in result.advisories)

    def test_latest_tag(self):
        content = 'FROM python:latest\nCMD ["python", "app.py"]'
        result = validate_dockerfile(content)
        assert any("DV-BP-001" in a for a in result.advisories)

    def test_no_tag(self):
        content = 'FROM python\nCMD ["python", "app.py"]'
        result = validate_dockerfile(content)
        assert any("DV-BP-001" in a for a in result.advisories)

    def test_scratch_no_advisory(self):
        """FROM scratch should not trigger DV-BP-001."""
        content = "FROM scratch\nCOPY app /app"
        result = validate_dockerfile(content)
        assert not any("DV-BP-001" in a for a in result.advisories)

    def test_add_usage(self):
        content = "FROM python:3.12\nADD . ."
        result = validate_dockerfile(content)
        assert any("DV-BP-003" in a for a in result.advisories)

    def test_shell_form_cmd(self):
        content = "FROM python:3.12\nCMD python app.py"
        result = validate_dockerfile(content)
        assert any("DV-BP-004" in a for a in result.advisories)

    def test_shell_form_entrypoint(self):
        content = "FROM python:3.12\nENTRYPOINT python app.py"
        result = validate_dockerfile(content)
        assert any("DV-BP-004" in a for a in result.advisories)

    def test_exec_form_no_advisory(self):
        content = 'FROM python:3.12\nCMD ["python", "app.py"]'
        result = validate_dockerfile(content)
        assert not any("DV-BP-004" in a for a in result.advisories)

    def test_single_stage_advisory(self):
        content = 'FROM python:3.12-slim\nCMD ["python", "app.py"]'
        result = validate_dockerfile(content)
        assert any("DV-BP-007" in a for a in result.advisories)

    def test_multi_stage_no_advisory(self):
        content = "FROM python:3.12 AS builder\nRUN echo build\nFROM python:3.12-slim\nCOPY --from=builder /app /app"
        result = validate_dockerfile(content)
        assert not any("DV-BP-007" in a for a in result.advisories)

    def test_no_healthcheck(self):
        content = 'FROM python:3.12-slim\nCMD ["python", "app.py"]'
        result = validate_dockerfile(content)
        assert any("DV-BP-008" in a for a in result.advisories)

    def test_no_label(self):
        content = 'FROM python:3.12-slim\nCMD ["python", "app.py"]'
        result = validate_dockerfile(content)
        assert any("DV-BP-009" in a for a in result.advisories)

    def test_python_alpine(self):
        content = "FROM python:3.12-alpine\nRUN echo hello"
        result = validate_dockerfile(content)
        assert any("DV-BP-010" in a for a in result.advisories)

    def test_from_with_platform_flag(self):
        """R1-S10: --platform flag must not cause false-positive DV-BP-001."""
        content = "FROM --platform=$BUILDPLATFORM python:3.14.2-alpine AS builder\nRUN echo hello"
        result = validate_dockerfile(content)
        assert not any("DV-BP-001" in a for a in result.advisories)

    def test_secret_in_env(self):
        """R1-S8: DV-BP-011 detects plaintext secrets in ENV."""
        content = "FROM python:3.12\nENV DB_PASSWORD=supersecret"
        result = validate_dockerfile(content)
        assert any("DV-BP-011" in a for a in result.advisories)

    def test_non_secret_env_no_advisory(self):
        """R1-S8: Normal ENV values don't trigger DV-BP-011."""
        content = "FROM python:3.12\nENV PYTHONDONTWRITEBYTECODE=1"
        result = validate_dockerfile(content)
        assert not any("DV-BP-011" in a for a in result.advisories)

    def test_secret_patterns(self):
        """Various secret-like ENV patterns all trigger DV-BP-011."""
        for env_line in [
            "ENV API_KEY=abc123",
            "ENV SECRET=mysecret",
            "ENV AUTH_TOKEN=xyz",
            "ENV PRIVATE_KEY=rsa-key",
        ]:
            content = f"FROM python:3.12\n{env_line}"
            result = validate_dockerfile(content)
            assert any("DV-BP-011" in a for a in result.advisories), (
                f"Expected DV-BP-011 for: {env_line}"
            )


# ── PI-013 integration ───────────────────────────────────────────────


class TestPI013Integration:
    def test_pi013_valid(self):
        """PI-013 Dockerfile must pass structural validation."""
        result = validate_dockerfile(PI_013_DOCKERFILE)
        assert result.valid
        assert result.stage_count == 2

    def test_pi013_directives(self):
        """PI-013 has expected directives."""
        result = validate_dockerfile(PI_013_DOCKERFILE)
        assert "FROM" in result.directives_found
        assert "WORKDIR" in result.directives_found
        assert "COPY" in result.directives_found
        assert "RUN" in result.directives_found
        assert "ENTRYPOINT" in result.directives_found

    def test_pi013_no_false_positive_bp001(self):
        """R1-S10: --platform flag doesn't cause false-positive for pinned image."""
        result = validate_dockerfile(PI_013_DOCKERFILE)
        assert not any("DV-BP-001" in a for a in result.advisories)

    def test_pi013_expected_advisories(self):
        """PI-013 should trigger specific known advisories."""
        result = validate_dockerfile(PI_013_DOCKERFILE)
        # No USER directive
        assert any("DV-BP-002" in a for a in result.advisories)
        # Shell form ENTRYPOINT
        assert any("DV-BP-004" in a for a in result.advisories)
        # Python + Alpine
        assert any("DV-BP-010" in a for a in result.advisories)
        # No HEALTHCHECK
        assert any("DV-BP-008" in a for a in result.advisories)
        # No LABEL
        assert any("DV-BP-009" in a for a in result.advisories)


# ── DockerfileValidationResult ───────────────────────────────────────


class TestValidationResult:
    def test_result_is_frozen(self):
        result = validate_dockerfile("FROM python:3.12")
        with pytest.raises(AttributeError):
            result.valid = False  # type: ignore[misc]

    def test_result_fields(self):
        result = validate_dockerfile("FROM python:3.12")
        assert isinstance(result.valid, bool)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)
        assert isinstance(result.advisories, list)
        assert isinstance(result.directives_found, list)
        assert isinstance(result.stage_count, int)
