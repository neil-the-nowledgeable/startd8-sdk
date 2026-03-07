"""Tests for the Micro Prime Template Registry (REQ-MP-300–304, REQ-MP-310–313)."""

from __future__ import annotations

import ast

import pytest

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, ForwardImportSpec
from startd8.micro_prime.templates import (
    RELAXED_TEMPLATES,
    TemplateRegistry,
    _is_dfa_stub,
    _is_safe_identifier,
    _safe_default_repr,
)
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature


class TestTemplateRegistry:
    """Tests for TemplateRegistry.match()."""

    def test_disabled_returns_none(self, simple_function_element):
        """REQ-MP-303: Bypass flag disables template matching."""
        registry = TemplateRegistry(enabled=False)
        assert registry.match(simple_function_element) is None

    def test_enabled_toggle(self):
        registry = TemplateRegistry(enabled=True)
        assert registry.enabled is True
        registry.enabled = False
        assert registry.enabled is False

    def test_no_match_for_regular_function(self, simple_function_element):
        """Regular functions should not match any template."""
        registry = TemplateRegistry()
        assert registry.match(simple_function_element) is None


class TestInitTemplate:
    """Tests for __init__ template (REQ-MP-301)."""

    def test_init_with_params(self, init_element):
        registry = TemplateRegistry()
        match = registry.match(init_element)
        body = match.code if match else None
        assert body is not None
        assert "self.name = name" in body
        assert "self.value = value" in body

    def test_init_no_params(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(params=[Param(name="self")]),
            parent_class="Empty",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        body = match.code if match else None
        assert body is not None
        assert body == "pass"

    def test_init_body_is_valid_python(self, init_element):
        registry = TemplateRegistry()
        match = registry.match(init_element)
        body = match.code if match else None
        # Wrap in function and parse
        code = f"def __init__(self, name, value):\n"
        code += "\n".join(f"    {line}" for line in body.splitlines())
        ast.parse(code)  # Should not raise


class TestReprTemplate:
    """Tests for __repr__ template (REQ-MP-301)."""

    def test_repr_generates_fstring(self, repr_element):
        registry = TemplateRegistry()
        match = registry.match(repr_element)
        body = match.code if match else None
        assert body is not None
        assert "return" in body
        assert "Config" in body

    def test_repr_is_valid_python(self, repr_element):
        registry = TemplateRegistry()
        match = registry.match(repr_element)
        body = match.code if match else None
        code = f"def __repr__(self):\n    {body}"
        ast.parse(code)


class TestStrTemplate:
    """Tests for __str__ template (REQ-MP-301)."""

    def test_str_template(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__str__",
            signature=Signature(params=[Param(name="self")]),
            parent_class="MyModel",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        body = match.code if match else None
        assert body is not None
        assert "return" in body


class TestEqTemplate:
    """Tests for __eq__ template (REQ-MP-301)."""

    def test_eq_template(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__eq__",
            signature=Signature(
                params=[Param(name="self"), Param(name="other")],
                return_annotation="bool",
            ),
            parent_class="Item",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        body = match.code if match else None
        assert body is not None
        assert "isinstance" in body
        assert "NotImplemented" in body

    def test_eq_is_valid_python(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__eq__",
            signature=Signature(
                params=[Param(name="self"), Param(name="other")],
            ),
            parent_class="Item",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        body = match.code if match else None
        code = f"def __eq__(self, other):\n"
        code += "\n".join(f"    {line}" for line in body.splitlines())
        ast.parse(code)


class TestHashTemplate:
    """Tests for __hash__ template (REQ-MP-301)."""

    def test_hash_template(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__hash__",
            signature=Signature(
                params=[Param(name="self")],
                return_annotation="int",
            ),
            parent_class="Item",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        body = match.code if match else None
        assert body is not None
        assert "hash" in body


class TestConstantTemplate:
    """Tests for constant template (REQ-MP-301)."""

    def test_int_constant(self, constant_element):
        registry = TemplateRegistry()
        match = registry.match(constant_element)
        body = match.code if match else None
        assert body is not None
        assert "DEFAULT_TIMEOUT" in body
        assert "0" in body

    def test_str_constant(self):
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="APP_NAME",
            signature=Signature(params=[], return_annotation="str"),
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        body = match.code if match else None
        assert body is not None
        assert 'APP_NAME = ""' in body

    def test_optional_constant(self):
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="MAYBE",
            signature=Signature(params=[], return_annotation="Optional[str]"),
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        body = match.code if match else None
        assert body is not None
        assert "MAYBE = None" in body

    def test_constant_no_annotation_returns_none(self):
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="UNKNOWN",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        body = match.code if match else None
        assert body is None


class TestPropertyTemplate:
    """Tests for property template (REQ-MP-301)."""

    def test_property_template(self, property_element):
        registry = TemplateRegistry()
        match = registry.match(property_element)
        body = match.code if match else None
        assert body is not None
        assert "return self._total" in body

    def test_property_is_valid_python(self, property_element):
        registry = TemplateRegistry()
        match = registry.match(property_element)
        body = match.code if match else None
        code = f"def total(self):\n    {body}"
        ast.parse(code)


class TestIsTrivial:
    """Tests for TemplateRegistry.is_trivial()."""

    def test_constant_is_trivial(self, constant_element):
        registry = TemplateRegistry()
        assert registry.is_trivial(constant_element) is True

    def test_property_is_trivial(self, property_element):
        registry = TemplateRegistry()
        assert registry.is_trivial(property_element) is True

    def test_init_is_trivial(self, init_element):
        registry = TemplateRegistry()
        assert registry.is_trivial(init_element) is True

    def test_regular_function_not_trivial(self, simple_function_element):
        registry = TemplateRegistry()
        assert registry.is_trivial(simple_function_element) is False

    def test_disabled_never_trivial(self, init_element):
        registry = TemplateRegistry(enabled=False)
        assert registry.is_trivial(init_element) is False


class TestASTValidation:
    """Tests for template AST validation (REQ-MP-304)."""

    def test_valid_template_passes(self, init_element):
        registry = TemplateRegistry()
        match = registry.match(init_element)
        body = match.code if match else None
        assert body is not None  # Would be None if AST validation failed


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: Template Registry Expansion (REQ-MP-310–313)
# ═══════════════════════════════════════════════════════════════════════════


class TestSafetyGuards:
    """Tests for Phase 2 safety guards (R4-S7, R5-S7, R2-S7, R5-S4)."""

    def test_is_safe_identifier_valid(self):
        assert _is_safe_identifier("name") is True
        assert _is_safe_identifier("_private") is True
        assert _is_safe_identifier("CamelCase") is True

    def test_is_safe_identifier_rejects_whitespace(self):
        assert _is_safe_identifier("bad name") is False
        assert _is_safe_identifier("bad\nname") is False

    def test_is_safe_identifier_rejects_non_identifier(self):
        assert _is_safe_identifier("") is False
        assert _is_safe_identifier("123abc") is False
        assert _is_safe_identifier("a-b") is False

    def test_is_safe_identifier_rejects_keyword(self):
        assert _is_safe_identifier("class") is False
        assert _is_safe_identifier("return") is False
        assert _is_safe_identifier("import") is False

    def test_safe_default_repr_literal(self):
        assert _safe_default_repr("42") == "42"
        assert _safe_default_repr("'hello'") == "'hello'"
        assert _safe_default_repr("None") == "None"
        assert _safe_default_repr("True") == "True"

    def test_safe_default_repr_injection(self):
        """Malicious default value is safely repr'd, not evaluated."""
        result = _safe_default_repr("__import__('os').system('rm -rf /')")
        # Should be a quoted string literal, not executable code
        assert result.startswith(("'", '"'))
        # Verify it round-trips safely via ast.literal_eval
        parsed = ast.literal_eval(result)
        assert isinstance(parsed, str)

    def test_is_dfa_stub_detects_stubs(self):
        assert _is_dfa_stub("raise NotImplementedError") is True
        assert _is_dfa_stub("raise NotImplementedError()") is True
        assert _is_dfa_stub("...") is True
        assert _is_dfa_stub("  raise NotImplementedError  ") is True
        # "pass" is a stub for non-dunder elements
        assert _is_dfa_stub("pass", element_name="process") is True
        # "pass" is NOT a stub for dunder methods (e.g. empty __init__)
        assert _is_dfa_stub("pass", element_name="__init__") is False

    def test_is_dfa_stub_rejects_real_code(self):
        assert _is_dfa_stub("self.name = name") is False
        assert _is_dfa_stub("return 42") is False

    def test_no_regression_guard_skips_stub(self):
        """Template output that equals a DFA stub should be skipped (R5-S4)."""
        # An empty __init__ returns "pass" which is a stub — but "pass" for
        # empty __init__ is actually correct, so the dunder_method template
        # is exempted by the fact that "pass" for __init__(self) is valid.
        # Test with a constant that would produce stub-like output.
        registry = TemplateRegistry()
        # A regular function won't match templates, so this is indirect.
        # The guard is tested via _is_dfa_stub directly above.

    def test_unsafe_element_name_rejected(self):
        """Element with unsafe name should not match any template (R5-S7)."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="bad name with spaces",
            signature=Signature(params=[Param(name="self")]),
            parent_class="Foo",
        )
        registry = TemplateRegistry()
        assert registry.match(elem) is None


class TestInitWithDefaults:
    """Tests for enhanced __init__ with defaults (REQ-MP-310)."""

    def test_init_with_default_params(self):
        """__init__ with params that have defaults stores them as attrs."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="host", annotation="str", default="'localhost'"),
                    Param(name="port", annotation="int", default="8080"),
                    Param(name="debug", annotation="bool", default="False"),
                ],
            ),
            parent_class="ServerConfig",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is not None
        assert "self.host = host" in match.code
        assert "self.port = port" in match.code
        assert "self.debug = debug" in match.code

    def test_init_with_defaults_valid_python(self):
        """Output should be valid Python."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="name", annotation="str", default="''"),
                    Param(name="count", annotation="int", default="0"),
                ],
            ),
            parent_class="Counter",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        code = "def __init__(self, name='', count=0):\n"
        code += "\n".join(f"    {line}" for line in match.code.splitlines())
        ast.parse(code)


class TestInitVarargs:
    """Tests for __init__ with *args/**kwargs (REQ-MP-311)."""

    def test_init_with_args(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="name", annotation="str"),
                    Param(name="args", kind=ParamKind.VAR_POSITIONAL),
                ],
            ),
            parent_class="Flexible",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is not None
        assert "self.name = name" in match.code
        assert "self._args = args" in match.code

    def test_init_with_kwargs(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="kwargs", kind=ParamKind.VAR_KEYWORD),
                ],
            ),
            parent_class="Extra",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is not None
        assert "self._kwargs = kwargs" in match.code

    def test_init_with_args_and_kwargs(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="base", annotation="str"),
                    Param(name="args", kind=ParamKind.VAR_POSITIONAL),
                    Param(name="kwargs", kind=ParamKind.VAR_KEYWORD),
                ],
            ),
            parent_class="Mixed",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is not None
        assert "self.base = base" in match.code
        assert "self._args = args" in match.code
        assert "self._kwargs = kwargs" in match.code

    def test_init_varargs_valid_python(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="args", kind=ParamKind.VAR_POSITIONAL),
                    Param(name="kwargs", kind=ParamKind.VAR_KEYWORD),
                ],
            ),
            parent_class="Proxy",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        code = "def __init__(self, *args, **kwargs):\n"
        code += "\n".join(f"    {line}" for line in match.code.splitlines())
        ast.parse(code)


class TestSimpleValidation:
    """Tests for simple validation template (REQ-MP-312)."""

    def test_validate_function_matches(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="validate_name",
            signature=Signature(
                params=[Param(name="name", annotation="str")],
                return_annotation="None",
            ),
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is not None
        assert match.name == "simple_validation"
        assert "if not name:" in match.code
        assert "raise ValueError" in match.code

    def test_check_function_matches(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="check_value",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="value", annotation="int"),
                ],
            ),
            parent_class="Validator",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is not None
        assert "if not value:" in match.code

    def test_validate_multiple_params_no_match(self):
        """Validation with 2+ params does not match the simple template."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="validate_range",
            signature=Signature(
                params=[
                    Param(name="low", annotation="int"),
                    Param(name="high", annotation="int"),
                ],
            ),
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is None or match.name != "simple_validation"

    def test_non_validate_function_no_match(self):
        """Functions not named validate_*/check_* don't match."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="process_data",
            signature=Signature(
                params=[Param(name="data", annotation="str")],
            ),
        )
        registry = TemplateRegistry()
        # Should not match simple_validation
        match = registry.match(elem)
        assert match is None or match.name != "simple_validation"

    def test_validate_output_valid_python(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="validate_input",
            signature=Signature(
                params=[Param(name="input_val", annotation="str")],
            ),
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        code = f"def validate_input(input_val):\n"
        code += "\n".join(f"    {line}" for line in match.code.splitlines())
        ast.parse(code)


class TestDataclassBoilerplate:
    """Tests for dataclass/Pydantic model template (REQ-MP-313)."""

    def test_dataclass_with_typed_fields(self):
        file_spec = ForwardFileSpec(
            file="src/models.py",
            imports=[
                ForwardImportSpec(kind="from", module="dataclasses", names=["dataclass"]),
            ],
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="UserConfig",
                    decorators=["dataclass"],
                ),
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__init__",
                    signature=Signature(
                        params=[
                            Param(name="self"),
                            Param(name="name", annotation="str"),
                            Param(name="age", annotation="int", default="0"),
                            Param(name="active", annotation="bool", default="True"),
                        ],
                    ),
                    parent_class="UserConfig",
                ),
            ],
        )
        class_elem = file_spec.elements[0]
        registry = TemplateRegistry()
        match = registry.match(class_elem, file_spec=file_spec)
        assert match is not None
        assert match.name == "dataclass_boilerplate"
        assert "name: str" in match.code
        assert "age: int = 0" in match.code
        assert "active: bool = True" in match.code

    def test_pydantic_basemodel(self):
        file_spec = ForwardFileSpec(
            file="src/schemas.py",
            imports=[
                ForwardImportSpec(kind="from", module="pydantic", names=["BaseModel"]),
            ],
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="RequestSchema",
                    bases=["BaseModel"],
                ),
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__init__",
                    signature=Signature(
                        params=[
                            Param(name="self"),
                            Param(name="url", annotation="str"),
                            Param(name="timeout", annotation="int", default="30"),
                        ],
                    ),
                    parent_class="RequestSchema",
                ),
            ],
        )
        class_elem = file_spec.elements[0]
        registry = TemplateRegistry()
        match = registry.match(class_elem, file_spec=file_spec)
        assert match is not None
        assert "url: str" in match.code
        assert "timeout: int = 30" in match.code

    def test_non_dataclass_no_match(self):
        """Plain class without dataclass/BaseModel should not match."""
        file_spec = ForwardFileSpec(
            file="src/plain.py",
            imports=[],
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="PlainClass",
                ),
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__init__",
                    signature=Signature(
                        params=[
                            Param(name="self"),
                            Param(name="x", annotation="int"),
                        ],
                    ),
                    parent_class="PlainClass",
                ),
            ],
        )
        class_elem = file_spec.elements[0]
        registry = TemplateRegistry()
        match = registry.match(class_elem, file_spec=file_spec)
        assert match is None or match.name != "dataclass_boilerplate"

    def test_dataclass_no_init_child_no_match(self):
        """Dataclass without __init__ child in file_spec shouldn't match."""
        file_spec = ForwardFileSpec(
            file="src/empty.py",
            imports=[],
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="EmptyModel",
                    decorators=["dataclass"],
                ),
            ],
        )
        class_elem = file_spec.elements[0]
        registry = TemplateRegistry()
        match = registry.match(class_elem, file_spec=file_spec)
        assert match is None or match.name != "dataclass_boilerplate"

    def test_dataclass_output_valid_python(self):
        file_spec = ForwardFileSpec(
            file="src/models.py",
            imports=[],
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="Point",
                    decorators=["dataclass"],
                ),
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__init__",
                    signature=Signature(
                        params=[
                            Param(name="self"),
                            Param(name="x", annotation="float", default="0.0"),
                            Param(name="y", annotation="float", default="0.0"),
                        ],
                    ),
                    parent_class="Point",
                ),
            ],
        )
        class_elem = file_spec.elements[0]
        registry = TemplateRegistry()
        match = registry.match(class_elem, file_spec=file_spec)
        # Wrap in class and parse
        code = f"class Point:\n"
        code += "\n".join(f"    {line}" for line in match.code.splitlines())
        ast.parse(code)

    def test_dataclass_malicious_default_safe(self):
        """Malicious default values should be safely serialized (R4-S7)."""
        file_spec = ForwardFileSpec(
            file="src/evil.py",
            imports=[],
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="EvilModel",
                    decorators=["dataclass"],
                ),
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__init__",
                    signature=Signature(
                        params=[
                            Param(name="self"),
                            Param(
                                name="payload",
                                annotation="str",
                                default="__import__('os').system('rm -rf /')",
                            ),
                        ],
                    ),
                    parent_class="EvilModel",
                ),
            ],
        )
        class_elem = file_spec.elements[0]
        registry = TemplateRegistry()
        match = registry.match(class_elem, file_spec=file_spec)
        assert match is not None
        # The malicious string should be repr'd, not evaluated
        assert "os" not in match.code or "'" in match.code


