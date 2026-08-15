"""#5 — the domain vocabulary is calibrated to the OTel semconv registry (no silent drift).

Skips if the semconv registry isn't available locally (e.g. CI without the OTel clone).

Generator: scripts/gen_semconv_domains.py · Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md (#5)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_GEN = REPO / "scripts" / "gen_semconv_domains.py"


def _load():
    spec = importlib.util.spec_from_file_location("gen_semconv_domains", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_gen = _load()
_registry_present = _gen.DEFAULT_REGISTRY.is_dir()
skip_no_registry = pytest.mark.skipif(not _registry_present, reason="semconv registry not local")


@skip_no_registry
class TestDomainCalibration:
    def _doc(self):
        return _gen.build(_gen.DEFAULT_REGISTRY)

    def test_every_domain_is_mapped_or_flagged_derived(self):
        # No OUR domain may be silently un-reconciled — it's either a real registry namespace
        # ("mapped") or an explicitly-flagged non-registry grouping ("derived").
        for d in self._doc()["our_domains"]:
            assert d["status"] in {"mapped", "derived"}, d
            if d["status"] == "derived":
                assert d.get("note"), f"{d['domain']} derived but not explained"

    def test_object_stores_is_the_only_derived(self):
        derived = [d["domain"] for d in self._doc()["our_domains"] if d["status"] == "derived"]
        assert derived == ["object-stores"], f"unexpected derived set: {derived}"

    def test_unmapped_candidates_are_surfaced(self):
        # The registry HAS communication namespaces we don't map yet — they must be surfaced, not lost.
        cands = {u["namespace"] for u in self._doc()["unmapped_candidates"]}
        assert {"jsonrpc", "cloudevents"} <= cands, f"expected candidates missing: {cands}"

    def test_generated_file_in_sync(self):
        # --check must pass — the committed semconv-domains.json matches the live registry reconciliation.
        assert _gen.main(["--check"]) == 0, "semconv-domains.json is stale — run gen_semconv_domains.py"


def test_generator_importable_without_registry():
    # The module + curation constants load even where the registry is absent (CI safety).
    assert _gen.COMMUNICATION_FILTER and _gen.SUBSUMED
