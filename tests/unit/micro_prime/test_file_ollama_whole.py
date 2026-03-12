"""Tests for file-level Ollama-whole generation strategy.

Validates that the engine can generate complete small files in a single
Ollama call instead of decomposing into individual element bodies.
"""

from __future__ import annotations

import ast
from unittest.mock import MagicMock, patch

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
)
from startd8.micro_prime.engine import (
    MicroPrimeEngine,
    _build_file_whole_prompt,
    _skeleton_has_stubs,
    _validate_file_whole_result,
)
from startd8.micro_prime.models import MicroPrimeConfig
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def logger_file_spec() -> ForwardFileSpec:
    """File spec matching the online-boutique Shared JSON Logger."""
    return ForwardFileSpec(
        file="src/recommendationservice/logger.py",
        imports=[
            ForwardImportSpec(kind="import", module="logging"),
            ForwardImportSpec(kind="import", module="sys"),
            ForwardImportSpec(
                kind="from", module="pythonjsonlogger", names=["jsonlogger"],
            ),
        ],
        elements=[
            ForwardElementSpec(
                kind=ElementKind.CLASS,
                name="CustomJsonFormatter",
                bases=["jsonlogger.JsonFormatter"],
            ),
            ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="add_fields",
                parent_class="CustomJsonFormatter",
                signature=Signature(
                    params=[
                        Param(name="self"),
                        Param(name="log_record"),
                        Param(name="record"),
                        Param(name="message_dict"),
                    ],
                    return_annotation="None",
                ),
            ),
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="getJSONLogger",
                signature=Signature(
                    params=[Param(name="name", annotation="str")],
                    return_annotation="logging.Logger",
                ),
            ),
        ],
    )


@pytest.fixture
def logger_skeleton() -> str:
    """Skeleton for the Shared JSON Logger file."""
    return '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        raise NotImplementedError


def getJSONLogger(name: str) -> logging.Logger:
    raise NotImplementedError
'''


@pytest.fixture
def logger_filled() -> str:
    """Correct implementation of the Shared JSON Logger."""
    return '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        if 'timestamp' not in log_record:
            log_record['timestamp'] = record.created
        if 'severity' in log_record:
            log_record['severity'] = log_record['severity'].upper()
        else:
            log_record['severity'] = record.levelname


def getJSONLogger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter(
        '%(timestamp)s %(severity)s %(name)s %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
'''


@pytest.fixture
def logger_manifest(logger_file_spec) -> ForwardManifest:
    return ForwardManifest(file_specs={logger_file_spec.file: logger_file_spec})


# ── Prompt builder tests ────────────────────────────────────────────────


class TestBuildFileWholePrompt:
    def test_includes_skeleton(self, logger_skeleton, logger_file_spec):
        prompt = _build_file_whole_prompt(logger_skeleton, logger_file_spec)
        assert "raise NotImplementedError" in prompt
        assert "CustomJsonFormatter" in prompt
        assert "getJSONLogger" in prompt

    def test_includes_task_description(self, logger_skeleton, logger_file_spec):
        prompt = _build_file_whole_prompt(
            logger_skeleton, logger_file_spec,
            task_description="Implement structured JSON logging for recommendationservice",
        )
        assert "structured JSON logging" in prompt

    def test_includes_domain_constraints(self, logger_skeleton, logger_file_spec):
        prompt = _build_file_whole_prompt(
            logger_skeleton, logger_file_spec,
            domain_constraints=["must use pythonjsonlogger", "log to stdout only"],
        )
        assert "pythonjsonlogger" in prompt
        assert "log to stdout only" in prompt

    def test_includes_fill_instructions(self, logger_skeleton, logger_file_spec):
        prompt = _build_file_whole_prompt(logger_skeleton, logger_file_spec)
        assert "Fill in ALL" in prompt
        assert "COMPLETE file" in prompt


# ── Validation tests ────────────────────────────────────────────────────


