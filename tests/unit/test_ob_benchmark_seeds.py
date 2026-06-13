"""M2 — Online Boutique benchmark seeds (FR-8/FR-31).

Verifies the 9 per-service seeds are present, load through add_features_from_seed as
exactly one independently-scored feature each, pin a native language that resolve_language()
agrees with, and are byte-stable (the generator's --check passes = reproducible inputs).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"
GENERATOR = REPO / "scripts" / "gen_ob_benchmark_seeds.py"

EXPECTED = {
    "cartservice": "csharp",
    "productcatalogservice": "go",
    "currencyservice": "nodejs",
    "paymentservice": "nodejs",
    "shippingservice": "go",
    "emailservice": "python",
    "checkoutservice": "go",
    "recommendationservice": "python",
    "adservice": "java",
}


def _seed_paths():
    return sorted(SEEDS_DIR.glob("seed-*.json"))


def test_all_nine_seeds_present():
    found = {p.stem.replace("seed-", "") for p in _seed_paths()}
    assert found == set(EXPECTED), f"seed set mismatch: {found ^ set(EXPECTED)}"
    assert (SEEDS_DIR / "seeds-index.json").exists()
    assert (SEEDS_DIR / "demo.proto").exists()


def test_proto_retains_apache_header():
    # FR-49: OB is Apache-2.0; the vendored contract must keep its license notice.
    text = (SEEDS_DIR / "demo.proto").read_text(encoding="utf-8")
    assert "Licensed under the Apache License" in text


@pytest.mark.parametrize("seed_path", _seed_paths(), ids=lambda p: p.stem)
def test_seed_loads_as_single_feature_with_pinned_language(seed_path):
    from startd8.contractors.queue import FeatureQueue
    from startd8.languages import LanguageRegistry, resolve_language

    LanguageRegistry.discover()
    meta = json.loads(seed_path.read_text(encoding="utf-8"))["service_metadata"]
    svc, pinned = meta["service"], meta["language"]
    assert pinned == EXPECTED[svc]
    assert meta.get("language_rationale")  # FR-31: rationale recorded

    q = FeatureQueue(project_root=Path(tempfile.mkdtemp()))
    feats = q.add_features_from_seed(seed_path)
    assert len(feats) == 1, "each service is one independently-scored task (FR-9)"
    assert feats[0].dependencies == []  # standalone in the matrix
    profile = resolve_language(feats[0].target_files)
    detected = getattr(profile, "language_id", getattr(profile, "id", None))
    assert detected == pinned, f"{svc}: pinned {pinned} but resolve_language said {detected}"


def test_seeds_are_byte_stable():
    # Reproducible inputs (R1-S9 / FR-19): regenerating yields identical bytes.
    r = subprocess.run([sys.executable, str(GENERATOR), "--check"],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, f"seed drift:\n{r.stdout}\n{r.stderr}"
