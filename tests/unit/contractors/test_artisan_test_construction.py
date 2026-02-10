"""
Unit Tests for Test Construction (Artisan)

Tests suite generation, stub creation, pytest collection compatibility,
parametrized test generation. Target: >85% coverage of construction logic.

Production-ready implementation covering:
- TestSuiteGenerator: generates test suites from source module metadata
- TestStubGenerator: generates test stubs in multiple styles (minimal/standard/comprehensive)
- PytestCollector: validates generated tests follow pytest collection conventions
- ParametrizedTestBuilder: builds parametrized test configurations
- Data models: SourceModule, SourceClass, SourceFunction, TestSuite, etc.

All tests are self-contained in this single file with no external dependencies
beyond pytest.
"""

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

import pytest


# =============================================================================
# ENUMS
# =============================================================================

class MethodType(Enum):
    """Type of method in source code."""
    INSTANCE = auto()
    CLASS_METHOD = auto()
    STATIC_METHOD = auto()
    PROPERTY = auto()


class Visibility(Enum):
    """Visibility of a source code element."""
    PUBLIC = auto()
    PROTECTED = auto()   # single underscore prefix
    PRIVATE = auto()     # double underscore prefix
    DUNDER = auto()      # __name__ pattern


class StubStyle(Enum):
    """Style of generated test stub."""
    MINIMAL = auto()        # just assert True placeholder
    STANDARD = auto()       # with arrange/act/assert comments
    COMPREHENSIVE = auto()  # with docstring, type hints, multiple asserts


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _sanitize_test_name(name: str) -> str:
    """
    Sanitize a name to be a valid Python test identifier.

    Replaces non-alphanumeric characters with underscores, removes leading
    digits, collapses multiple underscores, strips trailing underscores,
    and truncates to 100 characters. Returns 'unnamed' for empty results.
    """
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    sanitized = re.sub(r'^[0-9]+', '', sanitized)
    sanitized = re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.strip('_')
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    return sanitized if sanitized else 'unnamed'


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class SourceParameter:
    """Represents a parameter of a source function."""
    name: str
    annotation: Optional[str] = None
    default: Optional[str] = None
    is_args: bool = False
    is_kwargs: bool = False


@dataclass
class SourceFunction:
    """Represents a source function to generate tests for."""
    name: str
    parameters: List[SourceParameter] = field(default_factory=list)
    return_annotation: Optional[str] = None
    docstring: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    is_async: bool = False

    @property
    def visibility(self) -> Visibility:
        """Determine the visibility level based on naming convention."""
        if self.name.startswith('__') and self.name.endswith('__'):
            return Visibility.DUNDER
        if self.name.startswith('__'):
            return Visibility.PRIVATE
        if self.name.startswith('_'):
            return Visibility.PROTECTED
        return Visibility.PUBLIC

    @property
    def method_type(self) -> MethodType:
        """Determine the method type based on decorators."""
        if 'staticmethod' in self.decorators:
            return MethodType.STATIC_METHOD
        if 'classmethod' in self.decorators:
            return MethodType.CLASS_METHOD
        if 'property' in self.decorators:
            return MethodType.PROPERTY
        return MethodType.INSTANCE


@dataclass
class SourceClass:
    """Represents a source class to generate tests for."""
    name: str
    methods: List[SourceFunction] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    is_abstract: bool = False


@dataclass
class SourceModule:
    """Represents a source module to generate tests for."""
    name: str
    functions: List[SourceFunction] = field(default_factory=list)
    classes: List[SourceClass] = field(default_factory=list)
    docstring: Optional[str] = None


@dataclass
class TestCase:
    """Represents a single generated test case."""
    name: str
    body: str
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    parameters: List[SourceParameter] = field(default_factory=list)


@dataclass
class TestClass:
    """Represents a generated test class."""
    name: str
    test_cases: List[TestCase] = field(default_factory=list)
    setup_method: Optional[str] = None
    teardown_method: Optional[str] = None


@dataclass
class TestSuite:
    """Represents a generated test suite (file-level)."""
    module_name: str
    test_classes: List[TestClass] = field(default_factory=list)
    standalone_tests: List[TestCase] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    fixtures: List[str] = field(default_factory=list)

    @property
    def total_test_count(self) -> int:
        """Total number of test cases across standalone tests and test classes."""
        count = len(self.standalone_tests)
        for test_cls in self.test_classes:
            count += len(test_cls.test_cases)
        return count


@dataclass
class TestStub:
    """Represents a generated test stub."""
    function_name: str
    body: str
    style: StubStyle = StubStyle.STANDARD
    source_function: Optional[str] = None


@dataclass
class ParametrizedConfig:
    """Configuration for a parametrized test."""
    param_names: List[str]
    param_values: List[Tuple]
    ids: Optional[List[str]] = None
    indirect: bool = False

    @property
    def decorator_string(self) -> str:
        """Generate the @pytest.mark.parametrize decorator string."""
        names = ", ".join(self.param_names)
        values = repr(self.param_values)
        parts = [f'@pytest.mark.parametrize("{names}", {values}']
        if self.ids:
            parts[0] += f", ids={repr(self.ids)}"
        if self.indirect:
            parts[0] += ", indirect=True"
        parts[0] += ")"
        return parts[0]

    def validate(self) -> List[str]:
        """Validate the configuration, returning a list of error messages."""
        errors = []
        if not self.param_names:
            errors.append("Parameter names cannot be empty")
        if not self.param_values:
            errors.append("Parameter values cannot be empty")
        for idx, vals in enumerate(self.param_values):
            if len(vals) != len(self.param_names):
                errors.append(
                    f"Value set {idx} has {len(vals)} values but "
                    f"{len(self.param_names)} parameters defined"
                )
        if self.ids and len(self.ids) != len(self.param_values):
            errors.append(
                f"Number of IDs ({len(self.ids)}) doesn't match "
                f"number of value sets ({len(self.param_values)})"
            )
        return errors