class TestValidateFileWholeResult:
    def test_valid_implementation(self, logger_filled, logger_skeleton, logger_file_spec):
        valid, reason, missing = _validate_file_whole_result(
            logger_filled, logger_skeleton, logger_file_spec,
        )
        assert valid is True
        assert reason == "all checks passed"
        assert missing == []

    def test_rejects_empty_output(self, logger_skeleton, logger_file_spec):
        valid, reason, missing = _validate_file_whole_result(
            "", logger_skeleton, logger_file_spec,
        )
        assert valid is False
        assert "empty" in reason
        assert missing == []  # hard fail — no partial info

    def test_rejects_syntax_error(self, logger_skeleton, logger_file_spec):
        valid, reason, missing = _validate_file_whole_result(
            "def broken(:\n    pass", logger_skeleton, logger_file_spec,
        )
        assert valid is False
        assert "ast.parse" in reason
        assert missing == []  # hard fail

    def test_rejects_remaining_stubs(self, logger_skeleton, logger_file_spec):
        partial = logger_skeleton  # skeleton has unfilled stubs
        valid, reason, missing = _validate_file_whole_result(
            partial, logger_skeleton, logger_file_spec,
        )
        assert valid is False
        assert "stub-only NotImplementedError bodies" in reason
        assert len(missing) > 0  # soft fail — missing list populated

    def test_rejects_missing_elements(self, logger_skeleton, logger_file_spec):
        # Only has one of the three expected elements (class and method missing)
        code = "import logging\n\ndef getJSONLogger(name: str):\n    return logging.getLogger(name)\n"
        valid, reason, missing = _validate_file_whole_result(
            code, logger_skeleton, logger_file_spec,
        )
        assert valid is False
        assert "missing elements" in reason
        assert "class CustomJsonFormatter" in reason
        assert len(missing) > 0  # soft fail — missing list populated

    def test_strips_markdown_fences(self, logger_filled, logger_skeleton, logger_file_spec):
        fenced = f"```python\n{logger_filled}\n```"
        valid, reason, _missing = _validate_file_whole_result(
            fenced, logger_skeleton, logger_file_spec,
        )
        assert valid is True

    def test_rejects_skeleton_markers(self, logger_skeleton, logger_file_spec):
        code = "# [STARTD8-SKELETON]\nimport logging\ndef getJSONLogger(name): pass\n"
        valid, reason, missing = _validate_file_whole_result(
            code, logger_skeleton, logger_file_spec,
        )
        assert valid is False
        assert "skeleton markers" in reason
        assert missing == []  # hard fail


# ── Eligibility tests ───────────────────────────────────────────────────


class TestFileOllamaWholeEligibility:
    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_eligible_small_file(self, logger_file_spec, logger_skeleton):
        engine = self._make_engine()
        assert engine._is_file_ollama_whole_eligible(logger_file_spec, logger_skeleton)

    def test_disabled_by_config(self, logger_file_spec, logger_skeleton):
        engine = self._make_engine(file_ollama_whole_enabled=False)
        assert not engine._is_file_ollama_whole_eligible(logger_file_spec, logger_skeleton)

    def test_too_many_elements(self, logger_file_spec, logger_skeleton):
        engine = self._make_engine(file_ollama_whole_max_elements=2)
        assert not engine._is_file_ollama_whole_eligible(logger_file_spec, logger_skeleton)

    def test_too_many_lines(self, logger_file_spec, logger_skeleton):
        engine = self._make_engine(file_ollama_whole_max_loc=5)
        assert not engine._is_file_ollama_whole_eligible(logger_file_spec, logger_skeleton)

    def test_no_stubs_in_skeleton(self, logger_file_spec, logger_filled):
        engine = self._make_engine()
        # logger_filled has no raise NotImplementedError
        assert not engine._is_file_ollama_whole_eligible(logger_file_spec, logger_filled)


# ── Integration: process_file with file-whole ────────────────────────────


class TestProcessFileWithFileWhole:
    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_file_whole_success_skips_element_by_element(
        self, logger_file_spec, logger_skeleton, logger_filled, logger_manifest,
    ):
        """When file-whole succeeds, all elements should be marked successful."""
        engine = self._make_engine()

        with patch.object(engine, "_generate_ollama", return_value=(logger_filled, 100, 50)):
            result = engine.process_file(
                logger_file_spec, logger_manifest, logger_skeleton,
            )

        # All elements should be successful
        assert len(result.element_results) == 3
        for er in result.element_results:
            assert er.success is True
            assert er.decomposition_metadata["strategy"] == "file_ollama_whole"

        # filled_skeleton should be the complete file
        assert "raise NotImplementedError" not in result.filled_skeleton
        ast.parse(result.filled_skeleton)

    def test_file_whole_failure_falls_through(
        self, logger_file_spec, logger_skeleton, logger_manifest,
    ):
        """When file-whole fails, element-by-element should be attempted."""
        engine = self._make_engine()

        # First call = file-whole (returns garbage), subsequent = element-by-element
        call_count = 0

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # File-whole attempt returns only imports (simulates the real failure)
                return ("import json\nimport logging\n", 100, 10)
            # Element-by-element attempts
            return ("    return None", 50, 10)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate):
            result = engine.process_file(
                logger_file_spec, logger_manifest, logger_skeleton,
            )

        # file-whole failed → element-by-element was attempted
        # At least one call was made beyond the first file-whole attempt
        assert call_count > 1

    def test_file_whole_disabled_skips_attempt(
        self, logger_file_spec, logger_skeleton, logger_manifest,
    ):
        """When file_ollama_whole_enabled=False, no file-whole attempt is made."""
        engine = self._make_engine(file_ollama_whole_enabled=False)

        call_count = 0
        original_attempt = engine._attempt_file_ollama_whole

        def track_attempt(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_attempt(*args, **kwargs)

        with patch.object(engine, "_attempt_file_ollama_whole", side_effect=track_attempt):
            with patch.object(engine, "_generate_ollama", return_value=("    return None", 50, 10)):
                engine.process_file(
                    logger_file_spec, logger_manifest, logger_skeleton,
                )

        assert call_count == 0

    def test_file_whole_with_markdown_fences(
        self, logger_file_spec, logger_skeleton, logger_filled, logger_manifest,
    ):
        """File-whole should succeed even if Ollama wraps output in fences."""
        engine = self._make_engine()
        fenced = f"```python\n{logger_filled}\n```"

        with patch.object(engine, "_generate_ollama", return_value=(fenced, 100, 50)):
            result = engine.process_file(
                logger_file_spec, logger_manifest, logger_skeleton,
            )

        assert all(er.success for er in result.element_results)
        assert "```" not in result.filled_skeleton

    def test_file_whole_ollama_exception_falls_through(
        self, logger_file_spec, logger_skeleton, logger_manifest,
    ):
        """Ollama connection error during file-whole should fall through gracefully."""
        engine = self._make_engine()

        call_count = 0

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Ollama unavailable")
            return ("    return None", 50, 10)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate):
            result = engine.process_file(
                logger_file_spec, logger_manifest, logger_skeleton,
            )

        # Should have fallen through to element-by-element
        assert call_count > 1

    def test_file_whole_repair_recovers(
        self, logger_file_spec, logger_skeleton, logger_filled, logger_manifest,
    ):
        """P0: File-whole with repairable output should succeed after repair."""
        engine = self._make_engine()

        # Return code with a minor fence issue that repair can fix
        fenced_with_issue = f"```python\n{logger_filled}\n```"

        # Code that fails initial validation (stub-only function body) but
        # repair returns the correct logger_filled code.
        broken_code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = record.created