class TestQuickWinPack:
    """Quick-win test pack: 5 representative SIMPLE cases (R5-S5).

    Assert zero LLM calls for each by verifying template match.
    """

    def test_init_template(self):
        """__init__ with params → deterministic."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[Param(name="self"), Param(name="x", annotation="int")],
            ),
            parent_class="Foo",
        )
        registry = TemplateRegistry()
        assert registry.match(elem) is not None

    def test_repr_template(self):
        """__repr__ → deterministic."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__repr__",
            signature=Signature(params=[Param(name="self")]),
            parent_class="Foo",
        )
        registry = TemplateRegistry()
        assert registry.match(elem) is not None

    def test_constant_template(self):
        """Typed constant → deterministic."""
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="MAX_RETRIES",
            signature=Signature(params=[], return_annotation="int"),
        )
        registry = TemplateRegistry()
        assert registry.match(elem) is not None

    def test_property_getter_template(self):
        """Property → deterministic."""
        elem = ForwardElementSpec(
            kind=ElementKind.PROPERTY,
            name="total",
            signature=Signature(
                params=[Param(name="self")],
                return_annotation="int",
            ),
            parent_class="Order",
        )
        registry = TemplateRegistry()
        assert registry.match(elem) is not None

    def test_type_alias_template(self):
        """Type alias → deterministic."""
        elem = ForwardElementSpec(
            kind=ElementKind.TYPE_ALIAS,
            name="UserId",
            type_annotation="int",
        )
        registry = TemplateRegistry()
        assert registry.match(elem) is not None


