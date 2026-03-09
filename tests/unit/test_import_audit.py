"""Tests for L1+: deterministic import audit pass in code_extraction.py."""

from startd8.utils.code_extraction import audit_and_inject_imports


class TestAuditInjectsMissingStdlib:
    def test_os_path_join(self):
        code = "result = os.path.join('a', 'b')\n"
        patched, injected = audit_and_inject_imports(code)
        assert "import os" in patched
        assert any("os" in stmt for stmt in injected)

    def test_sys_module(self):
        code = "sys.exit(1)\n"
        patched, injected = audit_and_inject_imports(code)
        assert "import sys" in patched

    def test_json_module(self):
        code = "data = json.loads(text)\n"
        patched, injected = audit_and_inject_imports(code)
        assert "import json" in patched


class TestAuditInjectsMissingThirdParty:
    def test_grpc_with_alias_map(self):
        code = "server = grpc.server()\n"
        patched, injected = audit_and_inject_imports(
            code,
            available_packages=["grpcio==1.76.0"],
            package_alias_map={"grpcio": "grpc"},
        )
        assert "import grpc" in patched

    def test_flask_direct_match(self):
        code = "app = flask.Flask(__name__)\n"
        patched, injected = audit_and_inject_imports(
            code,
            available_packages=["flask>=3.0"],
        )
        assert "import flask" in patched


class TestAuditIdempotent:
    def test_running_twice_same_output(self):
        code = "result = os.path.join('a', 'b')\n"
        patched1, _ = audit_and_inject_imports(code)
        patched2, injected2 = audit_and_inject_imports(patched1)
        assert patched1 == patched2
        assert injected2 == []

    def test_already_imported_no_change(self):
        code = "import os\nresult = os.path.join('a', 'b')\n"
        patched, injected = audit_and_inject_imports(code)
        assert injected == []
        assert patched == code


class TestAuditPreservesExistingImports:
    def test_no_duplicate_os(self):
        code = "import os\nimport sys\nresult = os.path.join('a', 'b')\n"
        patched, injected = audit_and_inject_imports(code)
        assert injected == []
        assert patched.count("import os") == 1

    def test_from_import_not_duplicated(self):
        code = "from os.path import join\nresult = join('a', 'b')\n"
        patched, injected = audit_and_inject_imports(code)
        assert injected == []


class TestAuditUsesAliasMap:
    def test_pil_via_alias(self):
        code = "img = PIL.Image.open('test.png')\n"
        patched, injected = audit_and_inject_imports(
            code,
            available_packages=["pillow"],
            package_alias_map={"pillow": "PIL"},
        )
        assert "import PIL" in patched

    def test_yaml_via_alias(self):
        code = "data = yaml.safe_load(text)\n"
        patched, injected = audit_and_inject_imports(
            code,
            available_packages=["pyyaml"],
            package_alias_map={"pyyaml": "yaml"},
        )
        assert "import yaml" in patched


class TestAuditEdgeCases:
    def test_empty_code(self):
        patched, injected = audit_and_inject_imports("")
        assert patched == ""
        assert injected == []

    def test_syntax_error_fallback(self):
        code = "def broken(\n"
        patched, injected = audit_and_inject_imports(code)
        assert patched == code
        assert injected == []

    def test_no_packages_stdlib_only(self):
        code = "result = os.getcwd()\n"
        patched, injected = audit_and_inject_imports(code)
        assert "import os" in patched

    def test_builtin_names_not_imported(self):
        code = "x = len([1, 2, 3])\nprint(x)\n"
        patched, injected = audit_and_inject_imports(code)
        assert injected == []

    def test_defined_names_not_imported(self):
        code = "def foo():\n    return 42\nresult = foo()\n"
        patched, injected = audit_and_inject_imports(code)
        assert injected == []

    def test_class_names_not_imported(self):
        code = "class Foo:\n    pass\nx = Foo()\n"
        patched, injected = audit_and_inject_imports(code)
        assert injected == []

    def test_insertion_after_docstring(self):
        code = '"""Module docstring."""\n\nresult = os.getcwd()\n'
        patched, injected = audit_and_inject_imports(code)
        assert "import os" in patched
        # import should come after docstring
        lines = patched.splitlines()
        docstring_idx = next(i for i, l in enumerate(lines) if "docstring" in l)
        import_idx = next(i for i, l in enumerate(lines) if l == "import os")
        assert import_idx > docstring_idx

    def test_insertion_after_existing_imports(self):
        code = "import sys\n\nresult = os.getcwd()\n"
        patched, injected = audit_and_inject_imports(code)
        assert "import os" in patched
        lines = patched.splitlines()
        sys_idx = next(i for i, l in enumerate(lines) if l == "import sys")
        os_idx = next(i for i, l in enumerate(lines) if l == "import os")
        assert os_idx > sys_idx
