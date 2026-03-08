"""Shared fixtures for Micro Prime tests."""

from __future__ import annotations

import pytest

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.utils.code_manifest import (
    ElementKind,
    Param,
    ParamKind,
    Signature,
    Visibility,
)


@pytest.fixture
def simple_function_element() -> ForwardElementSpec:
    """A simple method element for testing."""
    return ForwardElementSpec(
        kind=ElementKind.METHOD,
        name="get_name",
        signature=Signature(
            params=[
                Param(name="self"),
                Param(name="key", annotation="str"),
            ],
            return_annotation="str",
        ),
        parent_class="MyClass",
        docstring_hint="Return the name for the given key.",
    )


@pytest.fixture
def constant_element() -> ForwardElementSpec:
    """A constant element for testing."""
    return ForwardElementSpec(
        kind=ElementKind.CONSTANT,
        name="DEFAULT_TIMEOUT",
        signature=Signature(
            params=[],
            return_annotation="int",
        ),
        docstring_hint="Default timeout in seconds.",
    )


@pytest.fixture
def async_function_element() -> ForwardElementSpec:
    """An async function element."""
    return ForwardElementSpec(
        kind=ElementKind.ASYNC_FUNCTION,
        name="fetch_data",
        signature=Signature(
            params=[
                Param(name="url", annotation="str"),
                Param(name="timeout", annotation="int", default="30"),
            ],
            return_annotation="dict",
        ),
        docstring_hint="Fetch data from the given URL.",
    )


@pytest.fixture
def property_element() -> ForwardElementSpec:
    """A property element."""
    return ForwardElementSpec(
        kind=ElementKind.PROPERTY,
        name="total",
        signature=Signature(
            params=[Param(name="self")],
            return_annotation="int",
        ),
        parent_class="Order",
        docstring_hint="Total order amount.",
        decorators=["property"],
    )


@pytest.fixture
def init_element() -> ForwardElementSpec:
    """An __init__ method element."""
    return ForwardElementSpec(
        kind=ElementKind.METHOD,
        name="__init__",
        signature=Signature(
            params=[
                Param(name="self"),
                Param(name="name", annotation="str"),
                Param(name="value", annotation="int", default="0"),
            ],
            return_annotation="None",
        ),
        parent_class="Config",
        docstring_hint="Initialize Config.",
    )


@pytest.fixture
def repr_element() -> ForwardElementSpec:
    """A __repr__ method element."""
    return ForwardElementSpec(
        kind=ElementKind.METHOD,
        name="__repr__",
        signature=Signature(
            params=[Param(name="self")],
            return_annotation="str",
        ),
        parent_class="Config",
    )


@pytest.fixture
def complex_function_element() -> ForwardElementSpec:
    """A complex function element (many params, async, kwargs)."""
    return ForwardElementSpec(
        kind=ElementKind.ASYNC_FUNCTION,
        name="orchestrate_pipeline",
        signature=Signature(
            params=[
                Param(name="config", annotation="dict"),
                Param(name="tasks", annotation="list"),
                Param(name="workers", annotation="int"),
                Param(name="timeout", annotation="float"),
                Param(name="retry", annotation="bool"),
                Param(name="kwargs", kind=ParamKind.VAR_KEYWORD),
            ],
            return_annotation="dict",
        ),
        docstring_hint="Orchestrate the full pipeline with all workers and retry logic.",
        decorators=["abstractmethod"],
    )


@pytest.fixture
def class_element_with_methods() -> ForwardElementSpec:
    """A class element whose methods are separate elements."""
    return ForwardElementSpec(
        kind=ElementKind.CLASS,
        name="CustomJsonFormatter",
        bases=["logging.Formatter"],
        docstring_hint=(
            "Formats log records as single-line JSON objects "
            "with timestamp, severity, name, and message fields."
        ),
    )


