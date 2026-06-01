#!/usr/bin/env python3
"""SG-1 + SG-3 confirmation against the REAL strtd8 target.

Tests whether the *existing* SDK code (prisma_parser + prisma_zod_symmetry) already
covers the two gates the spike proposed to build:
  SG-1: extract Prisma facts (models/fields/types/constraints)
  SG-3: bind Zod<->Prisma (CONFORMS_TO) and diff field sets

Acceptance: the existing checker must (a) flag the RUN_009 #13 drift (ProofPointSchema
with invented `claim`/`category`) and (b) NOT flag a coherent ProofPoint Zod schema.
"""
import sys
from pathlib import Path

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.validators.prisma_zod_symmetry import evaluate_cross_file_integrity, has_errors

SCHEMA = Path("/Users/neilyashinsky/Documents/dev/strtd8/strtd8/prisma/schema.prisma")

# RUN_009 #13: ProofPointSchema invents `claim`/`category` (not in the Prisma model)
BAD_ZOD = """
import { z } from 'zod';
export const ProofPointSchema = z.object({
  id: z.string(),
  title: z.string().optional(),
  claim: z.string(),
  category: z.string(),
});
"""

# Coherent: only fields that exist on the real ProofPoint model
GOOD_ZOD = """
import { z } from 'zod';
export const ProofPointSchema = z.object({
  id: z.string(),
  title: z.string().optional(),
  description: z.string().optional(),
});
"""


def main() -> int:
    text = SCHEMA.read_text()

    # --- SG-1: Prisma fact extraction on the real schema ---
    schema = parse_prisma_schema(text)
    models = schema.models  # dict: name -> PrismaModel
    print(f"[SG-1] parsed {len(models)} models: {sorted(models)}")
    pp = models.get("ProofPoint")
    ac = models.get("AiCall")
    pp_fields = {f.name for f in pp.fields} if pp else set()
    ac_fields = {f.name for f in ac.fields} if ac else set()
    print(f"[SG-1] ProofPoint fields: {sorted(pp_fields)}")
    print(f"[SG-1] AiCall fields: {sorted(ac_fields)}")
    sg1_ok = (
        bool(models)
        and {"claim", "category"}.isdisjoint(pp_fields)              # #13 source: not in model
        and {"promptTokens", "responseTokens"} <= ac_fields           # #12 source
        and {"inputTokens", "outputTokens"}.isdisjoint(ac_fields)
    )
    print(f"[SG-1] facts correct (model lacks claim/category; AiCall has prompt/responseTokens): {sg1_ok}")

    # --- SG-3: CONFORMS_TO binding + field-set diff (existing evaluate_cross_file_integrity) ---
    bad = evaluate_cross_file_integrity({"prisma/schema.prisma": text, "lib/bad.ts": BAD_ZOD})
    good = evaluate_cross_file_integrity({"prisma/schema.prisma": text, "lib/good.ts": GOOD_ZOD})

    bad_fields = {v.field for v in bad if getattr(v, "field", None)}
    print(f"[SG-3] BAD  Zod -> {len(bad)} violations, has_errors={has_errors(bad)}; fields flagged: {sorted(bad_fields)}")
    for v in bad:
        print(f"        - {getattr(v,'kind','?')}: {getattr(v,'field','?')} ({getattr(v,'severity','?')})")
    print(f"[SG-3] GOOD Zod -> {len(good)} violations, has_errors={has_errors(good)}")

    sg3_catches = {"claim", "category"} & bad_fields == {"claim", "category"}
    sg3_no_fp = not has_errors(good)
    sg3_ok = sg3_catches and sg3_no_fp
    print(f"[SG-3] catches #13 drift: {sg3_catches}; no false-positive on coherent: {sg3_no_fp}; PASS={sg3_ok}")

    print("\n==== VERDICT ====")
    print(f"SG-1 (Prisma facts via existing prisma_parser): {'PASS' if sg1_ok else 'FAIL'}")
    print(f"SG-3 (Zod<->Prisma CONFORMS_TO via existing validator): {'PASS' if sg3_ok else 'FAIL'}")
    return 0 if (sg1_ok and sg3_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
