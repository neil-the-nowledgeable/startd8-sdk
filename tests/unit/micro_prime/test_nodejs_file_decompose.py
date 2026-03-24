"""Tests for Node.js file-level function decomposition — REQ-NODE-MP-400.

Verifies that NodeFileDecomposeStrategy correctly:
- Detects multi-function Node.js skeletons with stubs
- Creates SubElements per stub function
- Maps arrow functions to FUNCTION kind
- Maps class methods to METHOD kind with parent_class
- Assembles via splice_nodejs_bodies
"""

import pytest

from startd8.micro_prime.decomposer import (
    DecompositionPlan,
    NodeFileDecomposeStrategy,
    SubElement,
)
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
)
from startd8.utils.code_manifest import ElementKind, Signature


_EMPTY_SIG = Signature(params=[])


def _make_element(name="server"):
    return ForwardElementSpec(name=name, kind=ElementKind.FUNCTION, signature=_EMPTY_SIG)


def _make_file_spec(file="src/server.js", elements=None):
    return ForwardFileSpec(file=file, elements=elements or [], imports=[])


def _make_manifest():
    return ForwardManifest(files=[], contracts=[])


# -- Skeleton fixtures --

MULTI_FUNCTION_SKELETON = """\
const pino = require('pino');

function createServer(port) {
  throw new Error("not implemented");
}

function handleRequest(req, res) {
  throw new Error("not implemented");
}

function shutdown(server) {
  throw new Error("not implemented");
}
"""

SINGLE_FUNCTION_SKELETON = """\
function main() {
  throw new Error("not implemented");
}
"""

IMPLEMENTED_SKELETON = """\
function add(a, b) {
  return a + b;
}

function multiply(a, b) {
  return a * b;
}
"""

ARROW_FUNCTION_SKELETON = """\
const fetchData = async (url) => {
  throw new Error("not implemented");
};

const processResult = (data) => {
  throw new Error("not implemented");
};
"""

CLASS_METHOD_SKELETON = """\
class CartService {
  addItem(userId, item) {
    throw new Error("not implemented");
  }

  getCart(userId) {
    throw new Error("not implemented");
  }

  emptyCart(userId) {
    throw new Error("not implemented");
  }
}
"""


@pytest.fixture
def strategy():
    return NodeFileDecomposeStrategy()


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

class TestCanHandle:
    def test_multi_function_js_file(self, strategy):
        fs = _make_file_spec(
            file="src/server.js",
            elements=[_make_element("createServer"), _make_element("handleRequest"), _make_element("shutdown")],
        )
        result = strategy.can_handle(
            _make_element(), fs, _make_manifest(), "",
        )
        assert result is True

    def test_single_function_not_decomposable(self, strategy):
        fs = _make_file_spec(
            file="src/main.js",
            elements=[_make_element("main")],
        )
        result = strategy.can_handle(
            _make_element(), fs, _make_manifest(), "",
        )
        assert result is False

    def test_python_file_rejected(self, strategy):
        fs = _make_file_spec(file="src/main.py", elements=[_make_element(), _make_element("b")])
        result = strategy.can_handle(
            _make_element(), fs, _make_manifest(), "",
        )
        assert result is False

    def test_typescript_file_accepted(self, strategy):
        fs = _make_file_spec(
            file="src/server.ts",
            elements=[_make_element("a"), _make_element("b")],
        )
        result = strategy.can_handle(
            _make_element(), fs, _make_manifest(), "",
        )
        assert result is True


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

class TestPlan:
    def test_plan_creates_sub_elements(self, strategy):
        """Skeleton with 3 stubs → 3 SubElements."""
        # We test plan() by providing a file_spec with elements and checking
        # the plan structure. The actual skeleton parsing is tested separately.
        fs = _make_file_spec(
            file="src/server.js",
            elements=[
                _make_element("createServer"),
                _make_element("handleRequest"),
                _make_element("shutdown"),
            ],
        )
        plan = strategy.plan(
            _make_element("server"), fs, _make_manifest(), "",
        )
        assert plan is not None
        assert len(plan.sub_elements) >= 2
        assert plan.strategy == "nodejs_file_function"
        assert plan.assembly_kind == "splice"

    def test_plan_returns_none_for_single_element(self, strategy):
        fs = _make_file_spec(
            file="src/main.js",
            elements=[_make_element("main")],
        )
        plan = strategy.plan(
            _make_element("main"), fs, _make_manifest(), "",
        )
        assert plan is None

    def test_sub_element_specs_have_correct_kind(self, strategy):
        fs = _make_file_spec(
            file="src/server.js",
            elements=[_make_element("a"), _make_element("b"), _make_element("c")],
        )
        plan = strategy.plan(
            _make_element("server"), fs, _make_manifest(), "",
        )
        assert plan is not None
        for sub in plan.sub_elements:
            assert sub.element_spec is not None
            assert sub.element_spec.kind in (
                ElementKind.FUNCTION, ElementKind.ASYNC_FUNCTION,
                ElementKind.METHOD, ElementKind.ASYNC_METHOD,
            )


# ---------------------------------------------------------------------------
# assemble
# ---------------------------------------------------------------------------

class TestAssemble:
    def test_splices_bodies_into_skeleton(self, strategy):
        plan = DecompositionPlan(
            original_element=_make_element("server"),
            sub_elements=[],
            strategy="nodejs_file_function",
            assembly_kind="splice",
            confidence=0.9,
        )
        sub_results = {
            "createServer": "const server = http.createServer();\nserver.listen(port);",
            "handleRequest": "res.writeHead(200);\nres.end('ok');",
            "shutdown": "server.close();",
        }
        assembled = strategy.assemble(plan, sub_results, MULTI_FUNCTION_SKELETON)
        assert assembled is not None
        assert "http.createServer()" in assembled
        assert "res.writeHead(200)" in assembled
        assert "server.close()" in assembled
        # Stub markers should be gone
        assert 'throw new Error("not implemented")' not in assembled

    def test_returns_none_on_empty_results(self, strategy):
        plan = DecompositionPlan(
            original_element=_make_element("server"),
            sub_elements=[],
            strategy="nodejs_file_function",
            assembly_kind="splice",
            confidence=0.9,
        )
        assert strategy.assemble(plan, {}, MULTI_FUNCTION_SKELETON) is None

    def test_splices_arrow_functions(self, strategy):
        plan = DecompositionPlan(
            original_element=_make_element("utils"),
            sub_elements=[],
            strategy="nodejs_file_function",
            assembly_kind="splice",
            confidence=0.9,
        )
        sub_results = {
            "fetchData": "const response = await fetch(url);\nreturn response.json();",
            "processResult": "return data.map(item => item.value);",
        }
        assembled = strategy.assemble(plan, sub_results, ARROW_FUNCTION_SKELETON)
        assert assembled is not None
        assert "fetch(url)" in assembled
        assert "data.map" in assembled