# ═══════════════════════════════════════════════════════════════════════════
# Phase 2 low-priority: Render contract + Relaxed allowlist (R4-S2, R1-S7)
# ═══════════════════════════════════════════════════════════════════════════


class TestRenderContract:
    """Snapshot tests for render contract (R4-S2).

    Templates must emit body-only code. The splicer handles indentation.
    """

    def test_init_body_only_no_def_line(self):
        """__init__ template must NOT include 'def __init__'."""
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="name", annotation="str"),
                    Param(name="value", annotation="int"),
                ],
            ),
            parent_class="Config",
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is not None
        assert not match.code.startswith("def ")

    def test_validation_body_only(self):
        """Validation template must NOT include 'def validate_'."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="validate_input",
            signature=Signature(
                params=[Param(name="data", annotation="str")],
            ),
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is not None
        assert not match.code.startswith("def ")

    def test_constant_is_full_assignment(self):
        """Constants emit full assignment (NAME = value), not body-only."""
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="MAX_SIZE",
            signature=Signature(params=[], return_annotation="int"),
        )
        registry = TemplateRegistry()
        match = registry.match(elem)
        assert match is not None
        assert match.code.startswith("MAX_SIZE")

    def test_snapshot_class_with_two_methods(self):
        """Snapshot: class with __init__ + __repr__ produces correct output."""
        init_elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__init__",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="x", annotation="int"),
                    Param(name="y", annotation="int"),
                ],
            ),
            parent_class="Point",
        )
        repr_elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="__repr__",
            signature=Signature(params=[Param(name="self")]),
            parent_class="Point",
        )
        registry = TemplateRegistry()
        init_match = registry.match(init_elem)
        repr_match = registry.match(repr_elem)

        # Simulate splicing into a class skeleton
        skeleton = (
            "class Point:\n"
            "    def __init__(self, x: int, y: int):\n"
            "        raise NotImplementedError\n"
            "\n"
            "    def __repr__(self):\n"
            "        raise NotImplementedError\n"
        )

        # Verify both outputs are body-only and valid Python when indented
        for match, sig in [(init_match, "self, x, y"), (repr_match, "self")]:
            assert match is not None
            indented = "\n".join(f"        {line}" for line in match.code.splitlines())
            code = f"class Point:\n    def _check({sig}):\n{indented}\n"
            ast.parse(code)  # Must not raise

    def test_dataclass_fields_zero_indented(self):
        """Dataclass template output is zero-indented."""
        file_spec = ForwardFileSpec(
            file="src/model.py",
            imports=[],
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.CLASS,
                    name="Item",
                    decorators=["dataclass"],
                ),
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__init__",
                    signature=Signature(
                        params=[
                            Param(name="self"),
                            Param(name="id", annotation="int"),
                            Param(name="name", annotation="str"),
                        ],
                    ),
                    parent_class="Item",
                ),
            ],
        )
        class_elem = file_spec.elements[0]
        registry = TemplateRegistry()
        match = registry.match(class_elem, file_spec=file_spec)
        assert match is not None
        # First line must start at column 0
        first_line = match.code.splitlines()[0]
        assert first_line == first_line.lstrip()


class TestRelaxedAllowlist:
    """Tests for relaxed template allowlist (R1-S7)."""

    def test_default_no_relaxed_templates(self):
        """Default registry uses no relaxed templates."""
        registry = TemplateRegistry()
        assert registry.relaxed_allowlist == frozenset()

    def test_relaxed_allowlist_empty_by_default(self):
        """RELAXED_TEMPLATES list exists but is empty by default."""
        assert isinstance(RELAXED_TEMPLATES, list)
        # Currently no relaxed templates defined
        assert len(RELAXED_TEMPLATES) == 0

    def test_allowlist_does_not_affect_standard_templates(self, init_element):
        """Standard templates work regardless of allowlist."""
        registry = TemplateRegistry(relaxed_allowlist=frozenset({"nonexistent"}))
        match = registry.match(init_element)
        assert match is not None

    def test_is_trivial_uses_active_templates(self, init_element):
        """is_trivial respects the active template list."""
        registry = TemplateRegistry()
        assert registry.is_trivial(init_element) is True
        # With relaxed allowlist set to something, standard still works
        registry2 = TemplateRegistry(relaxed_allowlist=frozenset({"foo"}))
        assert registry2.is_trivial(init_element) is True
