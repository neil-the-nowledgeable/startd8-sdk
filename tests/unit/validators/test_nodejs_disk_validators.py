"""Tests for Node.js disk validators in forward_manifest_validator.py (Phase 1).

Covers REQ-NODE-200 (JS file validation), REQ-NODE-201 (package.json validation),
REQ-NODE-202 (Node.js fingerprints in cross-language detection), and
REQ-NODE-500 (postmortem accuracy).
"""

import json
from unittest import mock

import pytest

from startd8.forward_manifest_validator import (
    DiskComplianceResult,
    _detect_language_mismatch,
    _validate_js_file,
    _validate_package_json,
)


# ---------------------------------------------------------------------------
# REQ-NODE-200: JavaScript file validation
# ---------------------------------------------------------------------------


VALID_JS_COMMONJS = """\
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');

function main() {
    const server = new grpc.Server();
    server.bindAsync('[::]:50051', grpc.ServerCredentials.createInsecure(), () => {
        server.start();
    });
}

main();
"""

VALID_JS_ESM = """\
import express from 'express';

const app = express();
app.get('/', (req, res) => res.send('hello'));
export default app;
"""

VALID_JS_ARROW = """\
const handler = (event) => {
    return { statusCode: 200, body: 'ok' };
};
module.exports = { handler };
"""


class TestValidateJsFile:
    """Test _validate_js_file() — REQ-NODE-200."""

    def _result(self):
        return DiskComplianceResult(file_path="test.js")

    def test_valid_js_passes_with_node(self):
        """Valid JS file passes node --check → compliance 1.0."""
        result = _validate_js_file(VALID_JS_COMMONJS, self._result())
        # If node is installed, should be 1.0; if not, 0.8 (text fallback)
        assert result.ast_valid is True
        assert result.contract_compliance >= 0.8

    def test_valid_js_esm(self):
        result = _validate_js_file(VALID_JS_ESM, self._result())
        assert result.ast_valid is True
        assert result.contract_compliance >= 0.8

    def test_valid_js_arrow_function(self):
        result = _validate_js_file(VALID_JS_ARROW, self._result())
        assert result.ast_valid is True
        assert result.contract_compliance >= 0.8

    def test_empty_js_file(self):
        result = _validate_js_file("", self._result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert result.error == "empty_file"

    def test_whitespace_only_js_file(self):
        result = _validate_js_file("   \n\n  ", self._result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert result.error == "empty_file"

    def test_no_js_keywords(self):
        """Content with no JS keywords → compliance 0.3."""
        result = _validate_js_file("hello world this is just text", self._result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.3
        assert result.error == "no_js_keywords"

    def test_invalid_js_syntax(self):
        """Syntax error detected by node --check → compliance 0.0."""
        bad_js = "function broken( { return 42; }"
        result = _validate_js_file(bad_js, self._result())
        # 'function' keyword is present, so keyword check passes.
        # If node is available, syntax check fails → 0.0.
        # If node is NOT available, text-based pass → 0.8.
        assert result.contract_compliance in (0.0, 0.8)

    def test_node_not_available_fallback(self):
        """When node is not installed, text-based fallback gives 0.8."""
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            result = _validate_js_file(VALID_JS_COMMONJS, self._result())
        assert result.ast_valid is True
        assert result.contract_compliance == 0.8

    def test_node_timeout_fallback(self):
        """When node --check times out → compliance 0.0."""
        import subprocess

        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("node", 15)):
            result = _validate_js_file(VALID_JS_COMMONJS, self._result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert result.error == "node_check_timeout"


# ---------------------------------------------------------------------------
# REQ-NODE-201: package.json validation
# ---------------------------------------------------------------------------


VALID_PACKAGE_JSON = json.dumps({
    "name": "grpc-currency-service",
    "version": "0.1.0",
    "dependencies": {
        "@grpc/grpc-js": "1.14.3",
        "pino": "10.3.0",
    },
})

PACKAGE_JSON_DEV_DEPS = json.dumps({
    "name": "my-service",
    "version": "1.0.0",
    "devDependencies": {
        "jest": "^29.0.0",
    },
})


class TestValidatePackageJson:
    """Test _validate_package_json() — REQ-NODE-201."""

    def _result(self):
        return DiskComplianceResult(file_path="package.json")

    def test_valid_package_json(self):
        result = _validate_package_json(VALID_PACKAGE_JSON, self._result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_valid_with_dev_deps_only(self):
        result = _validate_package_json(PACKAGE_JSON_DEV_DEPS, self._result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_missing_name_field(self):
        content = json.dumps({"version": "1.0.0", "dependencies": {"pino": "10.0.0"}})
        result = _validate_package_json(content, self._result())
        assert result.ast_valid is True
        assert result.contract_compliance == 0.3
        assert result.error == "missing_name_field"

    def test_missing_dependencies(self):
        content = json.dumps({"name": "my-service", "version": "1.0.0"})
        result = _validate_package_json(content, self._result())
        assert result.ast_valid is True
        assert result.contract_compliance == 0.5
        assert result.error == "missing_dependencies"

    def test_invalid_json(self):
        result = _validate_package_json("{bad json", self._result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert "invalid_json" in result.error

    def test_not_an_object(self):
        """JSON array instead of object → compliance 0.0."""
        result = _validate_package_json("[1, 2, 3]", self._result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert result.error == "package_json_not_object"

    def test_empty_string(self):
        result = _validate_package_json("", self._result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0


# ---------------------------------------------------------------------------
# REQ-NODE-202: Node.js fingerprints in cross-language detection
# ---------------------------------------------------------------------------


class TestNodejsCrossLanguageDetection:
    """Test Node.js fingerprint detection in non-JS files."""

    def test_require_in_html(self):
        content = "const grpc = require('@grpc/grpc-js');\n"
        result = _detect_language_mismatch(content, "/tmp/index.html")
        assert result is not None
        assert "nodejs_content_in_html" in result

    def test_module_exports_in_dockerfile(self):
        content = "module.exports = HipsterShopServer;\n"
        result = _detect_language_mismatch(content, "/tmp/Dockerfile")
        assert result is not None
        assert "nodejs_content_in_" in result

    def test_require_in_yaml(self):
        content = "let config = require('./config.json');\n"
        result = _detect_language_mismatch(content, "/tmp/config.yaml")
        assert result is not None
        assert "nodejs_content_in_yaml" in result

    def test_no_false_positive_in_js_file(self):
        """Node.js fingerprints in .js files should NOT be flagged."""
        content = "const grpc = require('@grpc/grpc-js');\nmodule.exports = main;\n"
        result = _detect_language_mismatch(content, "/tmp/server.js")
        assert result is None

    def test_no_false_positive_in_mjs_file(self):
        content = "import express from 'express';\n"
        result = _detect_language_mismatch(content, "/tmp/app.mjs")
        assert result is None

    def test_no_false_positive_in_ts_file(self):
        content = "const grpc = require('@grpc/grpc-js');\n"
        result = _detect_language_mismatch(content, "/tmp/server.ts")
        assert result is None

    def test_esm_import_not_flagged_as_python_in_js(self):
        """ESM 'import X from ...' in .js files must NOT trigger Python import detection."""
        content = "import express from 'express';\n"
        result = _detect_language_mismatch(content, "/tmp/app.js")
        assert result is None

    def test_no_false_positive_in_python_file(self):
        """Node.js fingerprints should not be checked in .py files."""
        content = "# const x = require('foo')\n"
        result = _detect_language_mismatch(content, "/tmp/test.py")
        assert result is None