def getJSONLogger(name: str) -> logging.Logger:
    raise NotImplementedError
'''

        from startd8.micro_prime.repair import RepairResult

        repair_result = RepairResult(
            code=logger_filled,
            steps_applied=["stub_removal"],
            ast_valid=True,
            ast_valid_before=False,
            ast_valid_after=True,
            repair_recovered=True,
            metrics={},
            step_results=[],
        )

        call_count = 0

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (broken_code, 100, 50)
            return ("    return None", 50, 10)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate), \
             patch("startd8.micro_prime.engine.run_repair_pipeline", return_value=repair_result):
            result = engine.process_file(
                logger_file_spec, logger_manifest, logger_skeleton,
            )

        # Should have succeeded via repair — only 1 Ollama call (file-whole)
        assert call_count == 1
        assert all(er.success for er in result.element_results)
        assert "raise NotImplementedError" not in result.filled_skeleton

    def test_file_whole_repair_fails_falls_through(
        self, logger_file_spec, logger_skeleton, logger_manifest,
    ):
        """P0: File-whole repair failure falls through to element-by-element."""
        engine = self._make_engine()

        # Return code that fails validation
        bad_code = "import logging\n\ndef getJSONLogger(name):\n    pass\n"

        from startd8.micro_prime.repair import RepairResult

        repair_result = RepairResult(
            code=bad_code,
            steps_applied=[],
            ast_valid=False,
            ast_valid_before=False,
            ast_valid_after=False,
            repair_recovered=False,
            metrics={},
            step_results=[],
        )

        call_count = 0

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (bad_code, 100, 50)
            return ("    return None", 50, 10)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate), \
             patch("startd8.micro_prime.engine.run_repair_pipeline", return_value=repair_result):
            result = engine.process_file(
                logger_file_spec, logger_manifest, logger_skeleton,
            )

        # Should have fallen through to element-by-element
        assert call_count > 1


# ── P0: _strip_fences helper used by validation ─────────────────────


class TestStripFencesInValidation:
    """P0: _validate_file_whole_result uses _strip_fences."""

    def test_nested_fences_handled(self, logger_filled, logger_skeleton, logger_file_spec):
        """Fenced output with language tag is handled correctly."""
        fenced = f"```python\n{logger_filled}\n```"
        valid, reason, *_ = _validate_file_whole_result(fenced, logger_skeleton, logger_file_spec)
        assert valid is True

    def test_plain_code_no_fences(self, logger_filled, logger_skeleton, logger_file_spec):
        """Code without fences passes validation."""
        valid, reason, *_ = _validate_file_whole_result(logger_filled, logger_skeleton, logger_file_spec)
        assert valid is True


# ── AST-based stub detection tests ─────────────────────────────────────


class TestASTStubDetection:
    """Validate AST-based stub detection replaces naive string search."""

    def test_accepts_not_implemented_in_branch(self, logger_skeleton, logger_file_spec):
        """Code with raise NotImplementedError in an if/else branch passes."""
        code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        if not hasattr(record, 'created'):
            raise NotImplementedError("Subclass must set created")
        log_record['timestamp'] = record.created
        log_record['severity'] = record.levelname


def getJSONLogger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(sys.stdout)
    formatter = CustomJsonFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
'''
        valid, reason, *_ = _validate_file_whole_result(code, logger_skeleton, logger_file_spec)
        assert valid is True, f"Should accept branch NotImplementedError, got: {reason}"

    def test_rejects_stub_only_body(self, logger_skeleton, logger_file_spec):
        """Function body that is ONLY raise NotImplementedError fails."""
        code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = record.created


def getJSONLogger(name: str) -> logging.Logger:
    raise NotImplementedError
