"""Hand-authored canonical calibration cases for the resolved pricing oracle.

Expected values are derived from canonical/spec.md and
canonical/canonicalization_decisions.md. This module deliberately does not
import authoring-run artifacts or model-generated suites.
"""


def _amount(decimal: str) -> dict:
    return {"decimal": decimal}


def _numeric_line(
    key: str,
    quantity: str,
    selected: str,
    base: str,
    reduction: str,
    due: str,
    *,
    promotion_applied: bool = False,
    percent_total: str = "0",
    percent_levels: list[str] | None = None,
    comparison: str | None = None,
) -> dict:
    line = {
        "line_key": key,
        "quantity": quantity,
        "price_on_request": False,
        "selected_unit_amount": _amount(selected),
        "promotion_applied": promotion_applied,
        "line_base_amount": _amount(base),
        "reduction": {
            "amount": _amount(reduction),
            "percent_total": percent_total,
            "percent_levels": percent_levels or [],
        },
        "line_due_amount": _amount(due),
    }
    if comparison is not None:
        line["comparison_unit_amount"] = _amount(comparison)
    return line


def _response(lines: list[dict], base: str, reduction: str, due: str, *, por_count: int = 0) -> dict:
    return {
        "currency_code": "USD",
        "lines": lines,
        "totals": {
            "base_amount": _amount(base),
            "reduction_amount": _amount(reduction),
            "due_amount": _amount(due),
            "price_on_request_count": por_count,
        },
    }


VALID_CASES = [
    {
        "name": "default_cascade_selects_lower_positive_candidate",
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "candidate-cascade",
                    "quantity": "3",
                    "unit_amount": _amount("10.00"),
                    "comparison_unit_amount": _amount("12.00"),
                    "candidate_unit_amount": _amount("8.00"),
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["10", "5"],
                        }
                    ],
                }
            ],
        },
        "expected_response": _response(
            [
                _numeric_line(
                    "candidate-cascade",
                    "3",
                    "8.00",
                    "24.00",
                    "3.48",
                    "20.52",
                    promotion_applied=True,
                    percent_total="14.5",
                    percent_levels=["10", "5"],
                    comparison="12.00",
                )
            ],
            "24.00",
            "3.48",
            "20.52",
        ),
    },
    {
        "name": "half_even_is_default_rounding_mode",
        "request": {
            "currency_code": "USD",
            "lines": [{"line_key": "half-even", "quantity": "1", "unit_amount": _amount("1.005")}],
        },
        "expected_response": _response(
            [_numeric_line("half-even", "1", "1.00", "1.00", "0.00", "1.00")],
            "1.00",
            "0.00",
            "1.00",
        ),
    },
    {
        "name": "half_even_rounds_odd_cent_up",
        "request": {
            "currency_code": "USD",
            "lines": [{"line_key": "half-even-up", "quantity": "1", "unit_amount": _amount("1.015")}],
        },
        "expected_response": _response(
            [_numeric_line("half-even-up", "1", "1.02", "1.02", "0.00", "1.02")],
            "1.02",
            "0.00",
            "1.02",
        ),
    },
    {
        "name": "sum_strategy_adds_percent_levels_once",
        "request": {
            "currency_code": "USD",
            "discount_strategy": "DISCOUNT_STRATEGY_SUM",
            "lines": [
                {
                    "line_key": "sum",
                    "quantity": "2",
                    "unit_amount": _amount("19.99"),
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["12.5", "7.5"],
                        }
                    ],
                }
            ],
        },
        "expected_response": _response(
            [
                _numeric_line(
                    "sum",
                    "2",
                    "19.99",
                    "39.98",
                    "8.00",
                    "31.98",
                    percent_total="20",
                    percent_levels=["12.5", "7.5"],
                )
            ],
            "39.98",
            "8.00",
            "31.98",
        ),
    },
    {
        "name": "candidate_must_be_positive_and_lower_than_unit",
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "candidate-equal",
                    "quantity": "1",
                    "unit_amount": _amount("10.00"),
                    "candidate_unit_amount": _amount("10.00"),
                }
            ],
        },
        "expected_response": _response(
            [_numeric_line("candidate-equal", "1", "10.00", "10.00", "0.00", "10.00")],
            "10.00",
            "0.00",
            "10.00",
        ),
    },
    {
        "name": "fixed_reductions_apply_after_all_percent_reductions",
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "fixed-after-percent",
                    "quantity": "1",
                    "unit_amount": _amount("100.00"),
                    "reductions": [
                        {"kind": "REDUCTION_KIND_PERCENT_LEVELS", "percent_levels": ["10"]},
                        {"kind": "REDUCTION_KIND_FIXED_AMOUNT", "amount": _amount("10.00")},
                    ],
                }
            ],
        },
        "expected_response": _response(
            [
                _numeric_line(
                    "fixed-after-percent",
                    "1",
                    "100.00",
                    "100.00",
                    "20.00",
                    "80.00",
                    percent_total="10",
                    percent_levels=["10"],
                )
            ],
            "100.00",
            "20.00",
            "80.00",
        ),
    },
    {
        "name": "exact_intermediate_arithmetic_precedes_output_quantization",
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "intermediate",
                    "quantity": "1",
                    "unit_amount": _amount("10.015"),
                    "reductions": [{"kind": "REDUCTION_KIND_PERCENT_LEVELS", "percent_levels": ["10"]}],
                }
            ],
        },
        "expected_response": _response(
            [
                _numeric_line(
                    "intermediate",
                    "1",
                    "10.02",
                    "10.02",
                    "1.00",
                    "9.01",
                    percent_total="10",
                    percent_levels=["10"],
                )
            ],
            "10.02",
            "1.00",
            "9.01",
        ),
    },
    {
        "name": "price_on_request_lines_are_excluded_from_numeric_totals",
        "request": {
            "currency_code": "USD",
            "lines": [
                {"line_key": "numeric", "quantity": "1", "unit_amount": _amount("7.00")},
                {"line_key": "por", "quantity": "2", "price_on_request": True},
            ],
        },
        "expected_response": _response(
            [
                _numeric_line("numeric", "1", "7.00", "7.00", "0.00", "7.00"),
                {"line_key": "por", "quantity": "2", "price_on_request": True},
            ],
            "7.00",
            "0.00",
            "7.00",
            por_count=1,
        ),
    },
    {
        "name": "multi_line_aggregation",
        "request": {
            "currency_code": "USD",
            "lines": [
                {"line_key": "first", "quantity": "1", "unit_amount": _amount("1.11")},
                {"line_key": "second", "quantity": "2", "unit_amount": _amount("2.22")},
            ],
        },
        "expected_response": _response(
            [
                _numeric_line("first", "1", "1.11", "1.11", "0.00", "1.11"),
                _numeric_line("second", "2", "2.22", "4.44", "0.00", "4.44"),
            ],
            "5.55",
            "0.00",
            "5.55",
        ),
    },
]


