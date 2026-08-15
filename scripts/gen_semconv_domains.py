#!/usr/bin/env python3
"""Generate + drift-check the §5 communication-domain vocabulary against the OTel semconv registry (#5).

The 16-pattern / 14-domain crosswalk vocabulary was hand-typed and drifted from the authoritative OTel
registry (we caught mcp/cloud/object-stores drift by a manual pass 2026-08-15). This generator makes that
reconciliation CONTINUOUS: it reads the semconv registry namespaces, applies a curated §5-communication
filter, and emits `semconv-domains.json` classifying every domain (mapped / derived / unmapped-candidate /
subsumed). `--check` fails when our vocabulary drifts from the registry — so drift is LOUD, not silent.

This is the mechanism behind the "calibration cadence" (dev-os/loops OTel-language loop, repurposed).
Lighter than OTel Weaver (which resolves the full typed schema); for the domain LIST, parsing the local
registry namespaces suffices.

Registry source (default): ~/Documents/dev/OTel/semantic-conventions/…/model/  (override with --registry).
Our domains: read from the committed python crosswalk (the parity reference — all languages match it).

Usage:
    python3 scripts/gen_semconv_domains.py
    python3 scripts/gen_semconv_domains.py --check         # drift guard (exit 1 on drift)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "design" / "semconv-domains.json"
OUR_CROSSWALK = REPO / "docs" / "design" / "python-capability-index" / "communication-crosswalk.json"
DEFAULT_REGISTRY = (REPO.parent / "OTel" / "semantic-conventions" / "semantic-conventions" / "model")

#: Curated: which registry namespaces are §5 *application-communication* (vs resource/infra/runtime).
#: This is the one piece of human curation — #5 generates candidates, this filter scopes them.
COMMUNICATION_FILTER = frozenset({
    # RPC / API family
    "http", "rpc", "jsonrpc", "onc_rpc", "signalr", "mcp",
    # messaging / events
    "messaging", "cloudevents",
    # database family
    "db", "cassandra", "elasticsearch", "oracledb",
    # application-level
    "graphql", "faas", "feature-flags", "gen-ai", "openai",
    # ops / network
    "cicd", "cli", "dns",
    # cloud providers
    "cloud", "aws", "azure", "gcp", "cloudfoundry", "heroku", "openshift",
})

#: Registry specifics we intentionally FOLD into one of our generic domains (not a gap).
SUBSUMED = {
    "cassandra": "db", "elasticsearch": "db", "oracledb": "db",
    "aws": "cloud", "azure": "cloud", "gcp": "cloud",
    "cloudfoundry": "cloud", "heroku": "cloud", "openshift": "cloud",
    "openai": "gen-ai",
}


def _registry_namespaces(registry_root: Path) -> list[str]:
    if not registry_root.is_dir():
        raise FileNotFoundError(f"semconv registry not found: {registry_root} (pass --registry)")
    return sorted(p.name for p in registry_root.iterdir() if p.is_dir())


def _our_domains() -> list[str]:
    d = json.loads(OUR_CROSSWALK.read_text(encoding="utf-8"))
    return sorted({p["semconv_domain"] for p in d["patterns"]})


def build(registry_root: Path) -> dict[str, Any]:
    registry = set(_registry_namespaces(registry_root))
    ours = _our_domains()
    comm = COMMUNICATION_FILTER

    domains = []
    for dom in ours:
        if dom in registry:
            domains.append({"domain": dom, "status": "mapped"})
        else:
            domains.append({"domain": dom, "status": "derived",
                            "note": "not a semconv namespace — our grouping; keep flagged, don't pretend canonical"})

    # registry communication namespaces we do NOT map as a top-level domain
    unmapped = sorted(ns for ns in (comm & registry)
                      if ns not in ours and ns not in SUBSUMED)
    subsumed = {k: v for k, v in sorted(SUBSUMED.items()) if k in registry}

    return {
        "generator": "gen_semconv_domains.py",
        "registry_source": str(registry_root),
        "counts": {
            "our_domains": len(ours),
            "mapped": sum(1 for d in domains if d["status"] == "mapped"),
            "derived": sum(1 for d in domains if d["status"] == "derived"),
            "unmapped_candidates": len(unmapped),
        },
        "our_domains": domains,
        "unmapped_candidates": [
            {"namespace": ns, "action": "candidate new §5 domain — consider adding"} for ns in unmapped
        ],
        "subsumed": subsumed,
        "registry_namespaces_snapshot": sorted(registry),
        "communication_filter": sorted(comm),
    }


def _serialize(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="semconv model/ dir")
    ap.add_argument("--check", action="store_true", help="Fail (exit 1) if our vocabulary drifts from the registry")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    try:
        doc = build(args.registry)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    text = _serialize(doc)

    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.is_file() else None
        if current != text:
            print("DRIFT: semconv-domains.json out of sync with the registry / our crosswalk")
            print(f"  unmapped candidates: {[u['namespace'] for u in doc['unmapped_candidates']]}")
            print(f"  derived (non-registry): {[d['domain'] for d in doc['our_domains'] if d['status']=='derived']}")
            print("  run gen_semconv_domains.py to regenerate + reconcile")
            return 1
        print(f"OK: domain vocabulary in sync ({doc['counts']})")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    c = doc["counts"]
    print(f"wrote {args.out}  (mapped={c['mapped']} derived={c['derived']} "
          f"unmapped_candidates={c['unmapped_candidates']})")
    if doc["unmapped_candidates"]:
        print(f"  candidate new §5 domains: {', '.join(u['namespace'] for u in doc['unmapped_candidates'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
