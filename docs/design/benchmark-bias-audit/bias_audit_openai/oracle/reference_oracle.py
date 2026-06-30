"""Reference oracle for ResolvedPriceService.AssessLines (canonical pricing pilot)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP

# Mutation hooks — mutants override exactly one of these module-level flags.
DEFAULT_ROUNDING_MODE = ROUND_HALF_EVEN
DEFAULT_DISCOUNT_STRATEGY = "DISCOUNT_STRATEGY_CASCADE"
APPLY_FIXED_BEFORE_PERCENT = False
CANDIDATE_REQUIRES_STRICTLY_LOWER = True
USE_FLOAT_ARITHMETIC = False
ROUND_INTERMEDIATE = False
CLAMP_FIXED_OVERRUN = False
INCLUDE_POR_IN_TOTALS = False
FORCE_SUM_FOR_CASCADE = False
FORCE_CASCADE_FOR_SUM = False

ROUNDING_MAP = {
    "ROUNDING_MODE_UNSPECIFIED": ROUND_HALF_EVEN,
    "ROUNDING_MODE_HALF_EVEN": ROUND_HALF_EVEN,
    "ROUNDING_MODE_HALF_UP": ROUND_HALF_UP,
    "ROUNDING_MODE_DOWN": ROUND_DOWN,
}

VALID_DISCOUNT_STRATEGIES = {
    "DISCOUNT_STRATEGY_UNSPECIFIED",
    "DISCOUNT_STRATEGY_CASCADE",
    "DISCOUNT_STRATEGY_SUM",
}
VALID_REDUCTION_KINDS = {
    "REDUCTION_KIND_PERCENT_LEVELS",
    "REDUCTION_KIND_FIXED_AMOUNT",
}


def assess_lines(request: dict) -> dict:
    """Pure-function oracle: AssessLinesRequest dict → AssessLinesResponse dict."""
    _validate_request(request)
    return _build_response(request)


def _num(value: Decimal) -> Decimal | float:
    if USE_FLOAT_ARITHMETIC:
        return float(value)
    return value


def _add(a: Decimal | float, b: Decimal | float) -> Decimal | float:
    if USE_FLOAT_ARITHMETIC:
        return float(a) + float(b)
    return _num(Decimal(str(a)) + Decimal(str(b)))


def _sub(a: Decimal | float, b: Decimal | float) -> Decimal | float:
    if USE_FLOAT_ARITHMETIC:
        return float(a) - float(b)
    return _num(Decimal(str(a)) - Decimal(str(b)))


def _mul(a: Decimal | float, b: Decimal | float) -> Decimal | float:
    if USE_FLOAT_ARITHMETIC:
        return float(a) * float(b)
    return _num(Decimal(str(a)) * Decimal(str(b)))


def _lt(a: Decimal | float, b: Decimal | float) -> bool:
    return Decimal(str(a)) < Decimal(str(b))


def _parse_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty decimal string")
    if value.strip() != value:
        raise ValueError(f"{field} uses a forbidden representation")
    forbidden = ("_", ",", "$", "€", "£", "¥")
    if any(mark in value for mark in forbidden):
        raise ValueError(f"{field} uses a forbidden representation")
    lowered = value.lower()
    if "e" in lowered:
        raise ValueError(f"{field} uses a forbidden exponent/float-literal representation")
    if lowered in {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity"}:
        raise ValueError(f"{field} must be finite")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is malformed") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def _amount(message: object | None, *, field: str) -> Decimal:
    if not isinstance(message, dict) or "decimal" not in message:
        raise ValueError(f"{field} amount is required")
    return _parse_decimal(message["decimal"], field=field)


def _currency_scale(request: dict) -> int:
    if "currency_scale" not in request:
        return 2
    scale = request["currency_scale"]
    if not isinstance(scale, int) or isinstance(scale, bool):
        raise ValueError("currency_scale must be a non-negative integer")
    if scale < 0:
        raise ValueError("currency_scale must be non-negative")
    return scale


def _rounding_mode(request: dict):
    mode = request.get("rounding_mode", "ROUNDING_MODE_UNSPECIFIED")
    if mode not in ROUNDING_MAP:
        raise ValueError("unknown rounding mode")
    if mode == "ROUNDING_MODE_UNSPECIFIED":
        return DEFAULT_ROUNDING_MODE
    return ROUNDING_MAP[mode]


def _discount_strategy(request: dict) -> str:
    strategy = request.get("discount_strategy", "DISCOUNT_STRATEGY_UNSPECIFIED")
    if strategy not in VALID_DISCOUNT_STRATEGIES:
        raise ValueError("unknown discount strategy")
    if strategy == "DISCOUNT_STRATEGY_UNSPECIFIED":
        strategy = DEFAULT_DISCOUNT_STRATEGY
    if FORCE_SUM_FOR_CASCADE and strategy == "DISCOUNT_STRATEGY_CASCADE":
        return "DISCOUNT_STRATEGY_SUM"
    if FORCE_CASCADE_FOR_SUM and strategy == "DISCOUNT_STRATEGY_SUM":
        return "DISCOUNT_STRATEGY_CASCADE"
    return strategy


def _money(value: Decimal | float, scale: int, rounding) -> dict:
    dec = Decimal(str(value))
    quantum = Decimal(1).scaleb(-scale)
    return {"decimal": format(dec.quantize(quantum, rounding=rounding), "f")}


def _maybe_round_intermediate(value: Decimal | float, scale: int, rounding) -> Decimal | float:
    if not ROUND_INTERMEDIATE:
        return value
    dec = Decimal(str(value))
    quantum = Decimal(1).scaleb(-scale)
    return _num(dec.quantize(quantum, rounding=rounding))


def _percent_string(value: Decimal | float, rounding) -> str:
    dec = Decimal(str(value))
    quantized = dec.quantize(Decimal("0.000001"), rounding=rounding)
    return format(quantized.normalize(), "f")


def _percent_factor(levels: list[str], strategy: str) -> tuple[Decimal | float, Decimal | float]:
    if not levels:
        return _num(Decimal("1")), _num(Decimal("0"))
    percents = [_parse_decimal(level, field="percent level") for level in levels]
    if strategy == "DISCOUNT_STRATEGY_SUM":
        total = sum(percents, Decimal("0"))
        return _sub(Decimal("1"), _num(total / Decimal("100"))), _num(total)
    remaining_factor = Decimal("1")
    for percent in percents:
        remaining_factor *= Decimal("1") - (percent / Decimal("100"))
    effective_percent = (Decimal("1") - remaining_factor) * Decimal("100")
    return _num(remaining_factor), _num(effective_percent)


def _validate_request(request: dict) -> None:
    lines = request.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError("lines must contain at least one item")

    seen_keys: set[str] = set()
    has_numeric_line = False

    for line in lines:
        line_key = line.get("line_key")
        if not isinstance(line_key, str) or not line_key:
            raise ValueError("line_key is required")
        if line_key in seen_keys:
            raise ValueError("duplicate line_key")
        seen_keys.add(line_key)

        quantity = _parse_decimal(line["quantity"], field="quantity")
        if quantity <= Decimal("0"):
            raise ValueError("quantity must be greater than zero")

        if line.get("price_on_request", False):
            forbidden = ("unit_amount", "comparison_unit_amount", "candidate_unit_amount", "reductions")
            for field in forbidden:
                if field in line and (field != "reductions" or line.get("reductions")):
                    raise ValueError("price_on_request line cannot include numeric pricing inputs")
            continue

        has_numeric_line = True
        if "unit_amount" not in line:
            raise ValueError("numeric line requires unit_amount")

        unit = _amount(line["unit_amount"], field="unit_amount")
        if unit < Decimal("0"):
            raise ValueError("unit_amount must be non-negative")

        if "comparison_unit_amount" in line:
            comparison = _amount(line["comparison_unit_amount"], field="comparison_unit_amount")
            if comparison < Decimal("0"):
                raise ValueError("comparison_unit_amount must be non-negative")

        if "candidate_unit_amount" in line:
            candidate = _amount(line["candidate_unit_amount"], field="candidate_unit_amount")
            if candidate < Decimal("0"):
                raise ValueError("candidate_unit_amount must be non-negative")

        for reduction in line.get("reductions", []):
            kind = reduction.get("kind")
            if kind not in VALID_REDUCTION_KINDS:
                raise ValueError("unknown reduction kind")
            if kind == "REDUCTION_KIND_PERCENT_LEVELS":
                if "amount" in reduction:
                    raise ValueError("percentage reduction cannot include amount")
                levels = reduction.get("percent_levels", [])
                if not isinstance(levels, list) or len(levels) < 1 or len(levels) > 4:
                    raise ValueError("percentage reduction must have one to four levels")
                for level in levels:
                    parsed = _parse_decimal(level, field="percent level")
                    if parsed < Decimal("0") or parsed > Decimal("100"):
                        raise ValueError("percent level must be between 0 and 100 inclusive")
            elif kind == "REDUCTION_KIND_FIXED_AMOUNT":
                if reduction.get("percent_levels"):
                    raise ValueError("fixed amount reduction cannot include percent_levels")
                fixed = _amount(reduction.get("amount"), field="fixed reduction amount")
                if fixed < Decimal("0"):
                    raise ValueError("fixed reduction amount must be non-negative")

    if has_numeric_line and not request.get("currency_code"):
        raise ValueError("currency_code is required when numeric lines are present")

    _currency_scale(request)
    _rounding_mode(request)
    _discount_strategy(request)


def _selected_unit(line: dict) -> tuple[Decimal | float, bool]:
    unit = _amount(line["unit_amount"], field="unit_amount")
    selected = _num(unit)
    promotion_applied = False
    if "candidate_unit_amount" in line:
        candidate = _amount(line["candidate_unit_amount"], field="candidate_unit_amount")
        if candidate > Decimal("0"):
            if CANDIDATE_REQUIRES_STRICTLY_LOWER:
                if candidate < unit:
                    selected = _num(candidate)
                    promotion_applied = True
            else:
                selected = _num(candidate)
                promotion_applied = True
    return selected, promotion_applied


def _apply_reductions(
    base: Decimal | float,
    reductions: list[dict],
    strategy: str,
    *,
    scale: int,
    rounding,
) -> tuple[Decimal | float, Decimal | float, list[str], Decimal | float]:
    percent_levels: list[str] = []
    fixed_amounts: list[Decimal | float] = []

    for reduction in reductions:
        kind = reduction["kind"]
        if kind == "REDUCTION_KIND_PERCENT_LEVELS":
            percent_levels.extend(reduction["percent_levels"])
        else:
            fixed_amounts.append(_num(_amount(reduction["amount"], field="fixed reduction amount")))

    if APPLY_FIXED_BEFORE_PERCENT:
        due = base
        for fixed in fixed_amounts:
            due = _maybe_round_intermediate(_sub(due, fixed), scale, rounding)
            if _lt(due, Decimal("0")):
                if CLAMP_FIXED_OVERRUN:
                    due = _num(Decimal("0"))
                else:
                    raise ValueError("fixed reduction would make line amount negative")
        factor, effective_percent = _percent_factor(percent_levels, strategy)
        due = _maybe_round_intermediate(_mul(due, factor), scale, rounding)
    else:
        factor, effective_percent = _percent_factor(percent_levels, strategy)
        due = _maybe_round_intermediate(_mul(base, factor), scale, rounding)
        for fixed in fixed_amounts:
            due = _maybe_round_intermediate(_sub(due, fixed), scale, rounding)
            if _lt(due, Decimal("0")):
                if CLAMP_FIXED_OVERRUN:
                    due = _num(Decimal("0"))
                else:
                    raise ValueError("fixed reduction would make line amount negative")

    reduction_amount = _sub(base, due)
    return due, reduction_amount, percent_levels, effective_percent


def _assess_numeric_line(
    line: dict,
    *,
    strategy: str,
    scale: int,
    rounding,
) -> tuple[dict, Decimal | float, Decimal | float, Decimal | float]:
    selected, promotion_applied = _selected_unit(line)
    quantity = _num(_parse_decimal(line["quantity"], field="quantity"))
    base = _maybe_round_intermediate(_mul(selected, quantity), scale, rounding)
    due, reduction_amount, percent_levels, effective_percent = _apply_reductions(
        base,
        line.get("reductions", []),
        strategy,
        scale=scale,
        rounding=rounding,
    )
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
            _amount(line["comparison_unit_amount"], field="comparison_unit_amount"),
            scale,
            rounding,
        )
    return response_line, base, reduction_amount, due


def _build_response(request: dict) -> dict:
    scale = _currency_scale(request)
    rounding = _rounding_mode(request)
    strategy = _discount_strategy(request)

    response_lines = []
    total_base = _num(Decimal("0"))
    total_reduction = _num(Decimal("0"))
    total_due = _num(Decimal("0"))
    por_count = 0

    for line in request["lines"]:
        if line.get("price_on_request", False):
            por_count += 1
            response_lines.append(
                {
                    "line_key": line["line_key"],
                    "quantity": line["quantity"],
                    "price_on_request": True,
                }
            )
            if INCLUDE_POR_IN_TOTALS:
                qty = _num(_parse_decimal(line["quantity"], field="quantity"))
                total_base = _add(total_base, qty)
                total_due = _add(total_due, qty)
            continue

        response_line, base, reduction_amount, due = _assess_numeric_line(
            line,
            strategy=strategy,
            scale=scale,
            rounding=rounding,
        )
        response_lines.append(response_line)
        total_base = _add(total_base, base)
        total_reduction = _add(total_reduction, reduction_amount)
        total_due = _add(total_due, due)

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
