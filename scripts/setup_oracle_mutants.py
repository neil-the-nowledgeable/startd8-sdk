#!/usr/bin/env python3
"""Setup script for S3 Oracle & Mutant Battery.

This script creates the directories under .startd8/bias_audit/ for the oracle
and mutants, copies pricing.proto to them, and generates the reference_server.js
and the 8 mutant server implementations.
"""

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_PROTO = REPO / "src" / "startd8" / "benchmark_matrix" / "behavioral" / "pricing.proto"
SRC_REF_SERVER = REPO / "tests" / "unit" / "benchmark_matrix" / "behavioral" / "fixtures" / "reference_pricing_server.js"

ORACLE_DIR = REPO / ".startd8" / "bias_audit" / "oracle"
MUTANTS_DIR = REPO / ".startd8" / "bias_audit" / "mutants"

def main():
    print("Setting up S3 directories...")
    ORACLE_DIR.mkdir(parents=True, exist_ok=True)
    MUTANTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Copying pricing.proto...")
    shutil.copy(SRC_PROTO, ORACLE_DIR / "pricing.proto")
    shutil.copy(SRC_PROTO, MUTANTS_DIR / "pricing.proto")

    print("Reading reference server template...")
    template = SRC_REF_SERVER.read_text(encoding="utf-8")

    # 1. Generate Oracle Reference Server
    oracle_header = (
        "// Provenance: Originally authored by Google Antigravity/Gemini as a correct reference server\n"
        "// for the pricing seed. Reviewed independently to verify it does not use float math or encode\n"
        "// Google-specific default assumptions. Re-implemented using exact BigInt decimal logic (M-T2.3).\n\n"
    )
    (ORACLE_DIR / "reference_server.js").write_text(oracle_header + template, encoding="utf-8")
    print(f"Generated oracle: {ORACLE_DIR / 'reference_server.js'}")

    # Helper function to generate and write a mutant
    def write_mutant(name: str, target: str, replacement: str, description: str):
        if target not in template:
            raise ValueError(f"Target pattern not found in template for mutant: {name}")
        mutated = template.replace(target, replacement)
        header = (
            f"// MUTANT: {name}\n"
            f"// Description: {description}\n"
            f"// Single-fault mutation injected for Step S3.\n\n"
        )
        dest_path = MUTANTS_DIR / f"{name}.js"
        dest_path.write_text(header + mutated, encoding="utf-8")
        print(f"Generated mutant: {dest_path}")

    # 2. mutant_rounding_default: default to HALF_EVEN instead of HALF_UP
    write_mutant(
        "mutant_rounding_default",
        "const mode = req.currency ? req.currency.rounding : 0;",
        "let mode = req.currency ? req.currency.rounding : 0;\n    if (mode === 0) mode = 2; // Treat unspecified rounding as HALF_EVEN",
        "Treat unspecified rounding mode as HALF_EVEN instead of HALF_UP"
    )

    # 3. mutant_half_up: round half down/nearest for 0.5 boundary
    write_mutant(
        "mutant_half_up",
        "  } else { /* HALF_UP / UNSPECIFIED */\n    if (rem2 >= factor) q += 1n;\n  }",
        "  } else { /* HALF_UP / UNSPECIFIED */\n    if (rem2 > factor) q += 1n; // mutant: round half down/nearest for 0.5 (off by one)\n  }",
        "Round half down/nearest on the 0.5 boundary for HALF_UP"
    )

    # 4. mutant_half_even: treat HALF_EVEN as HALF_UP
    write_mutant(
        "mutant_half_even",
        "  if (mode === 2 /* HALF_EVEN */) {\n    if (rem2 > factor || (rem2 === factor && q % 2n === 1n)) q += 1n;\n  } else { /* HALF_UP / UNSPECIFIED */",
        "  if (mode === 2 /* HALF_EVEN */) {\n    if (rem2 >= factor) q += 1n; // mutant: treat HALF_EVEN as HALF_UP\n  } else { /* HALF_UP / UNSPECIFIED */",
        "Treat HALF_EVEN rounding as HALF_UP"
    )

    # 5. mutant_strategy_default: bypass validation that strategy is required when discounts present
    write_mutant(
        "mutant_strategy_default",
        "    if (items.some((li) => (li.discounts || []).length > 0) && strategy === 0) {\n      return bad('strategy required when discounts present');\n    }",
        "    if (items.some((li) => (li.discounts || []).length > 0) && strategy === 0) {\n      // mutant: bypass strategy check when discounts present\n    }",
        "Bypass validation that discount strategy must be specified when discounts are present"
    )

    # 6. mutant_tier_limit: bypass validation of 1..4 tiers limit
    write_mutant(
        "mutant_tier_limit",
        "      for (const d of (li.discounts || [])) {\n        const n = (d.tier_factors || []).length;\n        if (n < 1 || n > 4) return bad('tiers must number 1..4');\n      }",
        "      for (const d of (li.discounts || [])) {\n        // mutant: do not validate tier limit\n      }",
        "Bypass validation that percentage/fixed discounts must have 1..4 tiers"
    )

    # 7. mutant_discount_cap: ignore maximum_amount discount cap
    write_mutant(
        "mutant_discount_cap",
        "          if (d.maximum_amount && d.maximum_amount !== '') {\n            const cap = parse(d.maximum_amount);\n            if (amt > cap) amt = cap;\n          }",
        "          if (d.maximum_amount && d.maximum_amount !== '') {\n            // mutant: ignore discount cap\n          }",
        "Ignore the maximum_amount cap limit on discount amounts"
    )

    # 8. mutant_tax_precedence: treat post-tax discounts (pre_tax=false) as pre-tax discounts (pre_tax=true)
    write_mutant(
        "mutant_tax_precedence",
        "      } else {\n        const grossBase = lineBase + pctOfScaled(lineBase, rate);\n        const dg = applyDiscounts(grossBase);\n        netTaxI = roundToInternal(dg, C, mode);\n        const onePlus = SCALE + rate / 100n;               // (1 + rate/100) at internal scale\n        netI = roundToInternal(div(netTaxI, onePlus), C, mode);\n        taxI = netTaxI - netI;\n        discBase = grossBase; discAfter = dg;\n      }",
        "      } else {\n        // mutant: treat post-tax discounts as pre-tax\n        const d = applyDiscounts(lineBase);\n        netI = roundToInternal(d, C, mode);\n        taxI = roundToInternal(pctOfScaled(netI, rate), C, mode);\n        netTaxI = netI + taxI;\n        discBase = lineBase; discAfter = d;\n      }",
        "Treat post-tax discounts (discounts_pre_tax=false) as pre-tax"
    )

    # 9. mutant_negative_validation: bypass validation of negative price/qty and zero qty
    write_mutant(
        "mutant_negative_validation",
        "      if (qty <= 0n || unit < 0n) return bad('non-positive quantity or negative price');",
        "      if (false) { // mutant: bypass validation\n        return bad('non-positive quantity or negative price');\n      }",
        "Bypass validation that unit price must be non-negative and quantity must be positive"
    )

    print("\nAll mutants successfully generated.")

if __name__ == "__main__":
    main()
