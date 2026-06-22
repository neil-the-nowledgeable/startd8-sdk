"""Independent canonical oracle fixtures.

These cases are derived from the canonical pricing spec, proto contract, and
canonicalization decisions. They intentionally do not import cohort-authored
suite artifacts from ``runs/**``.
"""

from __future__ import annotations


def amount(decimal: str) -> dict[str, str]:
    return {"decimal": decimal}


VALID_CASES = [
    {
        "name": "default_cascade_selects_lower_positive_candidate",
        "behavior_ids": ["B_PROMOTION_SELECTION", "B_DEFAULTS", "B_CASCADE_PERCENT", "B_TOTALS"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "cascade-promo",
                    "quantity": "1",
                    "unit_amount": amount("10.00"),
                    "comparison_unit_amount": amount("12.00"),
                    "candidate_unit_amount": amount("8.00"),
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["10", "5"],
                        }
                    ],
                }
            ],
        },
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "cascade-promo",
                    "quantity": "1",
                    "price_on_request": False,
                    "comparison_unit_amount": amount("12.00"),
                    "selected_unit_amount": amount("8.00"),
                    "promotion_applied": True,
                    "line_base_amount": amount("8.00"),
                    "reduction": {
                        "amount": amount("1.16"),
                        "percent_total": "14.5",
                        "percent_levels": ["10", "5"],
                    },
                    "line_due_amount": amount("6.84"),
                }
            ],
            "totals": {
                "base_amount": amount("8.00"),
                "reduction_amount": amount("1.16"),
                "due_amount": amount("6.84"),
                "price_on_request_count": 0,
            },
        },
    },
    {
        "name": "half_even_is_default_rounding_mode",
        "behavior_ids": ["B_ROUNDING_HALF_EVEN", "B_OUTPUT_ONLY_ROUNDING"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "half-even-boundary",
                    "quantity": "1",
                    "unit_amount": amount("1.005"),
                }
            ],
        },
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "half-even-boundary",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": amount("1.00"),
                    "promotion_applied": False,
                    "line_base_amount": amount("1.00"),
                    "reduction": {
                        "amount": amount("0.00"),
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": amount("1.00"),
                }
            ],
            "totals": {
                "base_amount": amount("1.00"),
                "reduction_amount": amount("0.00"),
                "due_amount": amount("1.00"),
                "price_on_request_count": 0,
            },
        },
    },
    {
        "name": "sum_strategy_adds_percent_levels_once",
        "behavior_ids": ["B_SUM_PERCENT", "B_STRATEGY_INPUT"],
        "request": {
            "currency_code": "USD",
            "discount_strategy": "DISCOUNT_STRATEGY_SUM",
            "lines": [
                {
                    "line_key": "sum-percent",
                    "quantity": "1",
                    "unit_amount": amount("100.00"),
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["10", "5"],
                        }
                    ],
                }
            ],
        },
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "sum-percent",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": amount("100.00"),
                    "promotion_applied": False,
                    "line_base_amount": amount("100.00"),
                    "reduction": {
                        "amount": amount("15.00"),
                        "percent_total": "15",
                        "percent_levels": ["10", "5"],
                    },
                    "line_due_amount": amount("85.00"),
                }
            ],
            "totals": {
                "base_amount": amount("100.00"),
                "reduction_amount": amount("15.00"),
                "due_amount": amount("85.00"),
                "price_on_request_count": 0,
            },
        },
    },
    {
        "name": "candidate_must_be_positive_and_lower_than_unit",
        "behavior_ids": ["B_PROMOTION_SELECTION", "B_MULTI_LINE_TOTALS"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "candidate-not-lower",
                    "quantity": "1",
                    "unit_amount": amount("5.00"),
                    "candidate_unit_amount": amount("6.00"),
                },
                {
                    "line_key": "candidate-lower",
                    "quantity": "1",
                    "unit_amount": amount("6.00"),
                    "candidate_unit_amount": amount("5.00"),
                },
            ],
        },
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "candidate-not-lower",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": amount("5.00"),
                    "promotion_applied": False,
                    "line_base_amount": amount("5.00"),
                    "reduction": {
                        "amount": amount("0.00"),
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": amount("5.00"),
                },
                {
                    "line_key": "candidate-lower",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": amount("5.00"),
                    "promotion_applied": True,
                    "line_base_amount": amount("5.00"),
                    "reduction": {
                        "amount": amount("0.00"),
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": amount("5.00"),
                },
            ],
            "totals": {
                "base_amount": amount("10.00"),
                "reduction_amount": amount("0.00"),
                "due_amount": amount("10.00"),
                "price_on_request_count": 0,
            },
        },
    },
    {
        "name": "fixed_reductions_apply_after_all_percent_reductions",
        "behavior_ids": ["B_PERCENT_THEN_FIXED", "B_REJECT_NEGATIVE_REMAINING"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "percent-then-fixed",
                    "quantity": "1",
                    "unit_amount": amount("100.00"),
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["10"],
                        },
                        {
                            "kind": "REDUCTION_KIND_FIXED_AMOUNT",
                            "amount": amount("5.00"),
                        },
                    ],
                }
            ],
        },
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "percent-then-fixed",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": amount("100.00"),
                    "promotion_applied": False,
                    "line_base_amount": amount("100.00"),
                    "reduction": {
                        "amount": amount("15.00"),
                        "percent_total": "10",
                        "percent_levels": ["10"],
                    },
                    "line_due_amount": amount("85.00"),
                }
            ],
            "totals": {
                "base_amount": amount("100.00"),
                "reduction_amount": amount("15.00"),
                "due_amount": amount("85.00"),
                "price_on_request_count": 0,
            },
        },
    },
    {
        "name": "exact_intermediate_arithmetic_precedes_output_quantization",
        "behavior_ids": ["B_EXACT_DECIMAL", "B_OUTPUT_ONLY_ROUNDING"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "exact-intermediate",
                    "quantity": "1",
                    "unit_amount": amount("10.015"),
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["10"],
                        }
                    ],
                }
            ],
        },
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "exact-intermediate",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": amount("10.02"),
                    "promotion_applied": False,
                    "line_base_amount": amount("10.02"),
                    "reduction": {
                        "amount": amount("1.00"),
                        "percent_total": "10",
                        "percent_levels": ["10"],
                    },
                    "line_due_amount": amount("9.01"),
                }
            ],
            "totals": {
                "base_amount": amount("10.02"),
                "reduction_amount": amount("1.00"),
                "due_amount": amount("9.01"),
                "price_on_request_count": 0,
            },
        },
    },
    {
        "name": "price_on_request_lines_are_excluded_from_numeric_totals",
        "behavior_ids": ["B_PRICE_ON_REQUEST", "B_TOTALS"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "numeric-line",
                    "quantity": "1",
                    "unit_amount": amount("10.00"),
                },
                {
                    "line_key": "por-line",
                    "quantity": "2",
                    "price_on_request": True,
                },
            ],
        },
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "numeric-line",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": amount("10.00"),
                    "promotion_applied": False,
                    "line_base_amount": amount("10.00"),
                    "reduction": {
                        "amount": amount("0.00"),
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": amount("10.00"),
                },
                {
                    "line_key": "por-line",
                    "quantity": "2",
                    "price_on_request": True,
                },
            ],
            "totals": {
                "base_amount": amount("10.00"),
                "reduction_amount": amount("0.00"),
                "due_amount": amount("10.00"),
                "price_on_request_count": 1,
            },
        },
    },
]


INVALID_CASES = [
    {
        "name": "rejects_fixed_reduction_overrun_after_percent",
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "fixed-overrun",
                    "quantity": "1",
                    "unit_amount": amount("10.00"),
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["50"],
                        },
                        {
                            "kind": "REDUCTION_KIND_FIXED_AMOUNT",
                            "amount": amount("6.00"),
                        },
                    ],
                }
            ],
        },
    },
    {
        "name": "rejects_empty_lines",
        "request": {
            "currency_code": "USD",
            "lines": [],
        },
    },
    {
        "name": "rejects_too_many_percent_levels",
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "too-many-percent-levels",
                    "quantity": "1",
                    "unit_amount": amount("10.00"),
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["1", "2", "3", "4", "5"],
                        }
                    ],
                }
            ],
        },
    },
]
