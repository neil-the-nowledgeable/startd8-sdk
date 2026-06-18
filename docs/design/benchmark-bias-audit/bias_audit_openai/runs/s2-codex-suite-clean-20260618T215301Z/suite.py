"""Behavioral suite data for the canonical resolved pricing calculator.

The module is intentionally self-contained: it defines RPC-shaped fixtures,
expected responses, expected invalid statuses, and a small Decimal oracle used
by local pytest-style checks. It does not import generated gRPC code or require
a live server.
"""

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP


INVALID_ARGUMENT = "INVALID_ARGUMENT"
OK = "OK"

ROUNDING_MAP = {
    "ROUNDING_MODE_UNSPECIFIED": ROUND_HALF_EVEN,
    "ROUNDING_MODE_HALF_EVEN": ROUND_HALF_EVEN,
    "ROUNDING_MODE_HALF_UP": ROUND_HALF_UP,
    "ROUNDING_MODE_DOWN": ROUND_DOWN,
}


VALID_CASES = [
    {
        "name": "default_cascade_selects_lower_positive_candidate",
        "behavior_ids": ["B_PROMOTION_SELECTION", "B_DEFAULTS", "B_CASCADE_PERCENT", "B_TOTALS"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-a",
                    "quantity": "3",
                    "unit_amount": {"decimal": "10.00"},
                    "comparison_unit_amount": {"decimal": "12.00"},
                    "candidate_unit_amount": {"decimal": "8.00"},
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["10", "5"],
                        }
                    ],
                }
            ],
        },
        "expected_status": OK,
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-a",
                    "quantity": "3",
                    "price_on_request": False,
                    "comparison_unit_amount": {"decimal": "12.00"},
                    "selected_unit_amount": {"decimal": "8.00"},
                    "promotion_applied": True,
                    "line_base_amount": {"decimal": "24.00"},
                    "reduction": {
                        "amount": {"decimal": "3.48"},
                        "percent_total": "14.5",
                        "percent_levels": ["10", "5"],
                    },
                    "line_due_amount": {"decimal": "20.52"},
                }
            ],
            "totals": {
                "base_amount": {"decimal": "24.00"},
                "reduction_amount": {"decimal": "3.48"},
                "due_amount": {"decimal": "20.52"},
                "price_on_request_count": 0,
            },
        },
        "mutant_behaviors_expected_to_fail": [
            "ignores candidate_unit_amount",
            "applies SUM when discount_strategy is unspecified",
            "rounds between percentage levels",
        ],
    },
    {
        "name": "sum_strategy_adds_percent_levels_once",
        "behavior_ids": ["B_SUM_PERCENT", "B_OUTPUT_ROUNDING"],
        "request": {
            "currency_code": "USD",
            "discount_strategy": "DISCOUNT_STRATEGY_SUM",
            "lines": [
                {
                    "line_key": "line-sum",
                    "quantity": "2",
                    "unit_amount": {"decimal": "19.99"},
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["12.5", "7.5"],
                        }
                    ],
                }
            ],
        },
        "expected_status": OK,
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-sum",
                    "quantity": "2",
                    "price_on_request": False,
                    "selected_unit_amount": {"decimal": "19.99"},
                    "promotion_applied": False,
                    "line_base_amount": {"decimal": "39.98"},
                    "reduction": {
                        "amount": {"decimal": "8.00"},
                        "percent_total": "20",
                        "percent_levels": ["12.5", "7.5"],
                    },
                    "line_due_amount": {"decimal": "31.98"},
                }
            ],
            "totals": {
                "base_amount": {"decimal": "39.98"},
                "reduction_amount": {"decimal": "8.00"},
                "due_amount": {"decimal": "31.98"},
                "price_on_request_count": 0,
            },
        },
        "mutant_behaviors_expected_to_fail": [
            "treats SUM as CASCADE",
            "omits aggregate percent output",
        ],
    },
    {
        "name": "fixed_reductions_apply_after_all_percent_reductions",
        "behavior_ids": ["B_FIXED_AFTER_PERCENT", "B_FIXED_AMOUNT", "B_TOTALS"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-fixed",
                    "quantity": "1",
                    "unit_amount": {"decimal": "100"},
                    "reductions": [
                        {"kind": "REDUCTION_KIND_FIXED_AMOUNT", "amount": {"decimal": "5"}},
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["10"],
                        },
                        {"kind": "REDUCTION_KIND_FIXED_AMOUNT", "amount": {"decimal": "7.50"}},
                    ],
                }
            ],
        },
        "expected_status": OK,
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-fixed",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": {"decimal": "100.00"},
                    "promotion_applied": False,
                    "line_base_amount": {"decimal": "100.00"},
                    "reduction": {
                        "amount": {"decimal": "22.50"},
                        "percent_total": "10",
                        "percent_levels": ["10"],
                    },
                    "line_due_amount": {"decimal": "77.50"},
                }
            ],
            "totals": {
                "base_amount": {"decimal": "100.00"},
                "reduction_amount": {"decimal": "22.50"},
                "due_amount": {"decimal": "77.50"},
                "price_on_request_count": 0,
            },
        },
        "mutant_behaviors_expected_to_fail": [
            "applies reductions strictly in request order",
            "treats fixed amounts as per-unit discounts",
        ],
    },
    {
        "name": "exact_intermediate_arithmetic_precedes_output_quantization",
        "behavior_ids": ["B_EXACT_DECIMAL", "B_OUTPUT_ONLY_ROUNDING", "B_FIXED_AMOUNT"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-exact",
                    "quantity": "3",
                    "unit_amount": {"decimal": "0.333"},
                    "reductions": [
                        {"kind": "REDUCTION_KIND_FIXED_AMOUNT", "amount": {"decimal": "0.009"}}
                    ],
                }
            ],
        },
        "expected_status": OK,
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-exact",
                    "quantity": "3",
                    "price_on_request": False,
                    "selected_unit_amount": {"decimal": "0.33"},
                    "promotion_applied": False,
                    "line_base_amount": {"decimal": "1.00"},
                    "reduction": {
                        "amount": {"decimal": "0.01"},
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": {"decimal": "0.99"},
                }
            ],
            "totals": {
                "base_amount": {"decimal": "1.00"},
                "reduction_amount": {"decimal": "0.01"},
                "due_amount": {"decimal": "0.99"},
                "price_on_request_count": 0,
            },
        },
        "mutant_behaviors_expected_to_fail": [
            "rounds unit amount before multiplying by quantity",
            "uses binary floating point arithmetic",
        ],
    },
    {
        "name": "half_even_is_default_rounding_mode",
        "behavior_ids": ["B_DEFAULTS", "B_ROUND_HALF_EVEN"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {"line_key": "line-even", "quantity": "1", "unit_amount": {"decimal": "1.005"}}
            ],
        },
        "expected_status": OK,
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-even",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": {"decimal": "1.00"},
                    "promotion_applied": False,
                    "line_base_amount": {"decimal": "1.00"},
                    "reduction": {
                        "amount": {"decimal": "0.00"},
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": {"decimal": "1.00"},
                }
            ],
            "totals": {
                "base_amount": {"decimal": "1.00"},
                "reduction_amount": {"decimal": "0.00"},
                "due_amount": {"decimal": "1.00"},
                "price_on_request_count": 0,
            },
        },
        "mutant_behaviors_expected_to_fail": ["defaults to HALF_UP instead of HALF_EVEN"],
    },
    {
        "name": "half_up_rounding_mode_is_honored",
        "behavior_ids": ["B_ROUND_HALF_UP"],
        "request": {
            "currency_code": "USD",
            "rounding_mode": "ROUNDING_MODE_HALF_UP",
            "lines": [
                {"line_key": "line-up", "quantity": "1", "unit_amount": {"decimal": "1.005"}}
            ],
        },
        "expected_status": OK,
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-up",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": {"decimal": "1.01"},
                    "promotion_applied": False,
                    "line_base_amount": {"decimal": "1.01"},
                    "reduction": {
                        "amount": {"decimal": "0.00"},
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": {"decimal": "1.01"},
                }
            ],
            "totals": {
                "base_amount": {"decimal": "1.01"},
                "reduction_amount": {"decimal": "0.00"},
                "due_amount": {"decimal": "1.01"},
                "price_on_request_count": 0,
            },
        },
        "mutant_behaviors_expected_to_fail": ["ignores explicit rounding_mode"],
    },
    {
        "name": "down_rounding_and_zero_scale_are_honored",
        "behavior_ids": ["B_ROUND_DOWN", "B_CURRENCY_SCALE"],
        "request": {
            "currency_code": "JPY",
            "currency_scale": 0,
            "rounding_mode": "ROUNDING_MODE_DOWN",
            "lines": [
                {"line_key": "line-down", "quantity": "1", "unit_amount": {"decimal": "9.99"}}
            ],
        },
        "expected_status": OK,
        "expected_response": {
            "currency_code": "JPY",
            "lines": [
                {
                    "line_key": "line-down",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": {"decimal": "9"},
                    "promotion_applied": False,
                    "line_base_amount": {"decimal": "9"},
                    "reduction": {
                        "amount": {"decimal": "0"},
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": {"decimal": "9"},
                }
            ],
            "totals": {
                "base_amount": {"decimal": "9"},
                "reduction_amount": {"decimal": "0"},
                "due_amount": {"decimal": "9"},
                "price_on_request_count": 0,
            },
        },
        "mutant_behaviors_expected_to_fail": [
            "always uses two fractional digits",
            "treats DOWN as HALF_EVEN",
        ],
    },
    {
        "name": "price_on_request_lines_are_excluded_from_numeric_totals",
        "behavior_ids": ["B_PRICE_ON_REQUEST", "B_TOTALS", "B_MULTI_LINE_ORDER"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {"line_key": "line-por", "quantity": "2", "price_on_request": True},
                {"line_key": "line-num", "quantity": "4", "unit_amount": {"decimal": "2.50"}},
            ],
        },
        "expected_status": OK,
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {"line_key": "line-por", "quantity": "2", "price_on_request": True},
                {
                    "line_key": "line-num",
                    "quantity": "4",
                    "price_on_request": False,
                    "selected_unit_amount": {"decimal": "2.50"},
                    "promotion_applied": False,
                    "line_base_amount": {"decimal": "10.00"},
                    "reduction": {
                        "amount": {"decimal": "0.00"},
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": {"decimal": "10.00"},
                },
            ],
            "totals": {
                "base_amount": {"decimal": "10.00"},
                "reduction_amount": {"decimal": "0.00"},
                "due_amount": {"decimal": "10.00"},
                "price_on_request_count": 1,
            },
        },
        "mutant_behaviors_expected_to_fail": [
            "requires unit_amount on price_on_request lines",
            "includes price_on_request lines in totals",
            "reorders response lines",
        ],
    },
    {
        "name": "candidate_must_be_positive_and_lower_than_unit",
        "behavior_ids": ["B_PROMOTION_SELECTION"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-candidate-zero",
                    "quantity": "1",
                    "unit_amount": {"decimal": "5.00"},
                    "candidate_unit_amount": {"decimal": "0.00"},
                },
                {
                    "line_key": "line-candidate-equal",
                    "quantity": "1",
                    "unit_amount": {"decimal": "5.00"},
                    "candidate_unit_amount": {"decimal": "5.00"},
                },
            ],
        },
        "expected_status": OK,
        "expected_response": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line-candidate-zero",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": {"decimal": "5.00"},
                    "promotion_applied": False,
                    "line_base_amount": {"decimal": "5.00"},
                    "reduction": {
                        "amount": {"decimal": "0.00"},
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": {"decimal": "5.00"},
                },
                {
                    "line_key": "line-candidate-equal",
                    "quantity": "1",
                    "price_on_request": False,
                    "selected_unit_amount": {"decimal": "5.00"},
                    "promotion_applied": False,
                    "line_base_amount": {"decimal": "5.00"},
                    "reduction": {
                        "amount": {"decimal": "0.00"},
                        "percent_total": "0",
                        "percent_levels": [],
                    },
                    "line_due_amount": {"decimal": "5.00"},
                },
            ],
            "totals": {
                "base_amount": {"decimal": "10.00"},
                "reduction_amount": {"decimal": "0.00"},
                "due_amount": {"decimal": "10.00"},
                "price_on_request_count": 0,
            },
        },
        "mutant_behaviors_expected_to_fail": [
            "accepts zero candidate as a promotion",
            "accepts equal candidate as a promotion",
        ],
    },
]