@pytest.fixture
def class_file_spec(class_element_with_methods) -> ForwardFileSpec:
    """File spec with a class + its methods as separate elements.

    Contains 5 elements to avoid the small-file bias (≤4 elements → -1)
    which would push the class from MODERATE to SIMPLE.
    """
    return ForwardFileSpec(
        file="src/emailservice/logger.py",
        imports=[
            ForwardImportSpec(kind="import", module="logging"),
            ForwardImportSpec(kind="import", module="json"),
            ForwardImportSpec(kind="from", module="datetime", names=["datetime"]),
        ],
        elements=[
            class_element_with_methods,
            ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="add_fields",
                signature=Signature(
                    params=[
                        Param(name="self"),
                        Param(name="log_record"),
                        Param(name="record"),
                        Param(name="message_dict"),
                    ],
                    return_annotation="None",
                ),
                parent_class="CustomJsonFormatter",
            ),
            ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="format",
                signature=Signature(
                    params=[
                        Param(name="self"),
                        Param(name="record", annotation="logging.LogRecord"),
                    ],
                    return_annotation="str",
                ),
                parent_class="CustomJsonFormatter",
            ),
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="getJSONLogger",
                signature=Signature(
                    params=[Param(name="name", annotation="str")],
                    return_annotation="logging.Logger",
                ),
            ),
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="setup_logging",
                signature=Signature(
                    params=[Param(name="level", annotation="int")],
                    return_annotation="None",
                ),
            ),
        ],
    )


@pytest.fixture
def class_skeleton() -> str:
    """Skeleton for the logger file with class + methods."""
    return '''# [STARTD8-SKELETON]
import logging
import json
from datetime import datetime

class CustomJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""
    raise NotImplementedError

    def add_fields(self, log_record, record, message_dict) -> None:
        """Add custom fields."""
        raise NotImplementedError

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record."""
        raise NotImplementedError
'''


@pytest.fixture
def class_manifest(class_file_spec) -> ForwardManifest:
    """A manifest for the class decomposition test."""
    return ForwardManifest(
        schema_version="1.0.0",
        file_specs={"src/emailservice/logger.py": class_file_spec},
        contracts=[],
    )


@pytest.fixture
def sample_file_spec() -> ForwardFileSpec:
    """A sample file spec with imports and elements."""
    return ForwardFileSpec(
        file="src/mypackage/utils.py",
        imports=[
            ForwardImportSpec(kind="from", module="typing", names=["Optional", "List"]),
            ForwardImportSpec(kind="from", module="pathlib", names=["Path"]),
            ForwardImportSpec(kind="import", module="json"),
        ],
        elements=[
            ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="get_name",
                signature=Signature(
                    params=[
                        Param(name="self"),
                        Param(name="key", annotation="str"),
                    ],
                    return_annotation="str",
                ),
                parent_class="MyClass",
            ),
            ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="get_value",
                signature=Signature(
                    params=[
                        Param(name="self"),
                        Param(name="key", annotation="str"),
                    ],
                    return_annotation="int",
                ),
                parent_class="MyClass",
            ),
            ForwardElementSpec(
                kind=ElementKind.CONSTANT,
                name="DEFAULT_TIMEOUT",
                signature=Signature(params=[], return_annotation="int"),
            ),
        ],
    )


@pytest.fixture
def sample_contracts() -> list[InterfaceContract]:
    """A list of sample contracts."""
    return [
        InterfaceContract(
            contract_id="C-001",
            category=ContractCategory.FUNCTION_NAME,
            confidence=ContractConfidence.EXPLICIT,
            description="Function must be named get_name",
            binding_text="Function name: get_name",
        ),
    ]


@pytest.fixture
def empty_contracts() -> list[InterfaceContract]:
    return []


@pytest.fixture
def sample_skeleton() -> str:
    """A sample skeleton file."""
    return '''# [STARTD8-SKELETON]
from __future__ import annotations
from typing import Optional, List
from pathlib import Path
import json


DEFAULT_TIMEOUT: int = ...  # STARTD8_AUTO_STUB


class MyClass:
    """My class."""

    def get_name(self, key: str) -> str:
        """Return the name for the given key."""
        raise NotImplementedError

    def get_value(self, key: str) -> int:
        """Return the value for the given key."""
        raise NotImplementedError
'''


@pytest.fixture
def filled_skeleton() -> str:
    """A skeleton with stubs replaced by implementations (for file-write tests)."""
    return '''# [STARTD8-SKELETON]
from __future__ import annotations
from typing import Optional, List
from pathlib import Path
import json


DEFAULT_TIMEOUT: int = 30


class MyClass:
    """My class."""

    def get_name(self, key: str) -> str:
        """Return the name for the given key."""
        return str(key)

    def get_value(self, key: str) -> int:
        """Return the value for the given key."""
        return len(key)
'''


@pytest.fixture
def sample_manifest(sample_file_spec, sample_contracts) -> ForwardManifest:
    """A sample forward manifest."""
    return ForwardManifest(
        schema_version="1.0.0",
        file_specs={"src/mypackage/utils.py": sample_file_spec},
        contracts=sample_contracts,
    )
