"""Tests for Node.js / TypeScript signature string parser (REQ-EE-103)."""

from __future__ import annotations

import pytest

from startd8.utils.code_manifest import ElementKind, Visibility
from startd8.utils.nodejs_signature_parser import parse_nodejs_signatures


TARGET = "src/services/payment.js"


class TestBasicFunction:
    def test_plain_function(self) -> None:
        specs = parse_nodejs_signatures(
            ["function chargeServiceHandlers(charge)"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.FUNCTION
        assert s.name == "chargeServiceHandlers"
        assert s.signature is not None
        assert len(s.signature.params) == 1
        assert s.signature.params[0].name == "charge"
        assert s.decomposition_source == "parse-llm"

    def test_async_function(self) -> None:
        specs = parse_nodejs_signatures(["async function main()"], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.FUNCTION
        assert s.name == "main"
        assert s.signature is not None
        assert s.signature.params == []


class TestClass:
    def test_plain_class(self) -> None:
        specs = parse_nodejs_signatures(["class CurrencyConverter"], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "CurrencyConverter"
        assert s.bases == []
        assert s.is_abstract is False
        assert s.decomposition_source == "parse-llm"

    def test_class_with_extends(self) -> None:
        specs = parse_nodejs_signatures(
            ["class PaymentService extends BaseService"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "PaymentService"
        assert s.bases == ["BaseService"]

    def test_export_default_class(self) -> None:
        specs = parse_nodejs_signatures(
            ["export default class PaymentService"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "PaymentService"
        assert s.visibility == Visibility.PUBLIC


class TestArrowFunction:
    def test_arrow_function_assignment(self) -> None:
        specs = parse_nodejs_signatures(
            ["const convert = (from, to, amount) => Money"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.FUNCTION
        assert s.name == "convert"
        assert s.signature is not None
        assert s.decomposition_source == "parse-llm"


class TestExportedFunction:
    def test_export_function(self) -> None:
        specs = parse_nodejs_signatures(
            ["export function processPayment(request)"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.FUNCTION
        assert s.name == "processPayment"
        assert s.visibility == Visibility.PUBLIC
        assert s.signature is not None
        assert len(s.signature.params) == 1

    def test_export_async_function(self) -> None:
        specs = parse_nodejs_signatures(
            ["export async function handleRequest(req, res)"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.FUNCTION
        assert s.name == "handleRequest"
        assert s.signature is not None
        assert len(s.signature.params) == 2
        assert s.signature.params[0].name == "req"
        assert s.signature.params[1].name == "res"


class TestTypeScript:
    def test_ts_function_with_types(self) -> None:
        specs = parse_nodejs_signatures(
            ["export function processPayment(request: PaymentRequest): PaymentResponse"],
            TARGET,
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.FUNCTION
        assert s.name == "processPayment"
        assert s.signature is not None
        assert len(s.signature.params) == 1
        assert s.signature.params[0].name == "request"
        assert s.signature.params[0].annotation == "PaymentRequest"
        assert s.signature.return_annotation == "PaymentResponse"

    def test_ts_interface(self) -> None:
        specs = parse_nodejs_signatures(
            ["export interface PaymentConfig"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "PaymentConfig"
        assert s.is_abstract is True
        assert s.visibility == Visibility.PUBLIC

    def test_ts_type_alias(self) -> None:
        specs = parse_nodejs_signatures(
            ["export type Money = { units: number; nanos: number }"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "Money"


class TestSkipPatterns:
    def test_module_exports_skipped(self) -> None:
        specs = parse_nodejs_signatures(
            ["module.exports = { chargeServiceHandlers }"], TARGET
        )
        assert specs == []

    def test_exports_dot_skipped(self) -> None:
        specs = parse_nodejs_signatures(
            ["exports.handler = handler"], TARGET
        )
        assert specs == []


class TestEdgeCases:
    def test_empty_input(self) -> None:
        specs = parse_nodejs_signatures([], TARGET)
        assert specs == []

    def test_unparseable_garbage(self) -> None:
        specs = parse_nodejs_signatures(
            ["@#$%^&* not a signature at all"], TARGET
        )
        assert specs == []

    def test_blank_strings_skipped(self) -> None:
        specs = parse_nodejs_signatures(["", "  ", "\n"], TARGET)
        assert specs == []


class TestMultipleMixed:
    def test_mixed_signatures(self) -> None:
        sigs = [
            "function chargeServiceHandlers(charge)",
            "class CurrencyConverter",
            "export async function handleRequest(req, res)",
            "const convert = (from, to, amount) => Money",
            "module.exports = { chargeServiceHandlers }",
            "export interface PaymentConfig",
            "not a valid signature",
        ]
        specs = parse_nodejs_signatures(sigs, TARGET)
        # 5 valid (function, class, export async fn, arrow, interface)
        # 2 skipped (module.exports, garbage)
        assert len(specs) == 5
        names = [s.name for s in specs]
        assert "chargeServiceHandlers" in names
        assert "CurrencyConverter" in names
        assert "handleRequest" in names
        assert "convert" in names
        assert "PaymentConfig" in names