INVALID_CASES = [
    {
        "name": "rejects_empty_lines",
        "behavior_ids": ["B_VALIDATION_LINES"],
        "request": {"currency_code": "USD", "lines": []},
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["accepts empty requests"],
    },
    {
        "name": "rejects_duplicate_line_key",
        "behavior_ids": ["B_VALIDATION_LINE_KEY"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {"line_key": "dup", "quantity": "1", "unit_amount": {"decimal": "1"}},
                {"line_key": "dup", "quantity": "1", "unit_amount": {"decimal": "2"}},
            ],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["does not enforce line_key uniqueness"],
    },
    {
        "name": "rejects_missing_currency_for_numeric_line",
        "behavior_ids": ["B_VALIDATION_CURRENCY"],
        "request": {"lines": [{"line_key": "line", "quantity": "1", "unit_amount": {"decimal": "1"}}]},
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["defaults or ignores missing currency_code"],
    },
    {
        "name": "rejects_malformed_decimal",
        "behavior_ids": ["B_VALIDATION_DECIMAL"],
        "request": {
            "currency_code": "USD",
            "lines": [{"line_key": "line", "quantity": "1,000", "unit_amount": {"decimal": "1"}}],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["uses permissive decimal parsing"],
    },
    {
        "name": "rejects_nonpositive_quantity",
        "behavior_ids": ["B_VALIDATION_QUANTITY"],
        "request": {
            "currency_code": "USD",
            "lines": [{"line_key": "line", "quantity": "0", "unit_amount": {"decimal": "1"}}],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["allows zero quantity"],
    },
    {
        "name": "rejects_negative_amount",
        "behavior_ids": ["B_VALIDATION_AMOUNT"],
        "request": {
            "currency_code": "USD",
            "lines": [{"line_key": "line", "quantity": "1", "unit_amount": {"decimal": "-0.01"}}],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["allows negative unit_amount"],
    },
    {
        "name": "rejects_numeric_line_without_unit_amount",
        "behavior_ids": ["B_VALIDATION_NUMERIC_LINE"],
        "request": {"currency_code": "USD", "lines": [{"line_key": "line", "quantity": "1"}]},
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["treats absent unit_amount as zero"],
    },
    {
        "name": "rejects_price_on_request_with_numeric_inputs",
        "behavior_ids": ["B_VALIDATION_PRICE_ON_REQUEST"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line",
                    "quantity": "1",
                    "price_on_request": True,
                    "unit_amount": {"decimal": "1"},
                }
            ],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["ignores numeric inputs on price_on_request lines"],
    },
    {
        "name": "rejects_too_many_percent_levels",
        "behavior_ids": ["B_VALIDATION_PERCENT_LEVELS"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line",
                    "quantity": "1",
                    "unit_amount": {"decimal": "10"},
                    "reductions": [
                        {
                            "kind": "REDUCTION_KIND_PERCENT_LEVELS",
                            "percent_levels": ["1", "2", "3", "4", "5"],
                        }
                    ],
                }
            ],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["accepts more than four percentage levels"],
    },
    {
        "name": "rejects_percent_level_over_100",
        "behavior_ids": ["B_VALIDATION_PERCENT_RANGE"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line",
                    "quantity": "1",
                    "unit_amount": {"decimal": "10"},
                    "reductions": [
                        {"kind": "REDUCTION_KIND_PERCENT_LEVELS", "percent_levels": ["100.01"]}
                    ],
                }
            ],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["allows percentage levels greater than 100"],
    },
    {
        "name": "rejects_fixed_reduction_overrun_after_percent",
        "behavior_ids": ["B_VALIDATION_FIXED_OVERRUN", "B_FIXED_AFTER_PERCENT"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line",
                    "quantity": "1",
                    "unit_amount": {"decimal": "10"},
                    "reductions": [
                        {"kind": "REDUCTION_KIND_FIXED_AMOUNT", "amount": {"decimal": "6"}},
                        {"kind": "REDUCTION_KIND_PERCENT_LEVELS", "percent_levels": ["50"]},
                    ],
                }
            ],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": [
            "clamps fixed reduction overrun to zero",
            "applies fixed amount before percentage reductions",
        ],
    },
    {
        "name": "rejects_unknown_strategy",
        "behavior_ids": ["B_VALIDATION_ENUMS"],
        "request": {
            "currency_code": "USD",
            "discount_strategy": 99,
            "lines": [{"line_key": "line", "quantity": "1", "unit_amount": {"decimal": "1"}}],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["treats unknown discount_strategy as a default"],
    },
    {
        "name": "rejects_unknown_rounding_mode",
        "behavior_ids": ["B_VALIDATION_ENUMS"],
        "request": {
            "currency_code": "USD",
            "rounding_mode": 99,
            "lines": [{"line_key": "line", "quantity": "1", "unit_amount": {"decimal": "1"}}],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["treats unknown rounding_mode as a default"],
    },
    {
        "name": "rejects_unknown_reduction_kind",
        "behavior_ids": ["B_VALIDATION_ENUMS"],
        "request": {
            "currency_code": "USD",
            "lines": [
                {
                    "line_key": "line",
                    "quantity": "1",
                    "unit_amount": {"decimal": "1"},
                    "reductions": [{"kind": 99}],
                }
            ],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["ignores unknown reduction kinds"],
    },
    {
        "name": "rejects_negative_currency_scale",
        "behavior_ids": ["B_VALIDATION_CURRENCY_SCALE"],
        "request": {
            "currency_code": "USD",
            "currency_scale": -1,
            "lines": [{"line_key": "line", "quantity": "1", "unit_amount": {"decimal": "1"}}],
        },
        "expected_status": INVALID_ARGUMENT,
        "mutant_behaviors_expected_to_fail": ["accepts negative currency_scale"],
    },
]


def all_cases():
    return VALID_CASES + INVALID_CASES


def _parse_decimal(value):
    if not isinstance(value, str) or not value:
        raise ValueError("decimal value must be a non-empty string")
    if value.strip() != value or any(mark in value for mark in ("_", ",", "$")):
        raise ValueError("decimal value uses a forbidden representation")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("malformed decimal") from exc
    if not parsed.is_finite():
        raise ValueError("decimal must be finite")
    return parsed


def _amount(message):
    return _parse_decimal(message["decimal"])


def _currency_scale(request):
    scale = request.get("currency_scale", 2)
    if not isinstance(scale, int) or scale < 0:
        raise ValueError("currency_scale must be a non-negative integer")
    return scale


def _rounding(request):
    mode = request.get("rounding_mode", "ROUNDING_MODE_UNSPECIFIED")
    if mode not in ROUNDING_MAP:
        raise ValueError("unknown rounding mode")
    return ROUNDING_MAP[mode]


def _money(value, scale, rounding):
    quantum = Decimal(1).scaleb(-scale)
    return {"decimal": format(value.quantize(quantum, rounding=rounding), "f")}


def _percent_string(value, rounding):
    quantized = value.quantize(Decimal("0.000001"), rounding=rounding)
    return format(quantized.normalize(), "f")


def _percent_factor(levels, strategy):
    if not levels:
        return Decimal("1"), Decimal("0")
    percents = [_parse_decimal(level) for level in levels]
    if strategy == "DISCOUNT_STRATEGY_SUM":
        total = sum(percents, Decimal("0"))
        return Decimal("1") - (total / Decimal("100")), total
    remaining_factor = Decimal("1")
    for percent in percents:
        remaining_factor *= Decimal("1") - (percent / Decimal("100"))
    effective_percent = (Decimal("1") - remaining_factor) * Decimal("100")
    return remaining_factor, effective_percent


def expected_response_from_request(request):
    scale = _currency_scale(request)
    rounding = _rounding(request)
    strategy = request.get("discount_strategy", "DISCOUNT_STRATEGY_UNSPECIFIED")
    if strategy == "DISCOUNT_STRATEGY_UNSPECIFIED":
        strategy = "DISCOUNT_STRATEGY_CASCADE"
    if strategy not in ("DISCOUNT_STRATEGY_CASCADE", "DISCOUNT_STRATEGY_SUM"):
        raise ValueError("unknown discount strategy")

    response_lines = []
    total_base = Decimal("0")
    total_reduction = Decimal("0")
    total_due = Decimal("0")
    por_count = 0

    for line in request["lines"]:
        quantity = _parse_decimal(line["quantity"])
        if line.get("price_on_request", False):
            por_count += 1
            response_lines.append(
                {
                    "line_key": line["line_key"],
                    "quantity": line["quantity"],
                    "price_on_request": True,
                }
            )
            continue

        unit = _amount(line["unit_amount"])
        selected = unit
        promotion_applied = False
        if "candidate_unit_amount" in line:
            candidate = _amount(line["candidate_unit_amount"])
            if candidate > Decimal("0") and candidate < unit:
                selected = candidate
                promotion_applied = True

        base = selected * quantity
        percent_levels = []
        fixed_amounts = []
        for reduction in line.get("reductions", []):
            kind = reduction["kind"]
            if kind == "REDUCTION_KIND_PERCENT_LEVELS":
                percent_levels.extend(reduction.get("percent_levels", []))
            elif kind == "REDUCTION_KIND_FIXED_AMOUNT":
                fixed_amounts.append(_amount(reduction["amount"]))
            else:
                raise ValueError("unknown reduction kind")

        factor, effective_percent = _percent_factor(percent_levels, strategy)
        due = base * factor
        for fixed in fixed_amounts:
            due -= fixed
        reduction_amount = base - due

        response_line = {
            "line_key": line["line_key"],
            "quantity": line["quantity"],
            "price_on_request": False,
            "selected_unit_amount": _money(selected, scale, rounding),
            "promotion_applied": promotion_applied,
            "line_base_amount": _money(base, scale, rounding),
            "reduction": {
                "amount": _money(reduction_amount, scale, rounding),
                "percent_total": _percent_string(effective_percent, rounding),
                "percent_levels": percent_levels,
            },
            "line_due_amount": _money(due, scale, rounding),
        }
        if "comparison_unit_amount" in line:
            response_line["comparison_unit_amount"] = _money(
                _amount(line["comparison_unit_amount"]), scale, rounding
            )
        response_lines.append(response_line)
        total_base += base
        total_reduction += reduction_amount
        total_due += due

    return {
        "currency_code": request["currency_code"],
        "lines": response_lines,
        "totals": {
            "base_amount": _money(total_base, scale, rounding),
            "reduction_amount": _money(total_reduction, scale, rounding),
            "due_amount": _money(total_due, scale, rounding),
            "price_on_request_count": por_count,
        },
    }


def test_valid_case_expected_responses_match_decimal_oracle():
    for case in VALID_CASES:
        assert case["expected_status"] == OK, case["name"]
        assert expected_response_from_request(case["request"]) == case["expected_response"], case[
            "name"
        ]


def test_invalid_cases_expect_invalid_argument():
    for case in INVALID_CASES:
        assert case["expected_status"] == INVALID_ARGUMENT, case["name"]
        assert "expected_response" not in case, case["name"]


def test_case_names_are_unique():
    names = [case["name"] for case in all_cases()]
    assert len(names) == len(set(names))