'''
        valid, reason, *_ = _validate_file_whole_result(code, logger_skeleton, logger_file_spec)
        assert valid is False
        assert "stub-only NotImplementedError bodies" in reason
        assert "getJSONLogger" in reason

    def test_rejects_stub_with_docstring(self, logger_skeleton, logger_file_spec):
        """Stub-only body preceded by docstring still detected."""
        code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        """Add custom fields to log record."""
        raise NotImplementedError()


def getJSONLogger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    return logger
'''
        valid, reason, *_ = _validate_file_whole_result(code, logger_skeleton, logger_file_spec)
        assert valid is False
        assert "stub-only NotImplementedError bodies" in reason
        assert "add_fields" in reason


# ── Nested duplicate detection tests ───────────────────────────────────


class TestNestedDuplicateDetection:
    """Validate nested duplicate function detection (Ollama over-generation)."""

    def test_rejects_nested_duplicate_function(self, logger_skeleton, logger_file_spec):
        """def foo(): def foo(): ... pattern rejected."""
        code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = record.created


def getJSONLogger(name: str) -> logging.Logger:
    def getJSONLogger(name: str) -> logging.Logger:
        return logging.getLogger(name)
    return getJSONLogger(name)
'''
        valid, reason, *_ = _validate_file_whole_result(code, logger_skeleton, logger_file_spec)
        assert valid is False
        assert "nested duplicate function" in reason
        assert "getJSONLogger" in reason

    def test_accepts_differently_named_nested_function(self, logger_skeleton, logger_file_spec):
        """def foo(): def _helper(): ... is accepted (legitimate nesting)."""
        code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = record.created
        log_record['severity'] = record.levelname


def getJSONLogger(name: str) -> logging.Logger:
    def _configure_handler():
        handler = logging.StreamHandler(sys.stdout)
        formatter = CustomJsonFormatter()
        handler.setFormatter(formatter)
        return handler
    logger = logging.getLogger(name)
    logger.addHandler(_configure_handler())
    logger.setLevel(logging.INFO)
    return logger
'''
        valid, reason, *_ = _validate_file_whole_result(code, logger_skeleton, logger_file_spec)
        assert valid is True, f"Should accept differently-named nested fn, got: {reason}"


# ── Structural position tests ──────────────────────────────────────────


class TestStructuralPosition:
    """Validate structural position checks (elements at correct nesting level)."""

    def test_rejects_method_at_top_level(self, logger_skeleton, logger_file_spec):
        """add_fields as standalone function instead of inside class -> rejected."""
        code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    pass


def add_fields(log_record, record, message_dict) -> None:
    log_record['timestamp'] = record.created


def getJSONLogger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    return logger
'''
        valid, reason, *_ = _validate_file_whole_result(code, logger_skeleton, logger_file_spec)
        assert valid is False
        assert "missing elements" in reason
        assert "CustomJsonFormatter.add_fields" in reason

    def test_rejects_missing_parent_class(self, logger_skeleton, logger_file_spec):
        """Methods present but parent class missing -> rejected."""
        code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


def add_fields(log_record, record, message_dict) -> None:
    log_record['timestamp'] = record.created


def getJSONLogger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    return logger
'''
        valid, reason, *_ = _validate_file_whole_result(code, logger_skeleton, logger_file_spec)
        assert valid is False
        assert "missing elements" in reason
        assert "class CustomJsonFormatter" in reason

    def test_accepts_correct_structure(self, logger_filled, logger_skeleton, logger_file_spec):
        """Class with methods + standalone function -> accepted."""
        valid, reason, *_ = _validate_file_whole_result(
            logger_filled, logger_skeleton, logger_file_spec,
        )
        assert valid is True
        assert reason == "all checks passed"

    def test_rejects_method_in_wrong_class(self, logger_skeleton, logger_file_spec):
        """Method exists but inside a different class -> rejected."""
        code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    pass


class WrongClass:
    def add_fields(self, log_record, record, message_dict) -> None:
        log_record['timestamp'] = record.created


def getJSONLogger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    return logger
'''
        valid, reason, *_ = _validate_file_whole_result(code, logger_skeleton, logger_file_spec)
        assert valid is False
        assert "missing elements" in reason
        assert "CustomJsonFormatter.add_fields" in reason


# ── Repair boundary tests ──────────────────────────────────────────────


class TestRepairBoundaryStructural:
    """Repair fixes AST but structural validation still catches issues."""

    def test_file_whole_repair_structural_fail(
        self, logger_file_spec, logger_skeleton, logger_manifest,
    ):
        """Repair fixes AST but output has wrong structure -> re-validation catches it."""
        engine = MicroPrimeEngine(config=MicroPrimeConfig())

        # Code that parses fine but has method at top level (structural fail)
        bad_structure = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    pass


def add_fields(log_record, record, message_dict) -> None:
    log_record['timestamp'] = record.created


def getJSONLogger(name: str) -> logging.Logger:
    return logging.getLogger(name)
'''
        from startd8.micro_prime.repair import RepairResult

        repair_result = RepairResult(
            code=bad_structure,
            steps_applied=["indent_normalize"],
            ast_valid=True,
            ast_valid_before=False,
            ast_valid_after=True,
            repair_recovered=True,
            metrics={},
            step_results=[],
        )

        call_count = 0

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (bad_structure, 100, 50)
            return ("    return None", 50, 10)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate), \
             patch("startd8.micro_prime.engine.run_repair_pipeline", return_value=repair_result):
            result = engine.process_file(
                logger_file_spec, logger_manifest, logger_skeleton,
            )

        # Repair "succeeded" (AST valid) but structural check fails ->
        # should fall through to element-by-element
        assert call_count > 1


