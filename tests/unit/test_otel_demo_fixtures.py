"""Unit tests for OTel Demo Python rebuild fixtures (Steps 1–6)."""
from __future__ import annotations

import py_compile
from pathlib import Path

import pytest

from scripts.python_capability_resolver import analyze_corpus, match_patterns, extract_signals, load_index

_REPO = Path(__file__).resolve().parents[2]
FIXTURES = _REPO / "fixtures" / "otel-demo"

FIXTURE_PY = [
    FIXTURES / "accounting-py" / "consumer.py",
    FIXTURES / "accounting-py" / "models.py",
    FIXTURES / "checkout-kafka-py" / "producer.py",
    FIXTURES / "email-py" / "app" / "main.py",
    FIXTURES / "cart-py" / "cart_server.py",
    FIXTURES / "cart-py" / "valkey_store.py",
    FIXTURES / "payment-py" / "payment_server.py",
    FIXTURES / "product-reviews-py" / "product_reviews_server.py",
]


@pytest.mark.unit
@pytest.mark.parametrize("path", FIXTURE_PY, ids=lambda p: p.parent.name + "/" + p.name)
def test_fixture_compiles(path: Path) -> None:
    assert path.is_file(), f"missing {path}"
    py_compile.compile(str(path), doraise=True)


@pytest.mark.unit
def test_fixtures_cover_messaging_and_redis() -> None:
    report = analyze_corpus(FIXTURES, corpus="fixtures", skip_generated=True, python_glob="**/*.py")
    assert "PY-OTEL-5.4-MESSAGING" in report.pattern_union
    assert "PY-OTEL-5.5-DATABASE" in report.pattern_union
    assert report.overall_index_percent >= 40.0


@pytest.mark.unit
def test_fixtures_cover_fastapi_http() -> None:
    report = analyze_corpus(FIXTURES, corpus="fixtures", skip_generated=True, python_glob="**/*.py")
    assert "PY-OTEL-5.1-HTTP" in report.pattern_union
    assert "PY-OTEL-5.6-GENAI" in report.pattern_union


@pytest.mark.unit
def test_http_get_only_not_matched() -> None:
    index = load_index()
    sig = extract_signals("data = {}\nvalue = data.get('key')\n")
    matches = match_patterns(sig, index["patterns"])
    assert not any(m.pattern_id == "PY-OTEL-5.1-HTTP" for m in matches)
