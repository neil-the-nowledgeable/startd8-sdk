"""Unify coverage (imports) + precision (contract IDLs) into one per-domain view.

Module: src/startd8/coverage_map/unified.py
"""

from __future__ import annotations

from startd8.coverage_map.unified import unify


def _cov(detected, pattern_domains, counts):
    return {"detected": detected, "pattern_domains": pattern_domains, "per_pattern_file_counts": counts}


def _prec(available, ops=0, idl="OpenAPI", files=()):
    return {"precision_available": available, "total_operations": ops, "idl_type": idl,
            "idl_files": [{"path": p, "operations": [], "count": 0} for p in files]}


class TestFourStates:
    def test_covered_plus_precise(self):
        cov = _cov(["X-OTEL-5.1-HTTP"], {"X-OTEL-5.1-HTTP": "http"}, {"X-OTEL-5.1-HTTP": 55})
        r = unify(cov, {"http": _prec(True, 192, "OpenAPI", ["openapi.yml"])})
        d = r["domains"]["http"]
        assert d["state"] == "covered+precise" and d["coverage_files"] == 55 and d["precise_operations"] == 192
        assert r["summary"]["covered_and_precise"] == 1

    def test_covered_only(self):
        cov = _cov(["X-OTEL-5.5-DATABASE"], {"X-OTEL-5.5-DATABASE": "db"}, {"X-OTEL-5.5-DATABASE": 12})
        r = unify(cov, {"db": _prec(False)})
        assert r["domains"]["db"]["state"] == "covered-only" and r["summary"]["covered_only"] == 1

    def test_precise_only(self):
        cov = _cov([], {"X-OTEL-5.3-RPC": "rpc"}, {})
        r = unify(cov, {"rpc": _prec(True, 21, "Protocol Buffers", ["demo.proto"])})
        assert r["domains"]["rpc"]["state"] == "precise-only" and r["summary"]["precise_only"] == 1

    def test_absent_domains_present_but_empty(self):
        cov = _cov([], {"X-OTEL-5.6-FAAS": "faas"}, {})
        r = unify(cov, {})
        assert r["domains"]["faas"]["state"] == "absent"


class TestSignalSplitShape:
    def test_java_signal_counts_summed(self):
        # Java reports per_pattern_signal_counts (import/annotation/both) instead of flat counts.
        cov = {"detected": ["J-OTEL-5.1-HTTP"], "pattern_domains": {"J-OTEL-5.1-HTTP": "http"},
               "per_pattern_signal_counts": {"J-OTEL-5.1-HTTP": {"import": 88, "annotation": 0, "both": 30}}}
        r = unify(cov, {"http": _prec(True, 192)})
        assert r["domains"]["http"]["coverage_files"] == 118  # 88 + 0 + 30