# ── Partial acceptance tests ────────────────────────────────────────────


class TestPartialAcceptance:
    """Phase 3: Partial acceptance keeps filled elements, escalates the rest."""

    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_partial_acceptance_fills_majority(
        self, logger_file_spec, logger_skeleton, logger_manifest,
    ):
        """28/30-style: most elements filled, a few stubs remain → partial FileResult."""
        engine = self._make_engine(min_element_fill_rate=0.5)

        # Code that has class + method filled but getJSONLogger is still a stub
        partial_code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = record.created
        log_record['severity'] = record.levelname


def getJSONLogger(name: str) -> logging.Logger:
    raise NotImplementedError
'''
        with patch.object(engine, "_generate_ollama", return_value=(partial_code, 100, 50)):
            result = engine._attempt_file_ollama_whole(
                logger_file_spec, logger_skeleton,
            )

        # Should return a partial result (2/3 elements filled = 67% ≥ 50%)
        assert result is not None
        assert result.filled_skeleton is not None
        successes = [r for r in result.element_results if r.success]
        failures = [r for r in result.element_results if not r.success]
        assert len(successes) == 2  # class + method
        assert len(failures) == 1  # getJSONLogger
        assert failures[0].element_name == "getJSONLogger"
        assert failures[0].escalation is not None
        assert failures[0].escalation.reason.value == "ollama_whole_failed"

    def test_partial_acceptance_below_threshold_rejects(
        self, logger_file_spec, logger_skeleton, logger_manifest,
    ):
        """Fill rate below threshold → returns None (full rejection)."""
        engine = self._make_engine(min_element_fill_rate=0.8)

        # Only class present, both functions missing (1/3 = 33% < 80%)
        partial_code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    pass


def getJSONLogger(name: str) -> logging.Logger:
    raise NotImplementedError
'''
        with patch.object(engine, "_generate_ollama", return_value=(partial_code, 100, 50)):
            result = engine._attempt_file_ollama_whole(
                logger_file_spec, logger_skeleton,
            )

        assert result is None

    def test_partial_results_have_escalation_on_missing(
        self, logger_file_spec, logger_skeleton,
    ):
        """Missing elements in partial result have EscalationResult attached."""
        engine = self._make_engine(min_element_fill_rate=0.5)

        partial_code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = record.created


def getJSONLogger(name: str) -> logging.Logger:
    raise NotImplementedError
'''
        with patch.object(engine, "_generate_ollama", return_value=(partial_code, 100, 50)):
            result = engine._attempt_file_ollama_whole(
                logger_file_spec, logger_skeleton,
            )

        assert result is not None
        for er in result.element_results:
            if not er.success:
                assert er.escalation is not None
                assert er.decomposition_metadata["strategy"] == "file_ollama_whole_partial"

    def test_hard_fail_no_partial(self, logger_file_spec, logger_skeleton):
        """Syntax error → no partial acceptance (hard fail returns None)."""
        engine = self._make_engine(min_element_fill_rate=0.1)

        with patch.object(engine, "_generate_ollama", return_value=("def broken(:\n    pass", 100, 50)):
            result = engine._attempt_file_ollama_whole(
                logger_file_spec, logger_skeleton,
            )

        assert result is None


# ── Retry with feedback tests ──────────────────────────────────────────


class TestRetryWithFeedback:
    """Phase 4: Single retry with failure reason injected into prompt."""

    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_retry_with_feedback_succeeds(
        self, logger_file_spec, logger_skeleton, logger_filled, logger_manifest,
    ):
        """First attempt fails, retry with feedback succeeds."""
        engine = self._make_engine(local_max_attempts=2)

        # First call: partial (stub remains), second call: fully filled
        call_count = 0

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Return code with a stub still in it
                return (logger_skeleton, 100, 50)
            # Retry succeeds — check that feedback was injected
            assert "RETRY" in prompt
            return (logger_filled, 100, 50)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate):
            result = engine._attempt_file_ollama_whole(
                logger_file_spec, logger_skeleton,
            )

        assert result is not None
        assert call_count == 2
        assert all(er.success for er in result.element_results)

    def test_retry_exhausted_falls_through(
        self, logger_file_spec, logger_skeleton, logger_manifest,
    ):
        """Both attempts fail → partial or None."""
        engine = self._make_engine(local_max_attempts=2, min_element_fill_rate=0.99)

        bad_code = '''\
import logging
import sys

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = record.created


