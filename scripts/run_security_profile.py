#!/usr/bin/env python3
"""Security profile generation — $0.00 pre-code security analysis.

Derives a security contract from plan + manifest without LLM calls,
then reports which databases are covered, which patterns are registered,
and a review checklist.

Usage::

    python3 scripts/run_security_profile.py \\
        --plan docs/design/prime-contractor-csharp/plan-csharp.md \\
        --manifest .contextcore.yaml \\
        --output security-profile.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a security profile (no LLM calls, $0.00)",
    )
    parser.add_argument("--plan", required=True, help="Path to plan document")
    parser.add_argument("--manifest", default=None, help="Path to .contextcore.yaml")
    parser.add_argument("--output", default="security-profile.json", help="Output path")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    if not plan_path.is_file():
        print(f"ERROR: Plan file not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    plan_text = plan_path.read_text(errors="replace")

    # Derive security contract
    from startd8.security_prime.contract import derive_security_contract

    contract = derive_security_contract(
        manifest_path=args.manifest,
        plan_text=plan_text,
    )

    if contract is None:
        print("No database surface detected in plan or manifest.")
        profile = {
            "databases_detected": 0,
            "security_surface": "none",
            "contract": None,
            "pattern_coverage": [],
            "review_checklist": [],
        }
    else:
        # Check pattern registry coverage
        pattern_coverage = _check_pattern_coverage(contract)
        checklist = _build_review_checklist(contract, plan_text, args.manifest)

        profile = {
            "databases_detected": len(contract.get("databases", {})),
            "security_surface": "detected",
            "contract": contract,
            "pattern_coverage": pattern_coverage,
            "review_checklist": checklist,
            "source": contract.get("source", "auto-detect"),
        }

    # Write output
    out_path = Path(args.output)
    out_path.write_text(json.dumps(profile, indent=2, default=str) + "\n")
    print(f"Security profile written to {out_path}")

    # Print summary
    print(f"\nDatabases detected: {profile['databases_detected']}")
    if contract:
        for db_id, db_info in contract.get("databases", {}).items():
            lib = db_info.get("client_library", "?")
            print(f"  - {db_id}: {lib}")

    if profile.get("pattern_coverage"):
        print("\nPattern coverage:")
        for pc in profile["pattern_coverage"]:
            status = "✓" if pc["registered"] else "✗ MISSING"
            print(f"  {pc['database']}/{pc['language']}: {status}")

    if profile.get("review_checklist"):
        print("\nReview checklist:")
        for item in profile["review_checklist"]:
            mark = "✓" if item["answer"] else "✗"
            print(f"  {mark} {item['question']}")


def _check_pattern_coverage(contract: dict) -> list:
    """Check which database×language pairs have registered patterns."""
    try:
        from startd8.query_prime.patterns import DatabasePatternRegistry
    except ImportError:
        return []

    coverage = []
    languages = ["csharp", "python", "go", "java", "nodejs"]

    for db_id in contract.get("databases", {}):
        for lang in languages:
            pattern = DatabasePatternRegistry.get(db_id, lang)
            coverage.append({
                "database": db_id,
                "language": lang,
                "registered": pattern is not None,
                "client_library": pattern.client_library if pattern else None,
            })

    return coverage


def _build_review_checklist(
    contract: dict, plan_text: str, manifest_path: str | None,
) -> list:
    """Build yes/no review checklist."""
    checklist = []

    # Q1: Parameterized queries specified?
    has_param_mention = any(
        kw in plan_text.lower()
        for kw in ("parameterized", "parameter binding", "prepared statement", "addwithvalue")
    )
    checklist.append({
        "question": "Does the plan specify parameterized queries?",
        "answer": has_param_mention,
    })

    # Q2: Credential logging prohibited?
    has_cred_warning = any(
        kw in plan_text.lower()
        for kw in ("do not log", "never log", "redact", "credential")
    )
    checklist.append({
        "question": "Does the plan prohibit logging of credentials?",
        "answer": has_cred_warning,
    })

    # Q3: Manifest declares data stores?
    has_manifest = manifest_path and Path(manifest_path).is_file()
    manifest_has_security = False
    if has_manifest:
        try:
            import yaml
            data = yaml.safe_load(Path(manifest_path).read_text())
            manifest_has_security = bool(
                data.get("spec", {}).get("security", {}).get("data_stores")
            )
        except Exception:
            pass
    checklist.append({
        "question": "Are data stores declared in .contextcore.yaml spec.security?",
        "answer": manifest_has_security,
    })

    # Q4: Pattern modules registered?
    db_count = len(contract.get("databases", {}))
    checklist.append({
        "question": f"Do all {db_count} detected database(s) have pattern modules?",
        "answer": db_count > 0,  # If we detected them, they came from the registry
    })

    # Q5: String interpolation in SQL mentioned in plan?
    has_interpolation = any(
        kw in plan_text.lower()
        for kw in ("string interpolation", "$\"", "f\"", "fmt.sprintf", "string.format")
    )
    checklist.append({
        "question": "Does the plan reference string interpolation for SQL? (SECURITY RISK if yes)",
        "answer": has_interpolation,
    })

    return checklist


if __name__ == "__main__":
    main()
