"""Tests for validate_disk_compliance() in forward_manifest_validator."""

import pytest

from startd8.forward_manifest_validator import (
    DiskComplianceResult,
    validate_disk_compliance,
)
from startd8.forward_manifest import (
    ForwardManifest,
    ForwardFileSpec,
    ForwardElementSpec,
    ForwardImportSpec,
)
from startd8.utils.code_manifest import ElementKind, Signature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_py(tmp_path, rel_path, content):
    """Write a Python file under tmp_path and return the relative path string."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return rel_path


# ---------------------------------------------------------------------------
# 1. Clean file (0 stubs, 0 duplicates, ast_valid=True)
# ---------------------------------------------------------------------------


class TestCleanFile:
    def test_clean_file_defaults(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "mymod.py",
            'def greet(name: str) -> str:\n    return f"Hello, {name}"\n',
        )
        result = validate_disk_compliance(rel, str(tmp_path))

        assert result.ast_valid is True
        assert result.stubs_remaining == 0
        assert result.duplicate_definitions == 0
        assert result.import_completeness == 1.0
        assert result.contract_compliance == 1.0
        assert result.contract_violations == []
        assert result.error is None

    def test_clean_file_with_class(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "models.py",
            (
                "class Foo:\n"
                "    def bar(self):\n"
                "        return 42\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True
        assert result.stubs_remaining == 0
        assert result.duplicate_definitions == 0


# ---------------------------------------------------------------------------
# 2. Stubbed file (raise NotImplementedError / bare pass)
# ---------------------------------------------------------------------------


class TestStubbedFile:
    def test_raise_not_implemented(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "stub1.py",
            "def todo():\n    raise NotImplementedError\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.stubs_remaining == 1

    def test_raise_not_implemented_call(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "stub2.py",
            'def todo():\n    raise NotImplementedError("not done")\n',
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.stubs_remaining == 1

    def test_bare_pass(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "stub3.py",
            "def placeholder():\n    pass\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.stubs_remaining == 1

    def test_pass_after_docstring(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "stub4.py",
            'def placeholder():\n    """Docstring."""\n    pass\n',
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.stubs_remaining == 1

    def test_multiple_stubs(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "stub5.py",
            (
                "def a():\n    pass\n\n"
                "def b():\n    raise NotImplementedError\n\n"
                "def c():\n    return 1\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.stubs_remaining == 2

    def test_method_stub(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "stub6.py",
            (
                "class Svc:\n"
                "    def process(self):\n"
                "        raise NotImplementedError\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.stubs_remaining == 1


# ---------------------------------------------------------------------------
# 3. Missing imports (import_completeness < 1.0)
# ---------------------------------------------------------------------------


class TestMissingImports:
    def test_partial_imports(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "app.py",
            "import os\n\ndef run():\n    return os.getcwd()\n",
        )
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    imports=[
                        ForwardImportSpec(kind="import", module="os"),
                        ForwardImportSpec(kind="import", module="sys"),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        assert result.import_completeness == pytest.approx(0.5)

    def test_all_imports_missing(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "empty_imports.py",
            "x = 1\n",
        )
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    imports=[
                        ForwardImportSpec(kind="import", module="json"),
                        ForwardImportSpec(kind="from", module="pathlib"),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        assert result.import_completeness == pytest.approx(0.0)

    def test_all_imports_present(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "full_imports.py",
            "import json\nfrom pathlib import Path\n",
        )
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    imports=[
                        ForwardImportSpec(kind="import", module="json"),
                        ForwardImportSpec(kind="from", module="pathlib"),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        assert result.import_completeness == pytest.approx(1.0)

    def test_submodule_import_matches(self, tmp_path):
        """An actual import of os.path should match a spec for os."""
        rel = _write_py(
            tmp_path,
            "sub_import.py",
            "import os.path\n",
        )
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    imports=[
                        ForwardImportSpec(kind="import", module="os"),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        assert result.import_completeness == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. Duplicate definitions at module level
# ---------------------------------------------------------------------------


class TestDuplicateDefinitions:
    def test_duplicate_function(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "dupes.py",
            (
                "def process():\n    return 1\n\n"
                "def process():\n    return 2\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.duplicate_definitions == 1

    def test_duplicate_class(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "dupes_cls.py",
            (
                "class Foo:\n    pass\n\n"
                "class Foo:\n    pass\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.duplicate_definitions == 1

    def test_no_duplicates(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "no_dupes.py",
            "def a():\n    pass\n\ndef b():\n    pass\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.duplicate_definitions == 0

    def test_nested_same_name_not_counted(self, tmp_path):
        """Same name inside a class should not count as module-level duplicate."""
        rel = _write_py(
            tmp_path,
            "nested.py",
            (
                "class Outer:\n"
                "    def run(self):\n"
                "        return 1\n\n"
                "    def run(self):\n"
                "        return 2\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        # Only module-level definitions count — Outer appears once
        assert result.duplicate_definitions == 0

    def test_triple_definition(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "triple.py",
            (
                "def x():\n    pass\n\n"
                "def x():\n    pass\n\n"
                "def x():\n    pass\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.duplicate_definitions == 2


# ---------------------------------------------------------------------------
# 5. Syntax error file (ast_valid=False)
# ---------------------------------------------------------------------------


class TestSyntaxError:
    def test_syntax_error(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "broken.py",
            "def oops(\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False
        assert result.error is not None
        assert "syntax_error" in result.error

    def test_syntax_error_skips_further_checks(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "broken2.py",
            "def foo(:\n    pass\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False
        assert result.stubs_remaining == 0
        assert result.duplicate_definitions == 0


# ---------------------------------------------------------------------------
# 6. Non-existent file (error="file_not_found")
# ---------------------------------------------------------------------------


class TestNonExistentFile:
    def test_missing_file(self, tmp_path):
        result = validate_disk_compliance("does_not_exist.py", str(tmp_path))
        assert result.ast_valid is False
        assert result.error == "file_not_found"
        assert result.file_path == "does_not_exist.py"


# ---------------------------------------------------------------------------
# 7. Non-Python file (returns default result)
# ---------------------------------------------------------------------------


class TestNonPythonFile:
    def test_txt_file(self, tmp_path):
        rel = "readme.txt"
        (tmp_path / rel).write_text("Hello", encoding="utf-8")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True
        assert result.stubs_remaining == 0
        assert result.error is None

    def test_yaml_file(self, tmp_path):
        rel = "config.yaml"
        (tmp_path / rel).write_text("key: value\n", encoding="utf-8")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True
        assert result.error is None


# ---------------------------------------------------------------------------
# 8. Contract violations — manifest spec elements missing
# ---------------------------------------------------------------------------


class TestContractViolations:
    def test_missing_function_element(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "svc.py",
            "def existing():\n    return 1\n",
        )
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    elements=[
                        ForwardElementSpec(
                            kind=ElementKind.FUNCTION,
                            name="existing",
                            signature=Signature(params=[]),
                        ),
                        ForwardElementSpec(
                            kind=ElementKind.FUNCTION,
                            name="missing_func",
                            signature=Signature(params=[]),
                        ),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        assert len(result.contract_violations) == 1
        v = result.contract_violations[0]
        assert v.violation_type == "missing_function"
        assert "missing_func" in v.expected
        assert v.severity == "error"

    def test_missing_class_element(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "models.py",
            "x = 1\n",
        )
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    elements=[
                        ForwardElementSpec(
                            kind=ElementKind.CLASS,
                            name="MyModel",
                        ),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        assert len(result.contract_violations) == 1
        assert result.contract_violations[0].violation_type == "missing_class"

    def test_contract_compliance_score(self, tmp_path):
        """Contract compliance should reflect fraction of satisfied checks."""
        rel = _write_py(
            tmp_path,
            "partial.py",
            "import os\n\ndef alpha():\n    return 1\n",
        )
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    elements=[
                        ForwardElementSpec(
                            kind=ElementKind.FUNCTION,
                            name="alpha",
                            signature=Signature(params=[]),
                        ),
                        ForwardElementSpec(
                            kind=ElementKind.FUNCTION,
                            name="beta",
                            signature=Signature(params=[]),
                        ),
                    ],
                    imports=[
                        ForwardImportSpec(kind="import", module="os"),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        # 3 total checks (2 elements + 1 import), 1 error violation (missing beta)
        assert result.contract_compliance == pytest.approx(1.0 - 1 / 3)

    def test_missing_import_violation(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "needs_import.py",
            "def go():\n    return 1\n",
        )
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    imports=[
                        ForwardImportSpec(kind="import", module="httpx"),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        import_violations = [
            v for v in result.contract_violations if v.violation_type == "missing_import"
        ]
        assert len(import_violations) == 1
        assert "httpx" in import_violations[0].expected

    def test_no_violations_when_all_present(self, tmp_path):
        rel = _write_py(
            tmp_path,
            "complete.py",
            (
                "import json\n\n"
                "class Handler:\n"
                "    def process(self):\n"
                "        return json.dumps({})\n"
            ),
        )
        manifest = ForwardManifest(
            file_specs={
                rel: ForwardFileSpec(
                    file=rel,
                    elements=[
                        ForwardElementSpec(
                            kind=ElementKind.CLASS,
                            name="Handler",
                        ),
                    ],
                    imports=[
                        ForwardImportSpec(kind="import", module="json"),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        assert result.contract_violations == []
        assert result.contract_compliance == pytest.approx(1.0)
        assert result.import_completeness == pytest.approx(1.0)

    def test_file_not_in_manifest_skips_contract_check(self, tmp_path):
        """When file_path is not in manifest.file_specs, no contract checks run."""
        rel = _write_py(
            tmp_path,
            "untracked.py",
            "def hello():\n    pass\n",
        )
        manifest = ForwardManifest(
            file_specs={
                "other.py": ForwardFileSpec(
                    file="other.py",
                    elements=[
                        ForwardElementSpec(
                            kind=ElementKind.FUNCTION,
                            name="missing",
                            signature=Signature(params=[]),
                        ),
                    ],
                )
            }
        )
        result = validate_disk_compliance(rel, str(tmp_path), manifest=manifest)
        assert result.contract_violations == []
        assert result.contract_compliance == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 9. Non-Python file validators (KZ-Q4)
# ---------------------------------------------------------------------------


def _write_file(tmp_path, rel_path, content):
    """Write a file under tmp_path and return the relative path string."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return rel_path