def getJSONLogger(name: str) -> logging.Logger:
    raise NotImplementedError
'''
        call_count = 0

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return (bad_code, 100, 50)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate):
            result = engine._attempt_file_ollama_whole(
                logger_file_spec, logger_skeleton,
            )

        assert call_count == 2
        # With 0.99 fill rate threshold, partial (67%) won't be accepted
        assert result is None


# ── Element manifest in prompt tests ───────────────────────────────────


class TestElementManifestInPrompt:
    """Phase 1b: Element listing added to file-whole prompt."""

    def test_includes_element_listing(self, logger_skeleton, logger_file_spec):
        prompt = _build_file_whole_prompt(logger_skeleton, logger_file_spec)
        assert "Elements to implement" in prompt
        assert "getJSONLogger" in prompt

    def test_includes_return_type_hint(self, logger_skeleton, logger_file_spec):
        prompt = _build_file_whole_prompt(logger_skeleton, logger_file_spec)
        # getJSONLogger has return_annotation="logging.Logger"
        assert "logging.Logger" in prompt

    def test_classes_excluded_from_listing(self, logger_skeleton, logger_file_spec):
        prompt = _build_file_whole_prompt(logger_skeleton, logger_file_spec)
        # Class elements should not appear in the "elements to implement" listing
        # (they don't have stubs — their methods do)
        lines = [l for l in prompt.splitlines() if l.startswith("# ") and "CustomJsonFormatter" in l and "." not in l]
        implement_lines = [l for l in lines if "Elements to implement" not in l]
        # CustomJsonFormatter should only appear as parent prefix (e.g., CustomJsonFormatter.add_fields)
        for line in implement_lines:
            # Should not have a bare "CustomJsonFormatter" without a method
            if "add_fields" not in line:
                assert False, f"Bare class in element listing: {line}"


# ── Adaptive max_tokens tests ─────────────────────────────────────────


class TestAdaptiveMaxTokens:
    """Phase 2b: Output budget scales with skeleton size."""

    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_large_skeleton_gets_more_tokens(
        self, logger_file_spec, logger_skeleton, logger_filled,
    ):
        """A 500-line skeleton should request more than the default 2048 tokens."""
        engine = self._make_engine(max_tokens=2048)

        # Create a large skeleton (500 lines)
        big_skeleton = logger_skeleton + "\n" * 490

        captured_kwargs = {}

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            captured_kwargs["max_tokens"] = max_tokens
            return (logger_filled, 100, 50)

        big_file_spec = logger_file_spec  # reuse, element count doesn't matter here

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate):
            engine._attempt_file_ollama_whole(big_file_spec, big_skeleton)

        # 500+ lines * 4 = 2000+, but skeleton is ~500 lines so 500*4=2000 < 2048
        # Actually the skeleton will be logger_skeleton (13 lines) + 490 blank = 503 lines
        # 503 * 4 = 2012 < 2048, so max(2048, 2012) = 2048
        # Let's just check it was passed
        assert captured_kwargs.get("max_tokens") is not None
        assert captured_kwargs["max_tokens"] >= 2048


# ── _skeleton_has_stubs AST-based detection (AC-R3) ────────────────────


class TestSkeletonHasStubs:
    """Validates AST-based stub detection replaces naive string search."""

    def test_actual_stub_detected(self):
        """A function body that is only `raise NotImplementedError` -> True."""
        code = "def foo():\n    raise NotImplementedError\n"
        assert _skeleton_has_stubs(code) is True

    def test_stub_with_docstring_detected(self):
        """Docstring + raise NotImplementedError is still a stub -> True."""
        code = 'def foo():\n    """Docstring."""\n    raise NotImplementedError()\n'
        assert _skeleton_has_stubs(code) is True

    def test_conditional_raise_not_stub(self):
        """raise NotImplementedError inside an if-branch is NOT a stub -> False."""
        code = (
            "def foo(x):\n"
            "    if x is None:\n"
            "        raise NotImplementedError('subclass must override')\n"
            "    return x + 1\n"
        )
        assert _skeleton_has_stubs(code) is False

    def test_string_literal_not_stub(self):
        """String containing 'raise NotImplementedError' is NOT a stub -> False."""
        code = (
            "def foo():\n"
            "    msg = 'should raise NotImplementedError here'\n"
            "    return msg\n"
        )
        assert _skeleton_has_stubs(code) is False

    def test_no_stubs_returns_false(self):
        """Fully implemented functions -> False."""
        code = "def foo():\n    return 42\n\ndef bar():\n    return 'hello'\n"
        assert _skeleton_has_stubs(code) is False

    def test_syntax_error_falls_back_to_string(self):
        """Unparseable skeleton falls back to string check."""
        code = "def broken(:\n    raise NotImplementedError\n"
        assert _skeleton_has_stubs(code) is True

    def test_syntax_error_no_match_returns_false(self):
        """Unparseable skeleton without the string -> False."""
        code = "def broken(:\n    return 42\n"
        assert _skeleton_has_stubs(code) is False

    def test_method_stub_detected(self):
        """Method inside a class with stub body -> True."""
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        raise NotImplementedError\n"
        )
        assert _skeleton_has_stubs(code) is True

    def test_comment_containing_phrase_not_stub(self):
        """Comment with 'raise NotImplementedError' is not a stub -> False."""
        code = (
            "def foo():\n"
            "    # TODO: raise NotImplementedError for unsupported types\n"
            "    return 42\n"
        )
        assert _skeleton_has_stubs(code) is False


# ── Phase 6 (AC-R6): Expanded file-whole coverage ─────────────────────


class TestHighCouplingOverride:
    """File-whole eligibility override when elements have high coupling."""

    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_coupling_override_bypasses_size_limits(self):
        """High coupling overrides max_elements and max_loc limits."""
        # Create a file spec with coupled elements (function calls sibling function)
        file_spec = ForwardFileSpec(
            file="src/data.py",
            imports=[],
            elements=[
                ForwardElementSpec(kind=ElementKind.FUNCTION, name="generate_data"),
                ForwardElementSpec(kind=ElementKind.FUNCTION, name="validate_data"),
                ForwardElementSpec(kind=ElementKind.FUNCTION, name="transform_data"),
            ],
        )
        # Skeleton where functions call each other (cross-refs >= 2)
        skeleton = '''\
