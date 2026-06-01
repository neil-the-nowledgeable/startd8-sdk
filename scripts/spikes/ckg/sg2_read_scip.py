#!/usr/bin/env python3
"""SG-2: read the strtd8 SCIP index and test the capabilities that DON'T exist today.

Genuine gaps (per the existing-code inventory):
  (f) external .d.ts symbol resolution  -> can we see @anthropic-ai/sdk's real exports,
      so a referenced `Anthropic.X` can be validated as real/nonexistent?  (RUN_009 #11)
  cross-file resolution -> does a reference in file A resolve to a definition in file B?
"""
import collections
import sys

import scip_pb2

IDX = "strtd8.scip"


def pkg_of(symbol: str) -> str:
    # SCIP global symbol: "<scheme> <manager> <package-name> <version> <descriptors...>"
    parts = symbol.split(" ")
    if symbol.startswith("local"):
        return "<local>"
    if len(parts) >= 4:
        return parts[2]  # package-name
    return "<other>"


def main() -> int:
    idx = scip_pb2.Index()
    with open(IDX, "rb") as fh:
        idx.ParseFromString(fh.read())

    print(f"[SG-2] tool: {idx.metadata.tool_info.name} {idx.metadata.tool_info.version}")
    print(f"[SG-2] documents: {len(idx.documents)}")
    print(f"[SG-2] external_symbols: {len(idx.external_symbols)}")

    # --- external package symbols (resolved .d.ts) ---
    ext_by_pkg = collections.Counter()
    anthropic_syms = []
    for s in idx.external_symbols:
        p = pkg_of(s.symbol)
        ext_by_pkg[p] += 1
        if "@anthropic-ai/sdk" in s.symbol:
            anthropic_syms.append(s.symbol)
    print("\n[SG-2] external symbols by package (top):")
    for p, n in ext_by_pkg.most_common(10):
        print(f"        {n:5d}  {p}")

    # Also scan occurrences for package symbols referenced in code
    occ_pkg = collections.Counter()
    cross_file_refs = 0
    proj_defs = {}   # symbol -> defining document path
    proj_refs = collections.defaultdict(set)  # symbol -> set of referencing docs
    SymbolRole = scip_pb2.SymbolRole
    for doc in idx.documents:
        for occ in doc.occurrences:
            sym = occ.symbol
            occ_pkg[pkg_of(sym)] += 1
            is_def = bool(occ.symbol_roles & SymbolRole.Definition)
            if not sym.startswith("local") and pkg_of(sym) not in ("<local>", "<other>"):
                if is_def:
                    proj_defs.setdefault(sym, doc.relative_path)
                else:
                    proj_refs[sym].add(doc.relative_path)

    # cross-file: a symbol defined in one project doc and referenced from another
    for sym, defdoc in proj_defs.items():
        for refdoc in proj_refs.get(sym, ()):  # noqa
            if refdoc != defdoc:
                cross_file_refs += 1
                break

    print("\n[SG-2] occurrence symbols by package (top):")
    for p, n in occ_pkg.most_common(10):
        print(f"        {n:6d}  {p}")

    print(f"\n[SG-2] cross-file resolved symbols (def in one file, ref in another): {cross_file_refs}")

    print(f"\n[SG-2] @anthropic-ai/sdk external symbols found: {len(anthropic_syms)}")
    for s in anthropic_syms[:12]:
        print(f"        {s}")

    # --- verdict ---
    ext_resolved = ext_by_pkg.get("@anthropic-ai/sdk", 0) > 0 or any(
        "@anthropic-ai/sdk" in s.symbol for s in idx.external_symbols
    )
    types_visible = len(anthropic_syms) > 0
    cross_file = cross_file_refs > 0
    print("\n==== SG-2 VERDICT ====")
    print(f"external .d.ts resolution (@anthropic-ai/sdk symbols present): {ext_resolved}")
    print(f"can enumerate Anthropic exported type/member symbols (signature f feasible): {types_visible}")
    print(f"real cross-file resolution (def->ref across files): {cross_file}")
    ok = ext_resolved and cross_file
    print(f"SG-2 PASS (external resolution + cross-file): {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