# =============================================================================
# CORE COMPONENTS
# =============================================================================

class TestSuiteGenerator:
    """
    Generates test suites from source module metadata.

    Supports configurable inclusion of private/dunder methods, multiple
    stub styles, and optional fixture generation.
    """

    def __init__(
        self,
        include_private: bool = False,
        include_dunder: bool = False,
        stub_style: StubStyle = StubStyle.STANDARD,
        generate_fixtures: bool = True,
    ):
        self.include_private = include_private
        self.include_dunder = include_dunder
        self.stub_style = stub_style
        self.generate_fixtures = generate_fixtures
        self._stub_generator = TestStubGenerator(style=stub_style)

    def generate(self, module: SourceModule) -> TestSuite:
        """Generate a complete test suite from a source module."""
        if not isinstance(module, SourceModule):
            raise TypeError(f"Expected SourceModule, got {type(module).__name__}")

        suite = TestSuite(
            module_name=f"test_{module.name}",
            imports=[f"import {module.name}", "import pytest"],
        )

        # Generate standalone test functions for module-level functions
        for func in module.functions:
            if self._should_include(func):
                test_case = self._generate_test_case(func)
                suite.standalone_tests.append(test_case)

        # Generate test classes for source classes
        for cls in module.classes:
            test_class = self._generate_test_class(cls)
            if test_class.test_cases:
                suite.test_classes.append(test_class)

        # Generate fixtures if enabled
        if self.generate_fixtures and module.classes:
            for cls in module.classes:
                fixture_name = _sanitize_test_name(cls.name).lower()
                suite.fixtures.append(fixture_name)

        return suite

    def _should_include(self, func: SourceFunction) -> bool:
        """Determine if a function should have tests generated based on visibility."""
        vis = func.visibility
        if vis == Visibility.PRIVATE and not self.include_private:
            return False
        if vis == Visibility.DUNDER and not self.include_dunder:
            return False
        return True

    def _generate_test_case(self, func: SourceFunction) -> TestCase:
        """Generate a test case for a single function."""
        sanitized = _sanitize_test_name(func.name)
        test_name = f"test_{sanitized}"
        stub = self._stub_generator.generate(func)
        return TestCase(
            name=test_name,
            body=stub.body,
            docstring=f"Test for {func.name}.",
        )

    def _generate_test_class(self, cls: SourceClass) -> TestClass:
        """Generate a test class for a source class."""
        sanitized = _sanitize_test_name(cls.name)
        test_class_name = f"Test{sanitized}"

        test_cases = []
        for method in cls.methods:
            if self._should_include(method):
                tc = self._generate_test_case(method)
                test_cases.append(tc)

        setup = None
        teardown = None
        if test_cases:
            setup = "def setup_method(self):\n    pass"
            teardown = "def teardown_method(self):\n    pass"

        return TestClass(
            name=test_class_name,
            test_cases=test_cases,
            setup_method=setup,
            teardown_method=teardown,
        )


class TestStubGenerator:
    """
    Generates test stubs for source functions.

    Supports three styles: MINIMAL, STANDARD, and COMPREHENSIVE.
    """

    def __init__(self, style: StubStyle = StubStyle.STANDARD):
        self.style = style

    def generate(self, func: SourceFunction) -> TestStub:
        """Generate a test stub for the given function."""
        if not isinstance(func, SourceFunction):
            raise TypeError(f"Expected SourceFunction, got {type(func).__name__}")

        if self.style == StubStyle.MINIMAL:
            body = self._minimal_body(func)
        elif self.style == StubStyle.STANDARD:
            body = self._standard_body(func)
        elif self.style == StubStyle.COMPREHENSIVE:
            body = self._comprehensive_body(func)
        else:
            raise ValueError(f"Unknown stub style: {self.style}")

        return TestStub(
            function_name=f"test_{_sanitize_test_name(func.name)}",
            body=body,
            style=self.style,
            source_function=func.name,
        )

    def _minimal_body(self, func: SourceFunction) -> str:
        """Generate a minimal test body with just a placeholder assertion."""
        return "assert True  # TODO: implement test"

    def _standard_body(self, func: SourceFunction) -> str:
        """Generate a standard test body with arrange/act/assert sections."""
        lines = [
            "# Arrange",
            "# TODO: set up test data",
            "",
            "# Act",
            f"# result = {func.name}()",
            "",
            "# Assert",
            "assert True  # TODO: add meaningful assertions",
        ]
        return "\n".join(lines)

    def _comprehensive_body(self, func: SourceFunction) -> str:
        """Generate a comprehensive test body with parameter setup and docstring."""
        lines = [
            f'"""Test that {func.name} behaves correctly."""',
            "# Arrange",
        ]

        for param in func.parameters:
            if param.name == 'self':
                continue
            if param.is_args:
                lines.append("args = ()  # TODO: provide *args")
            elif param.is_kwargs:
                lines.append("kwargs = {}  # TODO: provide **kwargs")
            else:
                default = param.default if param.default else "None"
                lines.append(f"{param.name} = {default}  # TODO: set value")

        lines.extend([
            "",
            "# Act",
            f"# result = {func.name}(...)",
            "",
            "# Assert",
            "# assert result is not None",
            "assert True  # TODO: replace with real assertions",
        ])
        return "\n".join(lines)

    def generate_batch(self, functions: List[SourceFunction]) -> List[TestStub]:
        """Generate stubs for multiple functions."""
        return [self.generate(fn) for fn in functions]