class TestRequirementsFileValidation:
    def test_valid_requirements(self, tmp_path):
        rel = _write_file(tmp_path, "requirements.in", "flask>=2.0\nrequests\npydantic~=2.0\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.contract_compliance == pytest.approx(1.0)
        assert result.semantic_issues == []

    def test_camelcase_function_names_flagged(self, tmp_path):
        """The PI-017 bug: requirements.in with function names instead of packages."""
        rel = _write_file(
            tmp_path,
            "requirements.in",
            "addToCart\nbrowseProduct\ncheckout\nfaker\nindex\nlocust\nsetCurrency\nviewCart\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        # 5 camelCase entries flagged: addToCart, browseProduct, setCurrency, viewCart
        # (checkout, faker, index, locust are valid lowercase names)
        assert result.contract_compliance < 1.0
        assert len(result.semantic_issues) >= 3  # at least addToCart, browseProduct, setCurrency, viewCart
        assert result.error is not None

    def test_comments_and_blanks_skipped(self, tmp_path):
        rel = _write_file(
            tmp_path,
            "requirements.in",
            "# A comment\n\nflask\n  # another\nrequests\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.contract_compliance == pytest.approx(1.0)

    def test_pip_flags_skipped(self, tmp_path):
        rel = _write_file(
            tmp_path,
            "requirements.in",
            "-e .\n--index-url https://pypi.org/simple\nflask\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.contract_compliance == pytest.approx(1.0)

    def test_requirements_txt_also_validated(self, tmp_path):
        rel = _write_file(tmp_path, "requirements.txt", "flask\nrequests\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.contract_compliance == pytest.approx(1.0)


class TestDockerfileValidation:
    def test_valid_dockerfile(self, tmp_path):
        rel = _write_file(
            tmp_path,
            "Dockerfile",
            "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nCMD [\"python\", \"app.py\"]\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True
        assert result.contract_compliance == pytest.approx(1.0)

    def test_missing_from_directive(self, tmp_path):
        rel = _write_file(
            tmp_path,
            "Dockerfile",
            "WORKDIR /app\nCOPY . .\nCMD [\"python\"]\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False
        assert result.contract_compliance == pytest.approx(0.0)
        assert "FROM" in result.error

    def test_no_entrypoint_warning(self, tmp_path):
        rel = _write_file(
            tmp_path,
            "Dockerfile",
            "FROM python:3.11\nWORKDIR /app\nCOPY . .\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True
        assert result.contract_compliance == pytest.approx(0.8)
        assert len(result.semantic_issues) == 1

    def test_multistage_dockerfile(self, tmp_path):
        rel = _write_file(
            tmp_path,
            "Dockerfile",
            (
                "FROM python:3.11 AS builder\n"
                "WORKDIR /build\n"
                "COPY . .\n"
                "FROM python:3.11-slim\n"
                "COPY --from=builder /build /app\n"
                "ENTRYPOINT [\"python\", \"app.py\"]\n"
            ),
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.contract_compliance == pytest.approx(1.0)


class TestYamlValidation:
    def test_valid_yaml(self, tmp_path):
        rel = _write_file(tmp_path, "config.yaml", "key: value\nlist:\n  - a\n  - b\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True

    def test_invalid_yaml(self, tmp_path):
        rel = _write_file(tmp_path, "config.yml", "key: [\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False
        assert "yaml_error" in result.error


class TestJsonValidation:
    def test_valid_json(self, tmp_path):
        rel = _write_file(tmp_path, "data.json", '{"key": "value"}\n')
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True

    def test_invalid_json(self, tmp_path):
        rel = _write_file(tmp_path, "data.json", '{"key": }\n')
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False
        assert "json_error" in result.error

    def test_tsconfig_jsonc_with_comments_is_valid(self, tmp_path):
        # tsconfig.json is JSONC — comments and trailing commas are legal and
        # must NOT be flagged as syntax errors (run-007 false-positive).
        content = (
            "{\n"
            '  "$schema": "https://json.schemastore.org/tsconfig",\n'
            "  /* Language & Environment */\n"
            '  "compilerOptions": {\n'
            '    "target": "ES2017",  // ECMAScript target\n'
            '    "jsx": "preserve",\n'
            "  },\n"  # trailing comma — legal in JSONC
            "}\n"
        )
        rel = _write_file(tmp_path, "tsconfig.json", content)
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True
        assert result.contract_compliance == pytest.approx(1.0)

    def test_tsconfig_with_real_error_still_fails(self, tmp_path):
        # JSONC tolerance must not mask a genuine structural error.
        rel = _write_file(tmp_path, "tsconfig.json", '{ "a": }\n')
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False
        assert "json_error" in result.error

    def test_plain_json_with_comment_still_fails(self, tmp_path):
        # A data .json file is NOT JSONC — comments remain invalid.
        rel = _write_file(tmp_path, "data.json", '{\n  // nope\n  "a": 1\n}\n')
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is False


class TestHtmlPassthrough:
    def test_html_keeps_defaults(self, tmp_path):
        """HTML files should keep default scores (no validator)."""
        rel = _write_file(tmp_path, "template.html", "<html><body>Hello</body></html>\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        assert result.ast_valid is True
        assert result.contract_compliance == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Proto stub verification (Run-055 F-2)
# ---------------------------------------------------------------------------


class TestProtoStubVerification:
    """Proto imports must match actual sibling _pb2.py files when siblings are known."""

    def test_valid_proto_with_sibling(self, tmp_path):
        """import demo_pb2 passes when demo_pb2.py exists as sibling."""
        rel = _write_py(tmp_path, "svc/server.py", "import demo_pb2\n")
        _write_py(tmp_path, "svc/demo_pb2.py", "# generated\n")
        result = validate_disk_compliance(
            rel, str(tmp_path),
            sibling_files=["svc/demo_pb2.py", "svc/server.py"],
        )
        proto_issues = [i for i in result.semantic_issues if "proto stub" in str(i.get("message", "")).lower()]
        assert len(proto_issues) == 0

    def test_hallucinated_proto_flagged(self, tmp_path):
        """import email_service_pb2 flagged when only demo_pb2.py exists."""
        rel = _write_py(
            tmp_path, "svc/client.py",
            "from email_service_pb2 import SendOrderConfirmationRequest\n",
        )
        _write_py(tmp_path, "svc/demo_pb2.py", "# generated\n")
        result = validate_disk_compliance(
            rel, str(tmp_path),
            sibling_files=["svc/demo_pb2.py", "svc/client.py"],
        )
        proto_issues = [
            i for i in result.semantic_issues
            if i.get("category") == "import_resolution"
            and "email_service_pb2" in str(i.get("message", ""))
        ]
        assert len(proto_issues) == 1
        assert proto_issues[0]["severity"] == "error"

    def test_proto_without_siblings_passes(self, tmp_path):
        """When sibling_files is None, proto regex alone is sufficient (backward compat)."""
        rel = _write_py(
            tmp_path, "svc/client.py",
            "from email_service_pb2 import X\n",
        )
        result = validate_disk_compliance(rel, str(tmp_path))
        # No proto verification without sibling context
        proto_issues = [i for i in result.semantic_issues if "proto stub" in str(i.get("message", "")).lower()]
        assert len(proto_issues) == 0


# ---------------------------------------------------------------------------
# Reverse prefix resolution (Run-055 F-3)
# ---------------------------------------------------------------------------


class TestReversePrefixResolution:
    """Import paths that are parent namespaces of requirements packages resolve."""

    def test_google_cloud_resolves(self, tmp_path):
        """from google.cloud import secretmanager resolves via google-cloud-secret-manager."""
        rel = _write_py(tmp_path, "svc/app.py", "from google.cloud import secretmanager\n")
        # Write requirements.in with google-cloud-secret-manager
        req = tmp_path / "svc" / "requirements.in"
        req.write_text("google-cloud-secret-manager\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        import_issues = [
            i for i in result.semantic_issues
            if i.get("category") == "import_resolution"
        ]
        assert len(import_issues) == 0

    def test_langchain_schema_resolves_via_alias(self, tmp_path):
        """from langchain.schema import HumanMessage resolves via package alias."""
        rel = _write_py(tmp_path, "svc/app.py", "from langchain.schema import HumanMessage\n")
        result = validate_disk_compliance(rel, str(tmp_path))
        import_issues = [
            i for i in result.semantic_issues
            if i.get("category") == "import_resolution"
            and "langchain" in str(i.get("symbol", ""))
        ]
        assert len(import_issues) == 0
