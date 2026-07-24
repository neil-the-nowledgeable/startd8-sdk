# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""One-shot semantic parity gate for the collector_enrichment cutover.

REQ_COLLECTOR_ENRICHMENT FR-10a/11. Before the hand-written ``transform/business`` block is removed
from the demo, prove the generated processor is equivalent to it. Parity is **semantic, not
byte-for-byte**: the hand-written block groups services that share a value into one OR-chained
statement (``… == "a" or … == "b"``), while the generator emits one statement per service. Both are
parsed back into a ``{service.name: {attr: value}}`` map and compared — order- and grouping-insensitive.

This is the reconciliation point the reflective spec identified: the handoff asked for byte parity,
but the two legitimate renderings can never be byte-equal, so equivalence is defined on the resolved
enrichment map instead.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict

import yaml

# set(attributes["business.<attr>"], "<value>") where <where-clause>
# value body: any char except an unescaped quote (Go-style \" / \\ escapes allowed).
_SET_RE = re.compile(
    r'set\(\s*attributes\[\s*"business\.(?P<attr>[A-Za-z0-9_]+)"\s*\]\s*,\s*'
    r'"(?P<value>(?:[^"\\]|\\.)*)"\s*\)\s+where\s+(?P<where>.*)$'
)
# resource.attributes["service.name"] == "<svc>"  (repeated, OR-joined)
_SVC_RE = re.compile(
    r'resource\.attributes\[\s*"service\.name"\s*\]\s*==\s*"(?P<svc>(?:[^"\\]|\\.)*)"'
)


def _unescape_ottl(s: str) -> str:
    """Reverse Go-style OTTL literal escaping (\\" → ", \\\\ → \\)."""
    return s.replace('\\"', '"').replace("\\\\", "\\")


@dataclass
class ParityResult:
    """Outcome of a semantic parity comparison."""

    matches: bool
    only_in_generated: Dict[str, Dict[str, str]] = field(default_factory=dict)
    only_in_reference: Dict[str, Dict[str, str]] = field(default_factory=dict)
    value_mismatch: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def summary(self) -> str:
        if self.matches:
            return "PARITY OK — generated ≡ reference (semantic)"
        parts = []
        if self.only_in_generated:
            parts.append(f"only_in_generated={self.only_in_generated}")
        if self.only_in_reference:
            parts.append(f"only_in_reference={self.only_in_reference}")
        if self.value_mismatch:
            parts.append(f"value_mismatch={self.value_mismatch}")
        return "PARITY MISMATCH — " + "; ".join(parts)


def extract_enrichment_map(cfg_yaml: str) -> Dict[str, Dict[str, str]]:
    """Parse a collector config into ``{service.name: {attr: value}}`` from its transform/business
    processor. Grouping-insensitive: an OR-chained ``where`` fans out to one entry per service.

    Tolerant of the exact processor key (``transform/business`` or any ``transform*`` key) and of a
    missing block (returns ``{}``). Comments are ignored by the YAML parser."""
    data = yaml.safe_load(cfg_yaml) or {}
    processors = (data.get("processors") or {}) if isinstance(data, dict) else {}

    out: Dict[str, Dict[str, str]] = {}
    for key, proc in processors.items():
        if not (key == "transform/business" or str(key).startswith("transform")):
            continue
        if not isinstance(proc, dict):
            continue
        for block in proc.get("trace_statements") or []:
            for stmt in (block or {}).get("statements") or []:
                m = _SET_RE.match(str(stmt).strip())
                if not m:
                    continue
                attr = m.group("attr")
                value = _unescape_ottl(m.group("value"))
                for svc_m in _SVC_RE.finditer(m.group("where")):
                    svc = _unescape_ottl(svc_m.group("svc"))
                    out.setdefault(svc, {})[attr] = value
    return out


def check_collector_enrichment_parity(
    generated_yaml: str, reference_yaml: str
) -> ParityResult:
    """Compare the generated processor against the hand-written reference — semantically (FR-10a/11)."""
    gen = extract_enrichment_map(generated_yaml)
    ref = extract_enrichment_map(reference_yaml)

    only_gen = {s: gen[s] for s in gen.keys() - ref.keys()}
    only_ref = {s: ref[s] for s in ref.keys() - gen.keys()}

    mismatch: Dict[str, Dict[str, Any]] = {}
    for svc in gen.keys() & ref.keys():
        g_attrs, r_attrs = gen[svc], ref[svc]
        diff: Dict[str, Any] = {}
        for attr in set(g_attrs) | set(r_attrs):
            gv, rv = g_attrs.get(attr), r_attrs.get(attr)
            if gv != rv:
                diff[attr] = {"generated": gv, "reference": rv}
        if diff:
            mismatch[svc] = diff

    matches = not (only_gen or only_ref or mismatch)
    return ParityResult(
        matches=matches,
        only_in_generated=only_gen,
        only_in_reference=only_ref,
        value_mismatch=mismatch,
    )
