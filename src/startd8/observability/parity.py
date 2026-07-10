"""
Descriptor↔emission parity (REQ-OBS-SHARED-002), kind-aware and a parent of named
sub-checks so a failure names a precise gate rather than a vague "parity" error:

  (b) metric identity  — canonical OTel name AND exported Prometheus name; reject
                         exported-name collisions even when canonical names differ.
  (c) emitter universe — every `meter.create_*` site in the repo maps to a declared
                         descriptor OR an owned exclusion (the registry below),
                         NOT just the modules in collector._INSTRUMENTED_MODULES.
  (d) span name-pattern — every declared SpanDescriptor.name_pattern matches a runtime
                         span site (best-effort) or is attributes_dynamic.

Relations are kind-aware: **metrics → bijection** (declared ⇔ emitted), **spans → subset**.

Bootstrap mode (REQ-OBS-SHARED-005 I4): a shrinking, *owned* exclusion registry of
known-undeclared emitters (and one known exported-name collision Phase 2 resolves) is
reported but does not hard-fail, so the keystone can land before every pre-existing
emitter is declared. Removing an entry requires declaring that descriptor.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .manifest import ObservabilityManifest, generate_manifest

# Metric instruments emit via meter.create_<kind>(name="..."/positional). Capture the
# instrument kind and the first string argument (positional or name=).
_CREATE_RE = re.compile(
    r"\.create_(counter|histogram|up_down_counter|gauge|observable_gauge|"
    r"observable_counter|observable_up_down_counter)\s*\(\s*"
    r"(?:name\s*=\s*)?[\"']([^\"']+)[\"']"
)


@dataclass(frozen=True)
class EmitterExclusion:
    """An owned, temporary tolerance for an undeclared emitter (R3-F3, bootstrap)."""

    pattern: str       # exact name, or name prefix if `prefix=True`
    owner: str
    reason: str
    prefix: bool = False

    def matches(self, name: str) -> bool:
        return name.startswith(self.pattern) if self.prefix else name == self.pattern


# The shrinking known-gap registry. Each entry is owned and slated for declaration in
# a follow-up pass; removing it requires adding the descriptor in the same change.
#
# EMPTY: every live emitter declares `_OTEL_DESCRIPTORS` and is registered in
# collector._INSTRUMENTED_MODULES (cat-5/B + frontend_codegen.telemetry). The bijection
# holds with no bootstrap tolerance.
EMITTER_EXCLUSIONS: List[EmitterExclusion] = []

# Exported names where a collision is known and resolved by a later pass. (Empty:
# the startd8.cost.total / startd8_cost_total clash was resolved in Phase 2 by
# disambiguating the per-session cost metric to startd8.session.cost.total.)
BOOTSTRAP_NAME_COLLISIONS = frozenset()


def _src_root() -> Path:
    # src/startd8/observability/parity.py -> src/startd8
    return Path(__file__).resolve().parents[1]


def _is_excluded(name: str) -> bool:
    return any(e.matches(name) for e in EMITTER_EXCLUSIONS)


@dataclass
class ParityResult:
    """Outcome of the parity checks. ``ok`` ignores owned/bootstrap-tolerated gaps."""

    declared_not_emitted: List[str] = field(default_factory=list)
    emitted_not_declared: List[str] = field(default_factory=list)        # hard (not excluded)
    bootstrap_undeclared: List[str] = field(default_factory=list)        # excluded this pass
    exported_name_collisions: List[str] = field(default_factory=list)    # hard
    bootstrap_collisions: List[str] = field(default_factory=list)        # tolerated this pass
    spans_without_site: List[str] = field(default_factory=list)          # best-effort, soft

    @property
    def ok(self) -> bool:
        return not (
            self.declared_not_emitted
            or self.emitted_not_declared
            or self.exported_name_collisions
        )


def exported_name(metric_name: str, prometheus_name: Optional[str] = None) -> str:
    """The Prometheus/Mimir-exported form operators query (sub-check b)."""
    if prometheus_name:
        return prometheus_name
    return metric_name.replace(".", "_")


# Modules that *analyze* metric-instrument constructors (fidelity harness) rather than
# *emit* SDK metrics. Their docstrings/patterns contain instrument-constructor examples
# by design — they are the exact thing these modules recognize — so the emitter scan
# must skip them or it flags analyzer examples as undeclared emissions.
_NON_EMITTER_MODULES = frozenset({
    "observability_fidelity_static.py",  # static fidelity: recognizes instrument ctors
})

# Path segments that hold non-shipping fixture code (fake services the fidelity spike
# instruments to demo detection). They contain real ``create_counter`` calls but are not
# SDK emitters — never part of the declared/emitted bijection.
_NON_EMITTER_DIRS = frozenset({"_spike_fixtures"})


def scan_emitted_metric_names(root: Optional[Path] = None) -> Dict[str, List[str]]:
    """Scan the SDK source for ``meter.create_*`` sites → {metric_name: [files]}."""
    root = root or _src_root()
    found: Dict[str, List[str]] = {}
    for py in root.rglob("*.py"):
        if (
            "__pycache__" in py.parts
            or py.name in _NON_EMITTER_MODULES
            or _NON_EMITTER_DIRS & set(py.parts)
        ):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        for _kind, name in _CREATE_RE.findall(text):
            found.setdefault(name, []).append(str(py))
    return found


def check_metric_identity(manifest: ObservabilityManifest) -> List[str]:
    """Sub-check (b): two distinct canonical metrics colliding on the exported name."""
    by_exported: Dict[str, List[str]] = {}
    for m in manifest.metrics:
        by_exported.setdefault(exported_name(m.name, m.prometheus_name), []).append(m.name)
    return [
        f"{exp} <- {sorted(set(names))}"
        for exp, names in by_exported.items()
        if len(set(names)) > 1
    ]


def check_metric_bijection(
    manifest: ObservabilityManifest,
    emitted: Optional[Dict[str, List[str]]] = None,
) -> ParityResult:
    """Sub-check (c) + bijection: declared ⇔ emitted, modulo the exclusion registry."""
    if emitted is None:
        emitted = scan_emitted_metric_names()
    declared = {m.name for m in manifest.metrics}
    emitted_names = set(emitted)

    result = ParityResult()
    result.declared_not_emitted = sorted(declared - emitted_names)
    undeclared = emitted_names - declared
    result.bootstrap_undeclared = sorted(n for n in undeclared if _is_excluded(n))
    result.emitted_not_declared = sorted(n for n in undeclared if not _is_excluded(n))

    collisions = check_metric_identity(manifest)
    for c in collisions:
        exp = c.split(" <- ")[0]
        (result.bootstrap_collisions if exp in BOOTSTRAP_NAME_COLLISIONS
         else result.exported_name_collisions).append(c)
    return result


def check_span_name_patterns(
    manifest: ObservabilityManifest, root: Optional[Path] = None
) -> List[str]:
    """Sub-check (d), best-effort: a declared span's static name prefix should appear
    in a span literal, unless attributes_dynamic."""
    root = root or _src_root()
    # Read each file once into a list (avoids an O(n^2) string-concat blob), then test
    # each span prefix with early-exit on the first matching file.
    texts: List[str] = []
    for py in root.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            texts.append(py.read_text(encoding="utf-8"))
        except OSError:
            continue

    missing: List[str] = []
    for s in manifest.spans:
        if s.attributes_dynamic:
            continue
        prefix = re.split(r"[{:]", s.name_pattern)[0]
        if prefix and not any(prefix in t for t in texts):
            missing.append(s.name_pattern)
    return missing


def run_parity(manifest: Optional[ObservabilityManifest] = None) -> ParityResult:
    """Run all parity sub-checks in bootstrap mode and return the aggregate result."""
    if manifest is None:
        manifest = generate_manifest()
    result = check_metric_bijection(manifest)
    result.spans_without_site = check_span_name_patterns(manifest)
    return result