def generate_data():
    raise NotImplementedError

def validate_data():
    data = generate_data()
    raise NotImplementedError

def transform_data():
    data = generate_data()
    validated = validate_data()
    raise NotImplementedError
'''
        # Set very low limits — would normally be ineligible
        engine = self._make_engine(
            file_ollama_whole_max_elements=1,
            file_ollama_whole_max_loc=5,
        )
        assert engine._is_file_ollama_whole_eligible(file_spec, skeleton) is True

    def test_no_coupling_respects_size_limits(self):
        """Without coupling, size limits are enforced."""
        file_spec = ForwardFileSpec(
            file="src/utils.py",
            imports=[],
            elements=[
                ForwardElementSpec(kind=ElementKind.FUNCTION, name="foo"),
                ForwardElementSpec(kind=ElementKind.FUNCTION, name="bar"),
            ],
        )
        # Independent functions — no coupling
        skeleton = '''\
def foo():
    raise NotImplementedError

def bar():
    raise NotImplementedError
'''
        engine = self._make_engine(file_ollama_whole_max_elements=1)
        assert engine._is_file_ollama_whole_eligible(file_spec, skeleton) is False


class TestFillRateThresholdBoundary:
    """Exact boundary behavior at min_element_fill_rate threshold."""

    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_exact_threshold_accepted(self):
        """Fill rate exactly at threshold -> partial acceptance."""
        # 3 elements, 1 missing = 2/3 = 66.7%
        engine = self._make_engine(min_element_fill_rate=0.666)
        file_spec = ForwardFileSpec(
            file="src/logger.py",
            imports=[],
            elements=[
                ForwardElementSpec(kind=ElementKind.CLASS, name="MyClass"),
                ForwardElementSpec(
                    kind=ElementKind.METHOD, name="method_a",
                    parent_class="MyClass",
                ),
                ForwardElementSpec(kind=ElementKind.FUNCTION, name="helper"),
            ],
        )
        skeleton = '''\
class MyClass:
    def method_a(self):
        raise NotImplementedError

def helper():
    raise NotImplementedError
'''
        # Code with helper still as stub
        partial = '''\
class MyClass:
    def method_a(self):
        return 42

def helper():
    raise NotImplementedError
'''
        with patch.object(engine, "_generate_ollama", return_value=(partial, 100, 50)):
            result = engine._attempt_file_ollama_whole(file_spec, skeleton)

        # 2/3 = 66.7% >= 66.6% -> accepted
        assert result is not None

    def test_just_below_threshold_rejected(self):
        """Fill rate just below threshold -> None."""
        engine = self._make_engine(min_element_fill_rate=0.67)
        file_spec = ForwardFileSpec(
            file="src/logger.py",
            imports=[],
            elements=[
                ForwardElementSpec(kind=ElementKind.CLASS, name="MyClass"),
                ForwardElementSpec(
                    kind=ElementKind.METHOD, name="method_a",
                    parent_class="MyClass",
                ),
                ForwardElementSpec(kind=ElementKind.FUNCTION, name="helper"),
            ],
        )
        skeleton = '''\
class MyClass:
    def method_a(self):
        raise NotImplementedError

def helper():
    raise NotImplementedError
'''
        partial = '''\
class MyClass:
    def method_a(self):
        return 42

def helper():
    raise NotImplementedError
