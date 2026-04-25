"""REQ-VUE-P-012 / Phase C.6: observability labels for Vue + JS dialect."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from startd8.languages.js_metadata import JS_DIALECT_VUE_SFC, JS_HOST_JAVASCRIPT_NODE
from startd8.languages.vue import VueLanguageProfile
from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator, _FileProcessingState


@pytest.mark.unit
def test_micro_prime_generation_metadata_includes_vue_js_labels() -> None:
    gen = MicroPrimeCodeGenerator(language_profile=VueLanguageProfile())
    st = _FileProcessingState()
    meta = gen._build_generation_metadata(st, 0)
    assert meta["language_id"] == "vue"
    assert meta["js_host_id"] == JS_HOST_JAVASCRIPT_NODE
    assert meta["js_dialect_id"] == JS_DIALECT_VUE_SFC


@pytest.mark.unit
def test_micro_prime_otel_profile_labels_match_vue_profile() -> None:
    gen = MicroPrimeCodeGenerator(language_profile=VueLanguageProfile())
    labels = gen._micro_prime_otel_profile_labels()
    assert labels == {
        "language_id": "vue",
        "js_host_id": JS_HOST_JAVASCRIPT_NODE,
        "js_dialect_id": JS_DIALECT_VUE_SFC,
    }


@pytest.mark.unit
def test_generation_path_metrics_merge_optional_labels() -> None:
    from startd8.micro_prime import engine as eng

    with patch.object(eng._engine_metrics, "record") as m:
        eng._record_generation_path(
            "file_whole_primary",
            "src/App.vue",
            {"language_id": "vue", "js_dialect_id": "vue_sfc"},
        )
    m.assert_called_once()
    name, _count, attrs = m.call_args[0]
    assert name == "generation_path"
    assert attrs["path"] == "file_whole_primary"
    assert attrs["file_path"] == "src/App.vue"
    assert attrs["language_id"] == "vue"
    assert attrs["js_dialect_id"] == "vue_sfc"
