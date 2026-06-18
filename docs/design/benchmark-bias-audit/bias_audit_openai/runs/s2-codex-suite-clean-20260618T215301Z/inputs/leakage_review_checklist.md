# S1 Leakage Review Checklist

**Artifact under review:** `pricing-task-brief.md`  
**Status:** Preliminary automated review complete; pending reviewer sign-off  

## Reviewer Sign-Off

| Reviewer | Role | Blinded? | Date | Decision | Notes |
|---|---|---:|---|---|---|
| TBD | Human/domain reviewer | TBD | TBD | TBD |  |
| TBD | Non-OpenAI tool reviewer | TBD | TBD | TBD | Claude Code or equivalent. |
| TBD | Non-OpenAI tool reviewer | TBD | TBD | TBD | Gemini CLI or equivalent. |

## Preliminary Automated Review

**Date:** 2026-06-18  
**Reviewer:** Codex in repository context  
**Decision:** Pass after correction, pending independent human/non-OpenAI review.

Findings:

- No forbidden current pricing seed names were found as positive contract instructions. They appear only
  as forbidden examples.
- No current `pricing.proto`, `requirements_text`, `pricing_suite.py`, or prior G1-G7 expected outputs
  were found in the prompt templates.
- One leakage risk was corrected: S1 previously fixed `tax-rate data` as a required request input even
  though `OPEN-007` leaves tax scope and representation unresolved. The brief now says tax-related
  inputs are request-provided only if tax is included in the final task.
- One rounding nudge was corrected: the exact upstream product-quantity rounding mode is now kept in
  the traceability matrix, not the neutral prompt-visible brief.
- One weak source-authority issue was corrected: `OPEN-008` no longer relies on prior internal research
  language and now cites upstream discount-cap behavior directly.

## Checks

- [ ] Every FIXED item maps to upstream Liferay evidence or benchmark schema evidence.
- [ ] Every OPEN item remains unresolved in the brief.
- [ ] The brief does not include current pricing seed RPC names as positive instructions.
- [ ] The brief does not include current pricing seed field names as positive instructions.
- [ ] The brief does not include current `pricing.proto` text.
- [ ] The brief does not include current `requirements_text` prose.
- [ ] The brief does not include current `pricing_suite.py` expected outputs.
- [ ] The brief does not prescribe HALF_UP, HALF_EVEN, or a default rounding mode.
- [ ] The brief does not prescribe chain as the default discount strategy.
- [ ] The brief does not prescribe tax ordering or a tax flag name.
- [ ] The brief does not prescribe INVALID_ARGUMENT or any other gRPC status code.
- [ ] The brief does not prescribe Node.js unless the benchmark harness gate later fixes runtime.
- [ ] The brief does not contain Codex/OpenAI-specific wording, JSON-schema-first preferences,
      Responses API phrasing, AGENTS.md assumptions, or Codex file-edit workflow cues.
- [ ] The brief does not contain Claude-specific `CLAUDE.md` phrasing or repository instruction text.
- [ ] The brief does not contain Gemini/Google-specific authoring hints.

## Known Forbidden Positive Names

These names may appear only as leakage examples, not as requested contract names:

- `ComputeBasket`
- `PriceCart`
- `net_payable`
- `offer_unit_price`
- `tier_factors`
- `discounts_pre_tax`
- `finalPrice`
- `promoPrice`
- `discountPercentageLevel1`
- `discountPercentageLevel2`
- `discountPercentageLevel3`
- `discountPercentageLevel4`