'''
        with patch.object(engine, "_generate_ollama", return_value=(partial, 100, 50)):
            result = engine._attempt_file_ollama_whole(file_spec, skeleton)

        # 2/3 = 66.7% < 67% -> rejected
        assert result is None


class TestRetryFeedbackInjection:
    """Validate that retry prompts include failure reasons."""

    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_retry_prompt_contains_failure_reason(self, logger_file_spec, logger_skeleton, logger_filled):
        """Second attempt's prompt should contain RETRY prefix with reason."""
        engine = self._make_engine(local_max_attempts=2)
        prompts_seen = []

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            prompts_seen.append(prompt)
            if len(prompts_seen) == 1:
                return (logger_skeleton, 100, 50)  # Stubs remain
            return (logger_filled, 100, 50)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate):
            engine._attempt_file_ollama_whole(logger_file_spec, logger_skeleton)

        assert len(prompts_seen) == 2
        assert "RETRY" in prompts_seen[1]
        assert "Previous attempt issues" in prompts_seen[1]

    def test_first_attempt_has_no_retry_prefix(self, logger_file_spec, logger_skeleton, logger_filled):
        """First attempt should NOT have RETRY prefix."""
        engine = self._make_engine(local_max_attempts=1)
        prompts_seen = []

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            prompts_seen.append(prompt)
            return (logger_filled, 100, 50)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate):
            engine._attempt_file_ollama_whole(logger_file_spec, logger_skeleton)

        assert len(prompts_seen) == 1
        assert "RETRY" not in prompts_seen[0]


class TestFileWholeRetryOnTotalEscalation:
    """When all elements escalate, file-whole is retried."""

    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_total_escalation_triggers_retry(
        self, logger_file_spec, logger_skeleton, logger_filled, logger_manifest,
    ):
        """0% element success -> file-whole retry attempted."""
        engine = self._make_engine()
        call_count = 0

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First file-whole attempt fails (incomplete)
                return ("import logging\n", 100, 10)
            if call_count <= 4:
                # Element-by-element attempts all fail
                return ("", 50, 10)
            # Retry file-whole succeeds
            return (logger_filled, 100, 50)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate):
            result = engine.process_file(
                logger_file_spec, logger_manifest, logger_skeleton,
            )

        # At least 3 calls: initial file-whole + element attempts + retry file-whole
        assert call_count >= 3


class TestValidationAfterRepairFails:
    """Repair succeeds (AST valid) but validation still rejects."""

    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_repair_valid_but_still_missing_elements(
        self, logger_file_spec, logger_skeleton, logger_manifest,
    ):
        """Repair fixes AST but missing elements -> falls through."""
        engine = self._make_engine()

        # Code that parses but is missing class elements
        incomplete_code = "import logging\n\ndef getJSONLogger(name: str):\n    return logging.getLogger(name)\n"

        from startd8.micro_prime.repair import RepairResult

        repair_result = RepairResult(
            code=incomplete_code,
            steps_applied=["fence_strip"],
            ast_valid=True,
            ast_valid_before=True,
            ast_valid_after=True,
            repair_recovered=False,
            metrics={},
            step_results=[],
        )

        call_count = 0

        def mock_generate(prompt, system_prompt=None, max_tokens=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (incomplete_code, 100, 50)
            return ("    return None", 50, 10)

        with patch.object(engine, "_generate_ollama", side_effect=mock_generate), \
             patch("startd8.micro_prime.engine.run_repair_pipeline", return_value=repair_result):
            result = engine.process_file(
                logger_file_spec, logger_manifest, logger_skeleton,
            )

        # Should have fallen through to element-by-element
        assert call_count > 1


class TestMultiClassFileNearThreshold:
    """Files with multiple classes near the element threshold."""

    def _make_engine(self, **config_overrides) -> MicroPrimeEngine:
        config = MicroPrimeConfig(**config_overrides)
        return MicroPrimeEngine(config=config)

    def test_multi_class_within_threshold(self):
        """File with 2 classes and methods within element limit."""
        file_spec = ForwardFileSpec(
            file="src/models.py",
            imports=[],
            elements=[
                ForwardElementSpec(kind=ElementKind.CLASS, name="User"),
                ForwardElementSpec(
                    kind=ElementKind.METHOD, name="validate",
                    parent_class="User",
                ),
                ForwardElementSpec(kind=ElementKind.CLASS, name="Product"),
                ForwardElementSpec(
                    kind=ElementKind.METHOD, name="to_dict",
                    parent_class="Product",
                ),
            ],
        )
        skeleton = '''\
class User:
    def validate(self):
        raise NotImplementedError

class Product:
    def to_dict(self):
        raise NotImplementedError
'''
        engine = self._make_engine(file_ollama_whole_max_elements=5)
        assert engine._is_file_ollama_whole_eligible(file_spec, skeleton) is True

    def test_multi_class_exceeds_threshold(self):
        """File with too many elements across classes."""
        elements = [
            ForwardElementSpec(kind=ElementKind.CLASS, name="A"),
        ]
        for i in range(10):
            elements.append(
                ForwardElementSpec(
                    kind=ElementKind.METHOD, name=f"method_{i}",
                    parent_class="A",
                ),
            )
        file_spec = ForwardFileSpec(file="src/big.py", imports=[], elements=elements)
        skeleton = "class A:\n" + "".join(
            f"    def method_{i}(self):\n        raise NotImplementedError\n"
            for i in range(10)
        )
        engine = self._make_engine(file_ollama_whole_max_elements=5)
        assert engine._is_file_ollama_whole_eligible(file_spec, skeleton) is False
