# S2 Canonicalization Decisions

**Date:** 2026-06-18  
**Status:** Adopted for initial suite authoring  

These decisions resolve the blockers identified in `../s2_preliminary_comparison.md`.

## Adopted Decisions

- Service and RPC names: `ResolvedPriceService.AssessLines`.
- Request message: `AssessLinesRequest`.
- Response message: `AssessLinesResponse`.
- Input line message: `ResolvedLine`.
- Output line message: `AssessedLine`.
- Money message: `Amount`.
- Discount input message: `Reduction`.
- Discount output message: `ReductionSummary`.
- Currency shape: request-level `currency_code`; all numeric lines use that currency.
- Price-on-application term: `price_on_request`.
- Fixed discount overrun: reject with `INVALID_ARGUMENT`; do not clamp to zero.
- Rounding: exact intermediate arithmetic and output-only monetary quantization.
- Default currency scale: `2`.
- Default rounding mode: `HALF_EVEN`.
- Supported rounding modes: `HALF_EVEN`, `HALF_UP`, and `DOWN`.
- Do not expose `round_after_each_reduction` in the primary pilot.

## Deferred From Primary Pilot

- Tax handling, tax-inclusive mirrors, and discount/tax ordering.
- Discount cap calculation and validation.
- Runtime language and startup command.
