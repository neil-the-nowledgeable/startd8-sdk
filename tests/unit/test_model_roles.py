"""Tests for the backend-agnostic per-role model resolver (MODEL_CONFIG #4)."""

from __future__ import annotations

import pytest

from startd8.model_catalog import Models, get_latest_model
from startd8.model_roles import Role, resolve_role_spec


class _FakeConfigManager:
    def __init__(self, models):  # models: {role: spec}
        self._m = models

    def get_model_config(self, role):
        spec = self._m.get(role)
        return {"default": spec} if spec else {}


# ---- precedence ----------------------------------------------------------

def test_override_wins():
    assert resolve_role_spec(Role.LEAD, override="x:y") == "x:y"


def test_run_config_role_key_and_legacy_alias():
    assert resolve_role_spec("lead", run_config={"lead": "a:b"}) == "a:b"
    assert resolve_role_spec("lead", run_config={"lead_agent": "c:d"}) == "c:d"


def test_user_config_models_section():
    cm = _FakeConfigManager({"drafter": "openai:gpt-4o"})
    assert resolve_role_spec("drafter", config_manager=cm) == "openai:gpt-4o"


def test_inheritance_explicit_parent():
    # reviewer ← lead, ingestion_* ← lead, cloud_retry ← drafter
    assert resolve_role_spec("reviewer", run_config={"lead_agent": "gemini:gemini-2.5-pro"}) == "gemini:gemini-2.5-pro"
    assert resolve_role_spec("ingestion_transformer", run_config={"lead_agent": "gemini:gemini-2.5-pro"}) == "gemini:gemini-2.5-pro"
    assert resolve_role_spec("micro_prime_cloud_retry", run_config={"drafter_agent": "gemini:gemini-2.5-flash"}) == "gemini:gemini-2.5-flash"


def test_provider_default_at_role_tier():
    assert resolve_role_spec("lead", provider="gemini") == get_latest_model("gemini", "flagship")
    assert resolve_role_spec("drafter", provider="gemini") == get_latest_model("gemini", "balanced")
    assert resolve_role_spec("micro_prime_cloud_retry", provider="gemini") == get_latest_model("gemini", "fast")


def test_provider_via_run_config_keys():
    assert resolve_role_spec("lead", run_config={"default_provider": "openai"}).startswith("openai:")
    assert resolve_role_spec("lead", run_config={"provider": "openai"}).startswith("openai:")


def test_catalog_defaults_no_config():
    assert resolve_role_spec("lead") == Models.PRIMARY_CONTRACTOR_LEAD
    assert resolve_role_spec("drafter") == Models.PRIMARY_CONTRACTOR_DRAFTER
    assert resolve_role_spec("tier3") == Models.CLAUDE_OPUS_LATEST
    assert resolve_role_spec("reviewer") == Models.PRIMARY_CONTRACTOR_LEAD
    assert resolve_role_spec("ingestion_assessor") == Models.CLAUDE_SONNET_LATEST
    # the residual hardcoded-haiku cloud-retry leak now resolves through the role map
    assert resolve_role_spec("micro_prime_cloud_retry") == Models.CLAUDE_HAIKU_LATEST
    assert resolve_role_spec("micro_prime_local") == "ollama:startd8-coder"


# ---- ordering between layers ---------------------------------------------

def test_full_precedence_ordering():
    rc = {"lead_agent": "a:b", "default_provider": "openai"}
    # explicit > inherit > provider
    assert resolve_role_spec("reviewer", override="z:z", run_config=rc) == "z:z"
    assert resolve_role_spec("reviewer", run_config=rc) == "a:b"               # inherit beats provider
    # no explicit parent → provider used at this role's tier
    assert resolve_role_spec("ingestion_assessor", run_config={"default_provider": "gemini"}) == get_latest_model("gemini", "balanced")


# ---- backend-agnostic (the edge-brains seam) -----------------------------

def test_backend_agnostic_specs_pass_through():
    # any provider string is returned verbatim — no special-casing (ollama/edge ready)
    assert resolve_role_spec("micro_prime_local", override="edge:house-7b") == "edge:house-7b"
    assert resolve_role_spec("micro_prime_local", run_config={"micro_prime_local": "ollama:custom"}) == "ollama:custom"
    assert resolve_role_spec("lead", override="edgebrains:iter-003") == "edgebrains:iter-003"


def test_role_enum_and_string_equivalent():
    assert resolve_role_spec(Role.TIER3, provider="gemini") == resolve_role_spec("tier3", provider="gemini")


# ---- regression guards (step 8: no silent-provider leak) ------------------

def test_provider_override_leaks_no_anthropic_across_roles():
    """The run-026 invariant: ONE provider override flips EVERY role — no role
    silently stays on anthropic. (gemini supports all role tiers.)"""
    for role in Role:
        spec = resolve_role_spec(role, provider="gemini")
        assert not spec.startswith("anthropic:"), f"{role.value} leaked anthropic: {spec}"


def test_resolution_sites_delegate_not_call_get_latest_model():
    """The role→model mapping lives only in model_roles. Resolution sites must
    delegate (no direct get_latest_model / hardcoded provider-default fallback),
    so the run-026 leak class can't be reintroduced site-by-site."""
    import inspect

    import startd8.contractors.prime_contractor_config as pcc
    import startd8.micro_prime.prime_adapter as pa
    import startd8.workflows.builtin.plan_ingestion_workflow as piw

    for mod in (piw, pcc, pa):
        src = inspect.getsource(mod)
        assert "get_latest_model" not in src, (
            f"{mod.__name__} should resolve models via model_roles.resolve_role_spec, "
            "not call get_latest_model directly"
        )
