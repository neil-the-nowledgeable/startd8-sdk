"""Tests for self-consistency semantic validators (AR-143 through AR-147).

Validates all 5 validators from ``self_consistency.py``:
- AR-146: Placeholder detection
- AR-143: Import dependency validation
- AR-145: Proto field reference validation
- AR-144: Protocol fidelity
- AR-147: Dockerfile coherence
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# AR-146: Placeholder Detection
# ---------------------------------------------------------------------------

class TestPlaceholderDetection:

    def test_clean_code_passes(self):
        """Clean production code produces no issues."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_placeholder_detection,
        )
        code = textwrap.dedent("""\
            import os
            def main():
                path = os.getcwd()
                return path
        """)
        issues = validate_placeholder_detection(code, None)
        assert issues == []

    def test_detects_todo(self):
        """Detects TODO markers."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_placeholder_detection,
        )
        code = "x = 1  # TODO implement this\n"
        issues = validate_placeholder_detection(code, None)
        assert len(issues) >= 1
        assert issues[0]["validator"] == "placeholder_detection"
        assert "TODO" in issues[0]["message"]

    def test_detects_not_implemented_error(self):
        """Detects NotImplementedError."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_placeholder_detection,
        )
        code = textwrap.dedent("""\
            def handler():
                raise NotImplementedError
        """)
        issues = validate_placeholder_detection(code, None)
        assert len(issues) >= 1
        assert any("NotImplementedError" in i["message"] for i in issues)

    def test_detects_your_key_here(self):
        """Detects YOUR_*_HERE patterns."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_placeholder_detection,
        )
        code = 'API_KEY = "YOUR_API_KEY_HERE"\n'
        issues = validate_placeholder_detection(code, None)
        assert len(issues) >= 1
        assert any("YOUR_API_KEY_HERE" in i["message"] for i in issues)

    def test_detects_replace_with(self):
        """Detects REPLACE_WITH_* patterns (DEV-002)."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_placeholder_detection,
        )
        code = 'digest = "REPLACE_WITH_ACTUAL_DIGEST"\n'
        issues = validate_placeholder_detection(code, None)
        assert len(issues) >= 1
        assert any("REPLACE_WITH" in i["message"] for i in issues)

    def test_subprocess_clean(self, tmp_path: Path):
        """Subprocess invocation exits cleanly for production code."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "clean.py"
        f.write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            run_validator("placeholder_detection", [str(f)])
        assert exc_info.value.code == 0

    def test_subprocess_detects(self, tmp_path: Path):
        """Subprocess invocation exits with code 1 on placeholder."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        f = tmp_path / "placeholder.py"
        f.write_text('x = "REPLACE_WITH_REAL_VALUE"\n', encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            run_validator("placeholder_detection", [str(f)])
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# AR-143: Import Dependency Validation
# ---------------------------------------------------------------------------

class TestImportDependency:

    def test_no_requirements_no_issues(self):
        """When no requirements.txt is available, returns no issues."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_import_dependency,
        )
        code = "import requests\n"

        class Stub:
            cwd = "/nonexistent/path"
            prompt_constraints = ()
            deps_source = None

        issues = validate_import_dependency(code, Stub())
        assert issues == []

    def test_detects_undeclared_import(self, tmp_path: Path):
        """Flags imports not listed in requirements.txt."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_import_dependency,
        )
        # Create requirements.txt with only 'flask'
        (tmp_path / "requirements.txt").write_text("flask>=2.0\n", encoding="utf-8")

        code = textwrap.dedent("""\
            import requests
            import flask
        """)

        class Stub:
            cwd = str(tmp_path)
            prompt_constraints = ()
            deps_source = None

        issues = validate_import_dependency(code, Stub())
        assert len(issues) >= 1
        assert any("requests" in i["message"] for i in issues)
        # flask should NOT be flagged
        assert not any("flask" in i["message"] for i in issues)

    def test_import_to_package_mapping(self, tmp_path: Path):
        """PIL import maps to Pillow in requirements."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_import_dependency,
        )
        (tmp_path / "requirements.txt").write_text("Pillow>=9.0\n", encoding="utf-8")

        code = "from PIL import Image\n"

        class Stub:
            cwd = str(tmp_path)
            prompt_constraints = ()
            deps_source = None

        issues = validate_import_dependency(code, Stub())
        # PIL → Pillow mapping should prevent false positive
        assert issues == []

    def test_stdlib_always_allowed(self, tmp_path: Path):
        """Standard library imports are never flagged."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_import_dependency,
        )
        (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")

        code = textwrap.dedent("""\
            import os
            import json
            import sys
        """)

        class Stub:
            cwd = str(tmp_path)
            prompt_constraints = ()
            deps_source = None

        issues = validate_import_dependency(code, Stub())
        assert issues == []

    def test_multi_import_checks_all_aliases(self, tmp_path: Path):
        """R1 bug fix: `import os, requests` must check both names."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_import_dependency,
        )
        (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")

        # `import os, requests` — os is stdlib (allowed), requests is not declared
        code = "import os, requests\n"

        class Stub:
            cwd = str(tmp_path)
            prompt_constraints = ()
            deps_source = None

        issues = validate_import_dependency(code, Stub())
        assert len(issues) == 1
        assert "requests" in issues[0]["message"]

    def test_requirements_txt_fallback(self, tmp_path: Path):
        """Subprocess uses cwd to find requirements.txt."""
        from startd8.workflows.builtin.preflight_rules.rules_validators import (
            run_validator,
        )
        (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
        f = tmp_path / "app.py"
        f.write_text("import nonexistent_package_xyz\n", encoding="utf-8")

        # Run from tmp_path as cwd so it finds requirements.txt
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(SystemExit) as exc_info:
                run_validator("import_dependency", [str(f)])
            assert exc_info.value.code == 1
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# AR-145: Proto Field References
# ---------------------------------------------------------------------------

class TestProtoFieldReferences:

    def test_no_protos_no_issues(self):
        """When no .proto files exist, returns no issues."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_proto_field_references,
        )
        code = "x.items\n"

        class Stub:
            cwd = "/nonexistent"
            prompt_constraints = ()

        issues = validate_proto_field_references(code, Stub())
        assert issues == []

    def test_detects_plural_mismatch(self, tmp_path: Path):
        """Detects item vs items mismatch when proto defines 'item'."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_proto_field_references,
        )
        # Create a .proto file with field 'product_id'
        proto_dir = tmp_path / "protos"
        proto_dir.mkdir()
        (proto_dir / "service.proto").write_text(
            textwrap.dedent("""\
                message Request {
                    string product_id = 1;
                    string name = 2;
                }
            """),
            encoding="utf-8",
        )

        # Code uses plural form 'product_ids' but proto has 'product_id'
        code = textwrap.dedent("""\
            class Handler:
                def process(self, request):
                    return request.product_ids
        """)

        class Stub:
            cwd = str(tmp_path)
            prompt_constraints = ()

        issues = validate_proto_field_references(code, Stub())
        assert len(issues) >= 1
        assert any("product_id" in i["message"] for i in issues)


# ---------------------------------------------------------------------------
# AR-144: Protocol Fidelity
# ---------------------------------------------------------------------------

class TestProtocolFidelity:

    def test_no_metadata_no_issues(self):
        """When no service_metadata, returns no issues."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_protocol_fidelity,
        )
        code = "import requests\nrequests.get('http://example.com')\n"
        issues = validate_protocol_fidelity(code, "app.py", None)
        assert issues == []

    def test_grpc_declared_http_used(self):
        """DEV-001: HTTP patterns in gRPC-declared service → issue."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_protocol_fidelity,
        )
        code = textwrap.dedent("""\
            import requests
            def call_service():
                return requests.get("http://example.com/api")
        """)
        metadata = {"transport_protocol": "grpc"}
        issues = validate_protocol_fidelity(code, "client.py", metadata)
        assert len(issues) >= 1
        assert issues[0]["validator"] == "protocol_fidelity"
        assert "HTTP" in issues[0]["message"] or "http" in issues[0]["message"].lower()

    def test_http_declared_grpc_used(self):
        """gRPC patterns in HTTP-declared service → issue."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_protocol_fidelity,
        )
        code = textwrap.dedent("""\
            import grpc
            channel = grpc.insecure_channel("localhost:50051")
        """)
        metadata = {"transport_protocol": "http"}
        issues = validate_protocol_fidelity(code, "client.py", metadata)
        assert len(issues) >= 1

    def test_matching_protocol_no_issues(self):
        """gRPC code with gRPC transport → no issues."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_protocol_fidelity,
        )
        code = textwrap.dedent("""\
            import grpc
            channel = grpc.insecure_channel("localhost:50051")
        """)
        metadata = {"transport_protocol": "grpc"}
        issues = validate_protocol_fidelity(code, "client.py", metadata)
        assert issues == []


# ---------------------------------------------------------------------------
# AR-147: Dockerfile Coherence
# ---------------------------------------------------------------------------

class TestDockerfileCoherence:

    def test_non_dockerfile_skipped(self):
        """Non-Dockerfile files are not checked."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_dockerfile_coherence,
        )
        code = "FROM python:3.11\n"
        issues = validate_dockerfile_coherence(code, "app.py", None)
        assert issues == []

    def test_base_image_mismatch(self):
        """gRPC service with Flask base image → issue."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_dockerfile_coherence,
        )
        code = textwrap.dedent("""\
            FROM tiangolo/uvicorn-gunicorn-flask:python3.9
            COPY . /app
        """)
        metadata = {"transport_protocol": "grpc"}
        issues = validate_dockerfile_coherence(code, "Dockerfile", metadata)
        assert len(issues) >= 1
        assert "base image" in issues[0]["message"].lower() or "HTTP" in issues[0]["message"]

    def test_grpc_healthcheck_mismatch(self):
        """DEV-004: gRPC service with curl healthcheck → issue."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_dockerfile_coherence,
        )
        code = textwrap.dedent("""\
            FROM python:3.11
            HEALTHCHECK CMD curl -f http://localhost:8080/health
        """)
        metadata = {"transport_protocol": "grpc"}
        issues = validate_dockerfile_coherence(code, "Dockerfile", metadata)
        assert len(issues) >= 1
        assert any("curl" in i["message"] or "HTTP" in i["message"] for i in issues)

    def test_matching_healthcheck_passes(self):
        """gRPC service with grpc_health_probe → no issues."""
        from startd8.contractors.artisan_phases.self_consistency import (
            validate_dockerfile_coherence,
        )
        code = textwrap.dedent("""\
            FROM python:3.11
            HEALTHCHECK CMD grpc_health_probe -addr=:50051
        """)
        metadata = {"transport_protocol": "grpc"}
        issues = validate_dockerfile_coherence(code, "Dockerfile", metadata)
        assert issues == []
