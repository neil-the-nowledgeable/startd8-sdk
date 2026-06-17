"""Unit tests for the Jetson contamination-firewall verdict logic (FR-J5a/J6/J6b/J8).

Fully offline — exercises the applied-adapter identity guard, the neutral-prompt check, the
determinism presence check, and the general/in-domain/invalid track decision.
"""

import pytest

from startd8.benchmark_matrix import firewall as fw

NEUTRAL = "You are a senior software engineer. Produce a complete, runnable implementation."
CORPUS = (
    "You are a senior Python engineer working on the GCP microservices-demo codebase. "
    "Match the house style (JSON logger, OpenTelemetry boilerplate, gRPC servicer pattern, "
    "Apache 2.0 header)."
)
SAMPLING = {"temperature": 0.0, "top_p": 1.0, "seed": 0}
QUANT = "nf4"


class TestParseAndVectors:
    def test_parse_served_adapter(self):
        assert fw.parse_served_adapter("served_adapter=iter_002") == "iter_002"
        assert fw.parse_served_adapter("served_adapter=__base__") == "__base__"
        assert fw.parse_served_adapter(None) is None
        assert fw.parse_served_adapter("garbage") is None

    def test_applied_adapter_match(self):
        v = fw.verify_applied_adapter("served_adapter=iter_002", "iter_002", expect_base=False)
        assert v.ok

    def test_applied_adapter_base_sentinel(self):
        v = fw.verify_applied_adapter("served_adapter=__base__", "mistralai/Mistral-7B-v0.3", expect_base=True)
        assert v.ok

    def test_applied_adapter_mismatch(self):
        v = fw.verify_applied_adapter("served_adapter=iter_002", "mistralai/Mistral-7B-v0.3", expect_base=True)
        assert not v.ok

    def test_applied_adapter_missing_echo(self):
        v = fw.verify_applied_adapter(None, "iter_002", expect_base=False)
        assert not v.ok and "echo missing" in v.detail

    def test_system_prompt_clean(self):
        assert fw.verify_system_prompt(NEUTRAL, NEUTRAL).ok

    def test_system_prompt_mismatch(self):
        assert not fw.verify_system_prompt("something else entirely", NEUTRAL).ok

    def test_system_prompt_banned_tokens(self):
        # server ignored our neutral prompt and used its corpus default → banned tokens present
        v = fw.verify_system_prompt(CORPUS, CORPUS)  # even if "expected"==corpus, tokens are banned
        assert not v.ok and "banned corpus tokens" in v.detail

    def test_determinism_recorded_vs_missing(self):
        assert fw.verify_determinism(SAMPLING, QUANT).ok
        assert not fw.verify_determinism(None, QUANT).ok
        assert not fw.verify_determinism(SAMPLING, None).ok


class TestEvaluateTracks:
    def test_clean_base_cell_goes_general(self):
        v = fw.evaluate_jetson_cell(
            requested_alias="mistral-7b-base",
            system_fingerprint="served_adapter=__base__",
            sent_prompt=NEUTRAL,
            expected_neutral=NEUTRAL,
            sampling=SAMPLING,
            quant=QUANT,
        )
        assert v.track == fw.TRACK_GENERAL
        assert v.clean and not v.invalidated

    def test_in_domain_cell_is_fenced_not_clean(self):
        v = fw.evaluate_jetson_cell(
            requested_alias="iter-002",
            system_fingerprint="served_adapter=iter_002",
            sent_prompt=NEUTRAL,
            expected_neutral=NEUTRAL,
            sampling=SAMPLING,
            quant=QUANT,
        )
        assert v.track == fw.TRACK_IN_DOMAIN
        assert not v.clean and not v.invalidated  # valid result, just never a general peer

    def test_wrong_adapter_invalidates(self):
        # requested the clean base, but the server served iter_002 (reachable-but-wrong-adapter)
        v = fw.evaluate_jetson_cell(
            requested_alias="mistral-7b-base",
            system_fingerprint="served_adapter=iter_002",
            sent_prompt=NEUTRAL,
            expected_neutral=NEUTRAL,
            sampling=SAMPLING,
            quant=QUANT,
        )
        assert v.invalidated and v.track == fw.TRACK_INVALID
        assert any("applied_adapter" in r for r in v.reasons)

    def test_clean_label_but_corpus_prompt_not_admissible(self):
        # adapter correct, but the server force-fed its corpus prompt → not clean, not general
        v = fw.evaluate_jetson_cell(
            requested_alias="mistral-7b-base",
            system_fingerprint="served_adapter=__base__",
            sent_prompt=CORPUS,
            expected_neutral=NEUTRAL,
            sampling=SAMPLING,
            quant=QUANT,
        )
        assert not v.clean
        assert v.track == fw.TRACK_INVALID  # clean-labeled but a vector failed ⇒ inadmissible

    def test_missing_fingerprint_invalidates(self):
        v = fw.evaluate_jetson_cell(
            requested_alias="iter-002",
            system_fingerprint=None,
            sent_prompt=NEUTRAL,
            expected_neutral=NEUTRAL,
            sampling=SAMPLING,
            quant=QUANT,
        )
        assert v.invalidated

    def test_unrecorded_determinism_blocks_clean(self):
        v = fw.evaluate_jetson_cell(
            requested_alias="mistral-7b-base",
            system_fingerprint="served_adapter=__base__",
            sent_prompt=NEUTRAL,
            expected_neutral=NEUTRAL,
            sampling=None,  # FR-J6b not recorded
            quant=QUANT,
        )
        assert not v.clean

    def test_provenance_serialization(self):
        v = fw.evaluate_jetson_cell(
            requested_alias="mistral-7b-base",
            system_fingerprint="served_adapter=__base__",
            sent_prompt=NEUTRAL,
            expected_neutral=NEUTRAL,
            sampling=SAMPLING,
            quant=QUANT,
        )
        prov = v.as_provenance()
        assert prov["track"] == "general" and prov["clean"] is True
        assert "applied_adapter" in prov["vectors"] and "system_prompt" in prov["vectors"]