class ParametrizedTestBuilder:
    """
    Builds parametrized test configurations.

    Supports fluent API for chaining, validation, and convenience
    creation from example dictionaries.
    """

    def __init__(self):
        self._configs: List[ParametrizedConfig] = []

    def add_config(self, config: ParametrizedConfig) -> 'ParametrizedTestBuilder':
        """Add a parametrize configuration (validates first)."""
        errors = config.validate()
        if errors:
            raise ValueError(f"Invalid config: {'; '.join(errors)}")
        self._configs.append(config)
        return self

    def build(self) -> List[ParametrizedConfig]:
        """Return all accumulated configurations."""
        return list(self._configs)

    def build_decorator_strings(self) -> List[str]:
        """Return pytest.mark.parametrize decorator strings for all configs."""
        return [cfg.decorator_string for cfg in self._configs]

    def clear(self) -> 'ParametrizedTestBuilder':
        """Clear all configurations."""
        self._configs.clear()
        return self

    @staticmethod
    def from_examples(
        func: SourceFunction,
        examples: List[Dict[str, Any]],
        expected_key: str = "expected",
    ) -> ParametrizedConfig:
        """
        Create a ParametrizedConfig from example dictionaries.

        Each dictionary should have the same keys, including the expected_key.
        """
        if not examples:
            raise ValueError("Examples list cannot be empty")

        first = examples[0]
        if expected_key not in first:
            raise KeyError(f"Expected key '{expected_key}' not found in examples")

        param_names = [key for key in first.keys()]
        param_values = [tuple(ex[key] for key in param_names) for ex in examples]

        return ParametrizedConfig(
            param_names=param_names,
            param_values=param_values,
        )


class PytestCollector:
    """
    Validates that generated tests follow pytest collection rules.

    Checks file names, function names, and class names against pytest's
    default discovery patterns.
    """

    TEST_FILE_PATTERN = re.compile(r'^test_.*\.py$|^.*_test\.py$')
    TEST_FUNC_PATTERN = re.compile(r'^test_[a-zA-Z0-9_]+$')
    TEST_CLASS_PATTERN = re.compile(r'^Test[A-Z][a-zA-Z0-9_]*$')

    @classmethod
    def is_valid_test_file_name(cls, name: str) -> bool:
        """Check if a filename follows pytest naming conventions."""
        return bool(cls.TEST_FILE_PATTERN.match(name))

    @classmethod
    def is_valid_test_function_name(cls, name: str) -> bool:
        """Check if a function name follows pytest naming conventions."""
        return bool(cls.TEST_FUNC_PATTERN.match(name))

    @classmethod
    def is_valid_test_class_name(cls, name: str) -> bool:
        """Check if a class name follows pytest naming conventions."""
        if name == "Test":
            return False
        return bool(cls.TEST_CLASS_PATTERN.match(name))

    @classmethod
    def validate_suite(cls, suite: TestSuite) -> List[str]:
        """Validate an entire test suite for pytest compatibility."""
        issues = []

        module_file = f"{suite.module_name}.py"
        if not cls.is_valid_test_file_name(module_file):
            issues.append(f"Module name '{suite.module_name}' won't be collected by pytest")

        for test_case in suite.standalone_tests:
            if not cls.is_valid_test_function_name(test_case.name):
                issues.append(f"Function '{test_case.name}' won't be collected by pytest")

        for test_cls in suite.test_classes:
            if not cls.is_valid_test_class_name(test_cls.name):
                issues.append(f"Class '{test_cls.name}' won't be collected by pytest")
            for test_case in test_cls.test_cases:
                if not cls.is_valid_test_function_name(test_case.name):
                    issues.append(
                        f"Method '{test_case.name}' in class '{test_cls.name}' "
                        f"won't be collected by pytest"
                    )

        return issues

    @classmethod
    def has_init(cls, test_class: TestClass) -> bool:
        """Check if a test class has __init__ (which prevents pytest collection)."""
        for test_case in test_class.test_cases:
            if test_case.name == '__init__':
                return True
        return False


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def simple_function():
    """A simple source function with no parameters."""
    return SourceFunction(name="do_something")


@pytest.fixture
def function_with_params():
    """A source function with various parameters."""
    return SourceFunction(
        name="calculate",
        parameters=[
            SourceParameter(name="self"),
            SourceParameter(name="x", annotation="int"),
            SourceParameter(name="y", annotation="int", default="0"),
        ],
        return_annotation="int",
        docstring="Calculate something.",
    )


@pytest.fixture
def complex_function():
    """A function with *args and **kwargs."""
    return SourceFunction(
        name="process",
        parameters=[
            SourceParameter(name="data", annotation="str"),
            SourceParameter(name="args", is_args=True),
            SourceParameter(name="kwargs", is_kwargs=True),
        ],
        is_async=True,
    )


@pytest.fixture
def private_function():
    """A private function."""
    return SourceFunction(name="__private_helper")


@pytest.fixture
def protected_function():
    """A protected function."""
    return SourceFunction(name="_internal_process")


@pytest.fixture
def dunder_function():
    """A dunder method."""
    return SourceFunction(name="__init__", parameters=[
        SourceParameter(name="self"),
        SourceParameter(name="value", annotation="int"),
    ])


@pytest.fixture
def static_method():
    """A static method."""
    return SourceFunction(
        name="from_string",
        parameters=[SourceParameter(name="s", annotation="str")],
        decorators=["staticmethod"],
    )


@pytest.fixture
def class_method():
    """A class method."""
    return SourceFunction(
        name="create",
        parameters=[
            SourceParameter(name="cls"),
            SourceParameter(name="value"),
        ],
        decorators=["classmethod"],
    )


@pytest.fixture
def property_method():
    """A property."""
    return SourceFunction(
        name="value",
        parameters=[SourceParameter(name="self")],
        decorators=["property"],
    )