INVALID_CASES = [
    {"name": "rejects_empty_lines", "request": {"currency_code": "USD", "lines": []}},
    {
        "name": "rejects_missing_currency_for_numeric_line",
        "request": {"lines": [{"line_key": "no-currency", "quantity": "1", "unit_amount": _amount("1")}]},
    },
    {
        "name": "rejects_duplicate_line_key",
        "request": {
            "currency_code": "USD",
            "lines": [
                {"line_key": "duplicate", "quantity": "1", "unit_amount": _amount("1")},
                {"line_key": "duplicate", "quantity": "1", "unit_amount": _amount("2")},
            ],
        },
    },
    {
        "name": "rejects_non_positive_quantity",
        "request": {
            "currency_code": "USD",
            "lines": [{"line_key": "zero", "quantity": "0", "unit_amount": _amount("1")}],
        },
    },
    {
        "name": "rejects_malformed_decimal",
        "request": {
            "currency_code": "USD",
            "lines": [{"line_key": "bad-decimal", "quantity": "1", "unit_amount": _amount("NaN")}],
        },
    },
    {
        "name": "rejects_too_many_percent_levels",
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "too-many-levels",
                    "quantity": "1",
                    "unit_amount": _amount("10"),
                    "reductions": [
                        {"kind": "REDUCTION_KIND_PERCENT_LEVELS", "percent_levels": ["1", "2", "3", "4", "5"]}
                    ],
                }
            ],
        },
    },
    {
        "name": "rejects_fixed_reduction_overrun_after_percent",
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "overrun",
                    "quantity": "1",
                    "unit_amount": _amount("10"),
                    "reductions": [{"kind": "REDUCTION_KIND_FIXED_AMOUNT", "amount": _amount("11")}],
                }
            ],
        },
    },
    {
        "name": "rejects_price_on_request_numeric_input",
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "por-numeric",
                    "quantity": "1",
                    "price_on_request": True,
                    "unit_amount": _amount("1"),
                }
            ],
        },
    },
    {
        "name": "rejects_unknown_discount_strategy",
        "request": {
            "currency_code": "USD",
            "discount_strategy": "DISCOUNT_STRATEGY_UNKNOWN",
            "lines": [{"line_key": "unknown-strategy", "quantity": "1", "unit_amount": _amount("1")}],
        },
    },
]
