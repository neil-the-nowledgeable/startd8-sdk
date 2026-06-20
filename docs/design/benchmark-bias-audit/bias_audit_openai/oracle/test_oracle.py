"""Oracle and mutant calibration tests for the canonical pricing calculator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from conftest import get_oracle_module


AUDIT_ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = (
    AUDIT_ROOT
    / "runs/s2-codex-suite-clean-20260618T215301Z/suite.py"
)


def _load_suite_cases():
    spec = importlib.util.spec_from_file_location("codex_suite", SUITE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.VALID_CASES, module.INVALID_CASES


VALID_CASES, INVALID_CASES = _load_suite_cases()


def _assess(request, pytestconfig):
    oracle = get_oracle_module(pytestconfig)
    return oracle.assess_lines(request)


@pytest.mark.parametrize("case", VALID_CASES, ids=[case["name"] for case in VALID_CASES])
def test_valid_case(case, pytestconfig):
    assert _assess(case["request"], pytestconfig) == case["expected_response"]


@pytest.mark.parametrize("case", INVALID_CASES, ids=[case["name"] for case in INVALID_CASES])
def test_invalid_case(case, pytestconfig):
    with pytest.raises(ValueError):
        _assess(case["request"], pytestconfig)


def test_oracle_no_external_state(pytestconfig):
    """FIXED-001 probe: oracle is a pure function with no I/O."""
    case = next(case for case in VALID_CASES if case["name"] == "default_cascade_selects_lower_positive_candidate")
    first = _assess(case["request"], pytestconfig)
    second = _assess(case["request"], pytestconfig)
    assert first == second


def test_rounding_half_even_boundary(pytestconfig):
    """OPEN-003 probe: default HALF_EVEN rounding at .005 boundary."""
    case = next(case for case in VALID_CASES if case["name"] == "half_even_is_default_rounding_mode")
    assert _assess(case["request"], pytestconfig) == case["expected_response"]


def test_cascade_default_strategy(pytestconfig):
    """OPEN-005 probe: omitted discount_strategy defaults to CASCADE."""
    case = next(
        case for case in VALID_CASES if case["name"] == "default_cascade_selects_lower_positive_candidate"
    )
    assert _assess(case["request"], pytestconfig) == case["expected_response"]


def test_sum_strategy_distinct_from_cascade(pytestconfig):
    """OPEN-005 probe: SUM aggregates percentage levels once."""
    case = next(case for case in VALID_CASES if case["name"] == "sum_strategy_adds_percent_levels_once")
    assert _assess(case["request"], pytestconfig) == case["expected_response"]


def test_promo_selection_strictly_lower(pytestconfig):
    """OPEN-006 probe: candidate must be positive and lower than unit amount."""
    case = next(
        case for case in VALID_CASES if case["name"] == "candidate_must_be_positive_and_lower_than_unit"
    )
    assert _assess(case["request"], pytestconfig) == case["expected_response"]


def test_fixed_after_percent_ordering(pytestconfig):
    """OPEN-004 probe: fixed reductions apply after all percentage reductions."""
    case = next(
        case for case in VALID_CASES if case["name"] == "fixed_reductions_apply_after_all_percent_reductions"
    )
    assert _assess(case["request"], pytestconfig) == case["expected_response"]


def test_output_only_rounding(pytestconfig):
    """OPEN-003 probe: intermediate arithmetic stays exact until response quantization."""
    case = next(
        case
        for case in VALID_CASES
        if case["name"] == "exact_intermediate_arithmetic_precedes_output_quantization"
    )
    assert _assess(case["request"], pytestconfig) == case["expected_response"]


def test_price_on_request_excluded_from_totals(pytestconfig):
    """OPEN-007 probe: price-on-request lines are excluded from numeric totals."""
    case = next(
        case for case in VALID_CASES if case["name"] == "price_on_request_lines_are_excluded_from_numeric_totals"
    )
    assert _assess(case["request"], pytestconfig) == case["expected_response"]


def test_fixed_overrun_rejects_instead_of_clamping(pytestconfig):
    """OPEN-008 probe: fixed reduction overrun is INVALID_ARGUMENT, not clamped."""
    case = next(
        case for case in INVALID_CASES if case["name"] == "rejects_fixed_reduction_overrun_after_percent"
    )
    with pytest.raises(ValueError):
        _assess(case["request"], pytestconfig)


def test_invalid_argument_taxonomy(pytestconfig):
    """OPEN-009 probe: validation failures raise ValueError (INVALID_ARGUMENT mapping)."""
    case = next(case for case in INVALID_CASES if case["name"] == "rejects_empty_lines")
    with pytest.raises(ValueError):
        _assess(case["request"], pytestconfig)


def test_multi_line_aggregation(pytestconfig):
    """OPEN-010 probe: request totals aggregate multiple numeric lines."""
    case = next(
        case for case in VALID_CASES if case["name"] == "candidate_must_be_positive_and_lower_than_unit"
    )
    assert _assess(case["request"], pytestconfig)["totals"]["base_amount"]["decimal"] == "10.00"


def test_output_detail_fields(pytestconfig):
    """OPEN-011 probe: response includes selected unit, base, reduction summary, and due amount."""
    case = next(case for case in VALID_CASES if case["name"] == "default_cascade_selects_lower_positive_candidate")
    response = _assess(case["request"], pytestconfig)
    line = response["lines"][0]
    assert {"selected_unit_amount", "line_base_amount", "reduction", "line_due_amount"} <= set(line)


def test_contract_names_and_field_shapes(pytestconfig):
    """OPEN-001 probe: response mirrors canonical proto field names."""
    case = next(case for case in VALID_CASES if case["name"] == "default_cascade_selects_lower_positive_candidate")
    response = _assess(case["request"], pytestconfig)
    assert {"currency_code", "lines", "totals"} <= set(response)
    assert {"base_amount", "reduction_amount", "due_amount", "price_on_request_count"} <= set(
        response["totals"]
    )


def test_money_decimal_representation(pytestconfig):
    """OPEN-002 probe: monetary values are Amount { decimal } string messages."""
    case = next(case for case in VALID_CASES if case["name"] == "default_cascade_selects_lower_positive_candidate")
    amount = _assess(case["request"], pytestconfig)["lines"][0]["line_due_amount"]
    assert set(amount) == {"decimal"}
    assert isinstance(amount["decimal"], str)


def test_exact_decimal_arithmetic(pytestconfig):
    """FIXED-008 probe: arithmetic uses exact decimals, not binary floats."""
    case = next(
        case
        for case in VALID_CASES
        if case["name"] == "exact_intermediate_arithmetic_precedes_output_quantization"
    )
    assert _assess(case["request"], pytestconfig) == case["expected_response"]


def test_tax_handling_deferred(pytestconfig):
    """OPEN-007 probe: tax fields are absent from the primary-pilot contract."""
    case = next(case for case in VALID_CASES if case["name"] == "default_cascade_selects_lower_positive_candidate")
    response = _assess(case["request"], pytestconfig)
    assert "tax" not in str(response).lower()


def test_decimal_precision_not_binary_float(pytestconfig):
    """FIXED-008 / float-arithmetic mutant probe: binary float changes quantized base amount."""
    request = {
        "currency_code": "USD",
        "lines": [{"line_key": "float-probe", "quantity": "3", "unit_amount": {"decimal": "0.335"}}],
    }
    response = _assess(request, pytestconfig)
    assert response["lines"][0]["line_base_amount"]["decimal"] == "1.00"


def test_intermediate_rounding_changes_cascade_result(pytestconfig):
    """OPEN-003 / round-intermediate mutant probe: percent applied after quantized base."""
    request = {
        "currency_code": "USD",
        "lines": [
            {
                "line_key": "round-probe",
                "quantity": "1",
                "unit_amount": {"decimal": "10.015"},
                "reductions": [
                    {"kind": "REDUCTION_KIND_PERCENT_LEVELS", "percent_levels": ["10"]},
                ],
            }
        ],
    }
    response = _assess(request, pytestconfig)
    assert response["lines"][0]["line_due_amount"]["decimal"] == "9.01"


def test_runtime_packaging_out_of_scope(pytestconfig):
    """OPEN-012 probe: oracle is importable without server startup metadata."""
    oracle = get_oracle_module(pytestconfig)
    assert callable(oracle.assess_lines)