@pytest.fixture
def sample_class():
    """A sample source class with mixed visibility methods."""
    return SourceClass(
        name="Calculator",
        methods=[
            SourceFunction(name="__init__", parameters=[
                SourceParameter(name="self"),
            ]),
            SourceFunction(name="add", parameters=[
                SourceParameter(name="self"),
                SourceParameter(name="a", annotation="int"),
                SourceParameter(name="b", annotation="int"),
            ], return_annotation="int"),
            SourceFunction(name="subtract", parameters=[
                SourceParameter(name="self"),
                SourceParameter(name="a", annotation="int"),
                SourceParameter(name="b", annotation="int"),
            ]),
            SourceFunction(name="_validate", parameters=[
                SourceParameter(name="self"),
                SourceParameter(name="value"),
            ]),
            SourceFunction(name="__secret", parameters=[
                SourceParameter(name="self"),
            ]),
        ],
        docstring="A simple calculator.",
    )


@pytest.fixture
def empty_class():
    """An empty source class."""
    return SourceClass(name="Empty", methods=[], docstring="Empty class.")


@pytest.fixture
def sample_module(sample_class):
    """A sample source module."""
    return SourceModule(
        name="calculator",
        functions=[
            SourceFunction(name="helper_func"),
            SourceFunction(name="_private_helper"),
        ],
        classes=[sample_class],
        docstring="Calculator module.",
    )


@pytest.fixture
def empty_module():
    """An empty source module."""
    return SourceModule(name="empty_module")


@pytest.fixture
def suite_generator():
    """Default test suite generator."""
    return TestSuiteGenerator()


@pytest.fixture
def inclusive_generator():
    """Generator that includes private and dunder methods."""
    return TestSuiteGenerator(include_private=True, include_dunder=True)


@pytest.fixture
def stub_generator():
    """Default stub generator."""
    return TestStubGenerator()


@pytest.fixture
def parametrized_builder():
    """Parametrized test builder."""
    return ParametrizedTestBuilder()


# =============================================================================
# TEST CLASSES
# =============================================================================

class TestSourceFunctionVisibility:
    """Tests for SourceFunction visibility detection."""

    def test_public_visibility(self, simple_function):
        assert simple_function.visibility == Visibility.PUBLIC

    def test_protected_visibility(self, protected_function):
        assert protected_function.visibility == Visibility.PROTECTED

    def test_private_visibility(self, private_function):
        assert private_function.visibility == Visibility.PRIVATE

    def test_dunder_visibility(self, dunder_function):
        assert dunder_function.visibility == Visibility.DUNDER

    @pytest.mark.parametrize("name,expected", [
        ("public_func", Visibility.PUBLIC),
        ("_protected", Visibility.PROTECTED),
        ("__private", Visibility.PRIVATE),
        ("__dunder__", Visibility.DUNDER),
        ("__init__", Visibility.DUNDER),
        ("__str__", Visibility.DUNDER),
        ("_", Visibility.PROTECTED),
    ])
    def test_visibility_parametrized(self, name, expected):
        func = SourceFunction(name=name)
        assert func.visibility == expected


class TestSourceFunctionMethodType:
    """Tests for SourceFunction method type detection."""

    def test_instance_method(self, simple_function):
        assert simple_function.method_type == MethodType.INSTANCE

    def test_static_method(self, static_method):
        assert static_method.method_type == MethodType.STATIC_METHOD

    def test_class_method(self, class_method):
        assert class_method.method_type == MethodType.CLASS_METHOD

    def test_property(self, property_method):
        assert property_method.method_type == MethodType.PROPERTY


class TestSanitizeTestName:
    """Tests for the _sanitize_test_name helper."""

    @pytest.mark.parametrize("input_name,expected", [
        ("simple", "simple"),
        ("with spaces", "with_spaces"),
        ("with-dashes", "with_dashes"),
        ("with.dots", "with_dots"),
        ("123leading_digits", "leading_digits"),
        ("CamelCase", "CamelCase"),
        ("multiple___underscores", "multiple_underscores"),
        ("trailing_", "trailing"),
        ("_leading", "leading"),
        ("a" * 150, "a" * 100),
        ("", "unnamed"),
        ("123", "unnamed"),
        ("hello!@#world", "hello_world"),
    ])
    def test_sanitize_names(self, input_name, expected):
        assert _sanitize_test_name(input_name) == expected


