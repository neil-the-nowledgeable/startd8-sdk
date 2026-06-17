"""Tests for the Jetson lane driver helpers (scripts/run_jetson_lane.py) — offline, no endpoint."""

import importlib.util
from pathlib import Path

import pytest

from startd8.benchmark_matrix import firewall as fw
from startd8.benchmark_matrix import jetson_lane as lane

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "run_jetson_lane.py"


def _load_driver():
    spec = importlib.util.spec_from_file_location("run_jetson_lane", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


driver = _load_driver()


def test_load_seed_prompt_paymentservice():
    seeds = driver.discover_seeds(["paymentservice"])
    assert len(seeds) == 1
    service, prompt, lang = driver.load_seed_prompt(seeds[0][1])
    assert service == "paymentservice"
    assert lang == "nodejs"
    assert "PaymentService" in prompt and len(prompt) > 200


def test_discover_seeds_all_vs_filtered():
    all_seeds = driver.discover_seeds(None)
    assert len(all_seeds) >= 9  # the OB service roster
    one = driver.discover_seeds(["cartservice"])
    assert [s for s, _ in one] == ["cartservice"]


def test_alias_of():
    assert driver._alias_of("jetson:mistral-7b-base") == "mistral-7b-base"
    assert driver._alias_of("bare") == "bare"


def test_build_plan_counts():
    seeds = driver.discover_seeds(["paymentservice", "cartservice"])
    plan = driver.build_plan(["jetson:mistral-7b-base", "jetson:iter-002"], seeds)
    assert plan["cells"] == 4
    assert set(plan["services"]) == {"paymentservice", "cartservice"}


def test_write_batch_partitions(tmp_path):
    pairs = [
        (lane.JetsonCellRecord("mistral-7b-base", "code", fw.TRACK_GENERAL, True,
                               {"reasons": []}, server_commit_sha="abc"), "paymentservice"),
        (lane.JetsonCellRecord("mistral-7b-base", None, fw.TRACK_INVALID, False,
                               {"reasons": ["applied_adapter: served=iter_002 expected=__base__"]}),
         "cartservice"),
    ]
    plan = {"models": ["jetson:mistral-7b-base"], "services": ["paymentservice", "cartservice"], "cells": 2}
    cells_path, report_path = driver.write_batch(tmp_path, pairs, plan, "abc")

    assert cells_path.exists() and report_path.exists()
    import json
    data = json.loads(cells_path.read_text())
    assert data["server_sha"] == "abc"
    assert len(data["cells"]) == 2
    assert {c["service"] for c in data["cells"]} == {"paymentservice", "cartservice"}
    report = report_path.read_text()
    assert "general (scored): **1**" in report
    assert "invalid (DROPPED): **1**" in report