class TestTestSuiteGeneration:
    """Tests for TestSuiteGenerator."""

    def test_generate_from_empty_module(self, suite_generator, empty_module):
        suite = suite_generator.generate(empty_module)
        assert suite.module_name == "test_empty_module"
        assert suite.total_test_count == 0
        assert len(suite.test_classes) == 0
        assert len(suite.standalone_tests) == 0

    def test_generate_module_name(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        assert suite.module_name == "test_calculator"

    def test_generate_imports(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        assert "import calculator" in suite.imports
        assert "import pytest" in suite.imports

    def test_generate_standalone_tests_excludes_private(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        # Default generator excludes PRIVATE (__dbl) and DUNDER, but includes PROTECTED (_single)
        assert len(suite.standalone_tests) == 2
        names = {tc.name for tc in suite.standalone_tests}
        assert "test_helper_func" in names
        assert "test_private_helper" in names

    def test_generate_standalone_tests_includes_private(self, inclusive_generator, sample_module):
        suite = inclusive_generator.generate(sample_module)
        assert len(suite.standalone_tests) == 2
        names = {tc.name for tc in suite.standalone_tests}
        assert "test_helper_func" in names
        assert "test_private_helper" in names

    def test_generate_test_class(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        assert len(suite.test_classes) == 1
        test_class = suite.test_classes[0]
        assert test_class.name == "TestCalculator"

    def test_generate_test_class_methods_default(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        test_class = suite.test_classes[0]
        method_names = {tc.name for tc in test_class.test_cases}
        assert "test_add" in method_names
        assert "test_subtract" in method_names
        assert "test_validate" in method_names  # _validate is PROTECTED, included by default
        assert len(test_class.test_cases) == 3

    def test_generate_test_class_methods_inclusive(self, inclusive_generator, sample_module):
        suite = inclusive_generator.generate(sample_module)
        test_class = suite.test_classes[0]
        assert len(test_class.test_cases) == 5

    def test_setup_teardown_generated(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        test_class = suite.test_classes[0]
        assert test_class.setup_method is not None
        assert test_class.teardown_method is not None
        assert "setup_method" in test_class.setup_method
        assert "teardown_method" in test_class.teardown_method

    def test_no_setup_for_empty_class(self, suite_generator, empty_module):
        empty_module.classes.append(SourceClass(name="EmptyClass"))
        suite = suite_generator.generate(empty_module)
        assert len(suite.test_classes) == 0

    def test_fixtures_generated(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        assert len(suite.fixtures) > 0
        assert "calculator" in suite.fixtures

    def test_fixtures_not_generated_when_disabled(self, sample_module):
        gen = TestSuiteGenerator(generate_fixtures=False)
        suite = gen.generate(sample_module)
        assert len(suite.fixtures) == 0

    def test_total_test_count(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        # 2 standalone (helper_func + _private_helper) + 3 class methods (add, subtract, _validate)
        assert suite.total_test_count == 5

    def test_invalid_input_type(self, suite_generator):
        with pytest.raises(TypeError, match="Expected SourceModule"):
            suite_generator.generate("not a module")

    def test_generate_with_multiple_classes(self, suite_generator):
        module = SourceModule(
            name="multi",
            classes=[
                SourceClass(name="Alpha", methods=[
                    SourceFunction(name="foo"),
                ]),
                SourceClass(name="Beta", methods=[
                    SourceFunction(name="bar"),
                    SourceFunction(name="baz"),
                ]),
            ],
        )
        suite = suite_generator.generate(module)
        assert len(suite.test_classes) == 2
        assert suite.total_test_count == 3

    def test_test_case_has_docstring(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        for test_case in suite.standalone_tests:
            assert test_case.docstring is not None
            assert "Test for" in test_case.docstring

    def test_generator_with_different_stub_styles(self, sample_module):
        for style in StubStyle:
            gen = TestSuiteGenerator(stub_style=style)
            suite = gen.generate(sample_module)
            assert suite.total_test_count > 0


class TestTestStubGeneration:
    """Tests for TestStubGenerator."""

    def test_minimal_stub(self, simple_function):
        gen = TestStubGenerator(style=StubStyle.MINIMAL)
        stub = gen.generate(simple_function)
        assert "assert True" in stub.body
        assert "TODO" in stub.body

    def test_standard_stub(self, simple_function):
        gen = TestStubGenerator(style=StubStyle.STANDARD)
        stub = gen.generate(simple_function)
        assert "# Arrange" in stub.body
        assert "# Act" in stub.body
        assert "# Assert" in stub.body

    def test_comprehensive_stub(self, function_with_params):
        gen = TestStubGenerator(style=StubStyle.COMPREHENSIVE)
        stub = gen.generate(function_with_params)
        assert '"""' in stub.body
        assert "# Arrange" in stub.body
        assert "x =" in stub.body
        assert "y = 0" in stub.body
        assert "self =" not in stub.body

    def test_comprehensive_stub_with_args_kwargs(self, complex_function):
        gen = TestStubGenerator(style=StubStyle.COMPREHENSIVE)
        stub = gen.generate(complex_function)
        assert "args = ()" in stub.body
        assert "kwargs = {}" in stub.body

    def test_stub_function_name(self, simple_function, stub_generator):
        stub = stub_generator.generate(simple_function)
        assert stub.function_name == "test_do_something"

    def test_stub_source_function(self, simple_function, stub_generator):
        stub = stub_generator.generate(simple_function)
        assert stub.source_function == "do_something"

    def test_stub_style_preserved(self):
        for style in StubStyle:
            gen = TestStubGenerator(style=style)
            stub = gen.generate(SourceFunction(name="x"))
            assert stub.style == style

    def test_generate_batch(self, stub_generator):
        funcs = [
            SourceFunction(name="func_a"),
            SourceFunction(name="func_b"),
            SourceFunction(name="func_c"),
        ]
        stubs = stub_generator.generate_batch(funcs)
        assert len(stubs) == 3
        assert stubs[0].function_name == "test_func_a"
        assert stubs[1].function_name == "test_func_b"
        assert stubs[2].function_name == "test_func_c"

    def test_generate_batch_empty(self, stub_generator):
        stubs = stub_generator.generate_batch([])
        assert stubs == []

    def test_invalid_input(self, stub_generator):
        with pytest.raises(TypeError, match="Expected SourceFunction"):
            stub_generator.generate("not a function")

    def test_comprehensive_no_params(self):
        gen = TestStubGenerator(style=StubStyle.COMPREHENSIVE)
        stub = gen.generate(SourceFunction(name="no_params"))
        assert "# Arrange" in stub.body
        assert "# Act" in stub.body

    def test_stub_for_function_with_only_self(self):
        gen = TestStubGenerator(style=StubStyle.COMPREHENSIVE)
        func = SourceFunction(name="method", parameters=[SourceParameter(name="self")])
        stub = gen.generate(func)
        assert "self =" not in stub.body


class TestPytestCollection:
    """Tests for PytestCollector validation."""

    @pytest.mark.parametrize("filename,expected", [
        ("test_something.py", True),
        ("something_test.py", True),
        ("test_.py", True),
        ("something.py", False),
        ("test_something.txt", False),
        ("Test_something.py", False),
        ("_test.py", True),  # matches ^.*_test\.py$ where .* is empty
        ("test_a_b_c.py", True),
    ])
    def test_valid_test_file_names(self, filename, expected):
        assert PytestCollector.is_valid_test_file_name(filename) == expected

    @pytest.mark.parametrize("funcname,expected", [
        ("test_something", True),
        ("test_a", True),
        ("test_123", True),
        ("test_CamelCase", True),
        ("something", False),
        ("Test_something", False),
        ("test_", False),
        ("test", False),
        ("test_a_b_c", True),
        ("test_with_numbers_123", True),
    ])
    def test_valid_test_function_names(self, funcname, expected):
        assert PytestCollector.is_valid_test_function_name(funcname) == expected

    @pytest.mark.parametrize("classname,expected", [
        ("TestSomething", True),
        ("TestA", True),
        ("Test", False),
        ("test_something", False),
        ("Something", False),
        ("TestCamelCase", True),
        ("Test123", False),  # pattern requires Test[A-Z] — digit after Test doesn't match
        ("TestWith_Underscore", True),
    ])
    def test_valid_test_class_names(self, classname, expected):
        assert PytestCollector.is_valid_test_class_name(classname) == expected

    def test_validate_suite_valid(self, suite_generator, sample_module):
        suite = suite_generator.generate(sample_module)
        issues = PytestCollector.validate_suite(suite)
        assert len(issues) == 0, f"Unexpected issues: {issues}"

    def test_validate_suite_bad_module_name(self):
        suite = TestSuite(module_name="bad_name")
        issues = PytestCollector.validate_suite(suite)
        assert any("module name" in issue.lower() or "won't be collected" in issue.lower()
                    for issue in issues)

    def test_validate_suite_bad_function_name(self):
        suite = TestSuite(
            module_name="test_good",
            standalone_tests=[TestCase(name="bad_name", body="pass")],
        )
        issues = PytestCollector.validate_suite(suite)
        assert len(issues) == 1

    def test_validate_suite_bad_class_name(self):
        suite = TestSuite(
            module_name="test_good",
            test_classes=[TestClass(name="bad_class", test_cases=[
                TestCase(name="test_ok", body="pass"),
            ])],
        )
        issues = PytestCollector.validate_suite(suite)
        assert len(issues) == 1

    def test_validate_suite_bad_method_in_class(self):
        suite = TestSuite(
            module_name="test_good",
            test_classes=[TestClass(name="TestGood", test_cases=[
                TestCase(name="not_a_test", body="pass"),
            ])],
        )
        issues = PytestCollector.validate_suite(suite)
        assert len(issues) == 1
        assert "TestGood" in issues[0]

    def test_has_init_true(self):
        test_cls = TestClass(
            name="TestBad",
            test_cases=[TestCase(name="__init__", body="pass")],
        )
        assert PytestCollector.has_init(test_cls) is True

    def test_has_init_false(self):
        test_cls = TestClass(
            name="TestGood",
            test_cases=[TestCase(name="test_something", body="pass")],
        )
        assert PytestCollector.has_init(test_cls) is False

    def test_generated_suite_passes_collection_validation(self, sample_module):
        """Integration: generated suites should always pass validation."""
        gen = TestSuiteGenerator()
        suite = gen.generate(sample_module)
        issues = PytestCollector.validate_suite(suite)
        assert issues == []


class TestParametrizedTestConstruction:
    """Tests for ParametrizedTestBuilder and ParametrizedConfig."""

    def test_simple_config(self):
        config = ParametrizedConfig(
            param_names=["x", "y", "expected"],
            param_values=[(1, 2, 3), (4, 5, 9)],
        )
        assert config.validate() == []

    def test_config_with_ids(self):
        config = ParametrizedConfig(
            param_names=["input", "expected"],
            param_values=[("hello", 5), ("world", 5)],
            ids=["short_word", "another_word"],
        )
        assert config.validate() == []
        assert "ids=" in config.decorator_string

    def test_config_with_indirect(self):
        config = ParametrizedConfig(
            param_names=["fixture_name"],
            param_values=[("a",), ("b",)],
            indirect=True,
        )
        assert "indirect=True" in config.decorator_string

    def test_config_mismatched_values(self):
        config = ParametrizedConfig(
            param_names=["x", "y"],
            param_values=[(1,), (2, 3)],
        )
        errors = config.validate()
        assert len(errors) > 0
        assert any("value" in err.lower() or "values" in err.lower() for err in errors)

    def test_config_mismatched_ids(self):
        config = ParametrizedConfig(
            param_names=["x"],
            param_values=[(1,), (2,)],
            ids=["only_one"],
        )
        errors = config.validate()
        assert len(errors) > 0

    def test_config_empty_names(self):
        config = ParametrizedConfig(
            param_names=[],
            param_values=[],
        )
        errors = config.validate()
        assert any("names" in err.lower() or "empty" in err.lower() for err in errors)

    def test_config_empty_values(self):
        config = ParametrizedConfig(
            param_names=["x"],
            param_values=[],
        )
        errors = config.validate()
        assert any("values" in err.lower() or "empty" in err.lower() for err in errors)

    def test_decorator_string_format(self):
        config = ParametrizedConfig(
            param_names=["a", "b"],
            param_values=[(1, 2), (3, 4)],
        )
        dec = config.decorator_string
        assert dec.startswith("@pytest.mark.parametrize(")
        assert '"a, b"' in dec
        assert dec.endswith(")")

    def test_builder_add_and_build(self, parametrized_builder):
        config = ParametrizedConfig(
            param_names=["x"],
            param_values=[(1,), (2,)],
        )
        parametrized_builder.add_config(config)
        result = parametrized_builder.build()
        assert len(result) == 1
        assert result[0] is config

    def test_builder_chaining(self, parametrized_builder):
        cfg1 = ParametrizedConfig(param_names=["x"], param_values=[(1,)])
        cfg2 = ParametrizedConfig(param_names=["y"], param_values=[(2,)])
        result = parametrized_builder.add_config(cfg1).add_config(cfg2).build()
        assert len(result) == 2

    def test_builder_clear(self, parametrized_builder):
        config = ParametrizedConfig(param_names=["x"], param_values=[(1,)])
        parametrized_builder.add_config(config)
        parametrized_builder.clear()
        assert parametrized_builder.build() == []

    def test_builder_rejects_invalid(self, parametrized_builder):
        config = ParametrizedConfig(param_names=[], param_values=[])
        with pytest.raises(ValueError, match="Invalid config"):
            parametrized_builder.add_config(config)

    def test_builder_decorator_strings(self, parametrized_builder):
        cfg1 = ParametrizedConfig(param_names=["x"], param_values=[(1,), (2,)])
        parametrized_builder.add_config(cfg1)
        strings = parametrized_builder.build_decorator_strings()
        assert len(strings) == 1
        assert "@pytest.mark.parametrize" in strings[0]

    def test_from_examples(self):
        func = SourceFunction(name="add")
        examples = [
            {"a": 1, "b": 2, "expected": 3},
            {"a": 4, "b": 5, "expected": 9},
        ]
        config = ParametrizedTestBuilder.from_examples(func, examples)
        assert "a" in config.param_names
        assert "b" in config.param_names
        assert "expected" in config.param_names
        assert len(config.param_values) == 2

    def test_from_examples_empty(self):
        func = SourceFunction(name="add")
        with pytest.raises(ValueError, match="empty"):
            ParametrizedTestBuilder.from_examples(func, [])

    def test_from_examples_missing_expected(self):
        func = SourceFunction(name="add")
        examples = [{"a": 1, "b": 2}]
        with pytest.raises(KeyError, match="expected"):
            ParametrizedTestBuilder.from_examples(func, examples)

    def test_single_param_value_set(self):
        config = ParametrizedConfig(
            param_names=["x"],
            param_values=[(42,)],
        )
        assert config.validate() == []
        assert "42" in config.decorator_string


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unicode_function_name(self):
        func = SourceFunction(name="café_latte")
        gen = TestStubGenerator()
        stub = gen.generate(func)
        assert stub.function_name == "test_caf_latte"

    def test_very_long_function_name(self):
        long_name = "a" * 200
        func = SourceFunction(name=long_name)
        gen = TestStubGenerator()
        stub = gen.generate(func)
        assert len(stub.function_name) <= 106  # "test_" + 100 + tolerance

    def test_function_name_with_special_chars(self):
        func = SourceFunction(name="hello-world!!")
        sanitized = _sanitize_test_name(func.name)
        assert sanitized.isidentifier() or sanitized == "unnamed"

    def test_empty_class_produces_no_test_class(self, suite_generator):
        module = SourceModule(
            name="mod",
            classes=[SourceClass(name="Empty", methods=[])],
        )
        suite = suite_generator.generate(module)
        assert len(suite.test_classes) == 0

    def test_class_with_only_private_methods_default(self, suite_generator):
        module = SourceModule(
            name="mod",
            classes=[SourceClass(name="Secret", methods=[
                SourceFunction(name="__hidden"),
                SourceFunction(name="_internal"),
            ])],
        )
        suite = suite_generator.generate(module)
        # __hidden is PRIVATE (excluded), but _internal is PROTECTED (included by default)
        assert len(suite.test_classes) == 1
        assert len(suite.test_classes[0].test_cases) == 1
        assert suite.test_classes[0].test_cases[0].name == "test_internal"

    def test_class_with_only_private_methods_inclusive(self, inclusive_generator):
        module = SourceModule(
            name="mod",
            classes=[SourceClass(name="Secret", methods=[
                SourceFunction(name="__hidden"),
                SourceFunction(name="_internal"),
            ])],
        )
        suite = inclusive_generator.generate(module)
        assert len(suite.test_classes) == 1
        assert len(suite.test_classes[0].test_cases) == 2

    def test_name_collision_across_classes(self, suite_generator):
        module = SourceModule(
            name="mod",
            classes=[
                SourceClass(name="A", methods=[SourceFunction(name="run")]),
                SourceClass(name="B", methods=[SourceFunction(name="run")]),
            ],
        )
        suite = suite_generator.generate(module)
        assert len(suite.test_classes) == 2
        assert suite.test_classes[0].test_cases[0].name == "test_run"
        assert suite.test_classes[1].test_cases[0].name == "test_run"

    def test_module_with_no_functions_no_classes(self, suite_generator, empty_module):
        suite = suite_generator.generate(empty_module)
        assert suite.total_test_count == 0
        assert suite.fixtures == []

    def test_suite_total_count_mixed(self):
        suite = TestSuite(
            module_name="test_m",
            standalone_tests=[TestCase(name="test_a", body="pass")],
            test_classes=[
                TestClass(name="TestX", test_cases=[
                    TestCase(name="test_b", body="pass"),
                    TestCase(name="test_c", body="pass"),
                ]),
            ],
        )
        assert suite.total_test_count == 3

    def test_multiple_validation_errors(self):
        config = ParametrizedConfig(
            param_names=[],
            param_values=[],
            ids=["orphan"],
        )
        errors = config.validate()
        assert len(errors) >= 2


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_end_to_end_generation_and_validation(self):
        """Generate a suite and validate it passes all checks."""
        module = SourceModule(
            name="my_app",
            functions=[
                SourceFunction(name="main"),
                SourceFunction(name="parse_args", parameters=[
                    SourceParameter(name="args", is_args=True),
                ]),
            ],
            classes=[
                SourceClass(name="App", methods=[
                    SourceFunction(name="run"),
                    SourceFunction(name="stop"),
                ]),
            ],
        )

        generator = TestSuiteGenerator(stub_style=StubStyle.COMPREHENSIVE)
        suite = generator.generate(module)

        assert suite.module_name == "test_my_app"
        assert suite.total_test_count == 4
        assert len(suite.test_classes) == 1
        assert suite.test_classes[0].name == "TestApp"

        issues = PytestCollector.validate_suite(suite)
        assert issues == []

        for test_case in suite.standalone_tests:
            assert len(test_case.body) > 0

    def test_parametrized_with_generated_stubs(self):
        """Combine parametrized configs with stub generation."""
        func = SourceFunction(
            name="add",
            parameters=[
                SourceParameter(name="a", annotation="int"),
                SourceParameter(name="b", annotation="int"),
            ],
            return_annotation="int",
        )

        stub_gen = TestStubGenerator(style=StubStyle.STANDARD)
        stub = stub_gen.generate(func)

        config = ParametrizedConfig(
            param_names=["a", "b", "expected"],
            param_values=[(1, 2, 3), (0, 0, 0), (-1, 1, 0)],
            ids=["positive", "zeros", "mixed"],
        )

        test_case = TestCase(
            name=stub.function_name,
            body=stub.body,
            decorators=[config.decorator_string],
        )

        assert test_case.name == "test_add"
        assert len(test_case.decorators) == 1
        assert "@pytest.mark.parametrize" in test_case.decorators[0]

    def test_full_pipeline_multiple_styles(self):
        """Test generation with all stub styles."""
        func = SourceFunction(name="compute", parameters=[
            SourceParameter(name="self"),
            SourceParameter(name="value", annotation="float"),
        ])

        for style in StubStyle:
            gen = TestStubGenerator(style=style)
            stub = gen.generate(func)
            assert stub.function_name == "test_compute"
            assert len(stub.body) > 0
            assert stub.style == style

    def test_large_module_generation(self):
        """Test with a large number of functions and classes."""
        functions = [SourceFunction(name=f"func_{idx}") for idx in range(50)]
        classes = [
            SourceClass(
                name=f"Class{idx}",
                methods=[SourceFunction(name=f"method_{jdx}") for jdx in range(10)],
            )
            for idx in range(5)
        ]

        module = SourceModule(name="large_module", functions=functions, classes=classes)
        gen = TestSuiteGenerator()
        suite = gen.generate(module)

        assert len(suite.standalone_tests) == 50
        assert len(suite.test_classes) == 5
        assert suite.total_test_count == 100

        issues = PytestCollector.validate_suite(suite)
        assert issues == []

    def test_builder_with_from_examples_and_validate(self):
        """Test the full parametrized builder workflow."""
        builder = ParametrizedTestBuilder()
        func = SourceFunction(name="multiply")

        examples = [
            {"x": 2, "y": 3, "expected": 6},
            {"x": 0, "y": 5, "expected": 0},
            {"x": -1, "y": -1, "expected": 1},
        ]

        config = ParametrizedTestBuilder.from_examples(func, examples)
        builder.add_config(config)

        configs = builder.build()
        assert len(configs) == 1
        assert len(configs[0].param_values) == 3

        decorators = builder.build_decorator_strings()
        assert len(decorators) == 1

    def test_abstract_class_handling(self, suite_generator):
        """Abstract classes should still generate tests for concrete methods."""
        module = SourceModule(
            name="shapes",
            classes=[
                SourceClass(
                    name="Shape",
                    methods=[SourceFunction(name="area")],
                    is_abstract=True,
                ),
            ],
        )
        suite = suite_generator.generate(module)
        assert len(suite.test_classes) == 1


class TestDataModels:
    """Tests for data model correctness and default values."""

    def test_source_parameter_defaults(self):
        param = SourceParameter(name="x")
        assert param.annotation is None
        assert param.default is None
        assert param.is_args is False
        assert param.is_kwargs is False

    def test_source_function_defaults(self):
        func = SourceFunction(name="f")
        assert func.parameters == []
        assert func.return_annotation is None
        assert func.docstring is None
        assert func.decorators == []
        assert func.is_async is False

    def test_source_class_defaults(self):
        cls = SourceClass(name="C")
        assert cls.methods == []
        assert cls.bases == []
        assert cls.docstring is None
        assert cls.is_abstract is False

    def test_source_module_defaults(self):
        mod = SourceModule(name="m")
        assert mod.functions == []
        assert mod.classes == []
        assert mod.docstring is None

    def test_test_suite_defaults(self):
        suite = TestSuite(module_name="test_m")
        assert suite.test_classes == []
        assert suite.standalone_tests == []
        assert suite.imports == []
        assert suite.fixtures == []
        assert suite.total_test_count == 0

    def test_test_stub_defaults(self):
        stub = TestStub(function_name="test_x", body="pass")
        assert stub.style == StubStyle.STANDARD
        assert stub.source_function is None

    def test_parametrized_config_defaults(self):
        config = ParametrizedConfig(
            param_names=["x"],
            param_values=[(1,)],
        )
        assert config.ids is None
        assert config.indirect is False


class TestEnums:
    """Tests for enum completeness."""

    def test_method_type_values(self):
        assert len(MethodType) == 4
        assert MethodType.INSTANCE
        assert MethodType.CLASS_METHOD
        assert MethodType.STATIC_METHOD
        assert MethodType.PROPERTY

    def test_visibility_values(self):
        assert len(Visibility) == 4
        assert Visibility.PUBLIC
        assert Visibility.PROTECTED
        assert Visibility.PRIVATE
        assert Visibility.DUNDER

    def test_stub_style_values(self):
        assert len(StubStyle) == 3
        assert StubStyle.MINIMAL
        assert StubStyle.STANDARD
        assert StubStyle.COMPREHENSIVE