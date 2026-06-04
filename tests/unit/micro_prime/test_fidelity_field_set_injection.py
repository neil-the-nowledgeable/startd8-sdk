"""FR-MPF-1 — field-set/enum authority reaches the micro-prime generation prompt.

Completes FR-CAR-5b/8a: the per-feature Prisma field-set + enum + module-path-negative block the lead
path builds into ``gen_context["upstream_interfaces"]`` MUST be forwarded into the micro-prime prompt,
alongside the already-landed (8b) static ``convention_guidance``. These tests assert the *wiring* (the
authority crosses the boundary and renders); the *efficacy* acceptance (measured adherence lift) is a
separate cross-tier measurement per the plan.
"""

from __future__ import annotations

from startd8.forward_manifest import ForwardManifest
from startd8.micro_prime.context import MicroPrimeContext


def _manifest() -> ForwardManifest:
    # Minimal manifest — from_prime only stores it; these tests exercise the context plumbing.
    return ForwardManifest(file_specs={})


def test_from_prime_forwards_upstream_interfaces():
    """from_prime must forward gen_context['upstream_interfaces'] (it previously dropped it)."""
    field_set_block = (
        "Data-model field sets — use ONLY these fields, do not invent:\n"
        "- JobDescription: id, title, company, rawText, createdAt"
    )
    ctx = MicroPrimeContext.from_prime(
        {"upstream_interfaces": field_set_block},
        _manifest(),
        ["app/job_export.py"],
        ollama_available=True,
    )
    assert ctx.upstream_interfaces == field_set_block


def test_from_prime_upstream_interfaces_defaults_empty():
    """Absent in gen_context → empty string (backward-compatible; no spurious block)."""
    ctx = MicroPrimeContext.from_prime(
        {}, _manifest(), ["app/job_export.py"], ollama_available=True,
    )
    assert ctx.upstream_interfaces == ""


def test_context_field_default_is_backward_compatible():
    """The new frozen-dataclass field is defaulted → existing constructors still work."""
    ctx = MicroPrimeContext(manifest=_manifest(), target_files=["x.py"])
    assert ctx.upstream_interfaces == ""


def test_process_file_with_context_merges_field_set_before_convention(monkeypatch):
    """engine folds upstream_interfaces into domain_constraints, field-set first then convention idiom.

    We capture the domain_constraints handed to process_file rather than running a real generation.
    """
    from startd8.micro_prime import engine as engine_mod

    captured = {}

    def _fake_process_file(self, file_spec, manifest, skeleton, **kwargs):
        captured["domain_constraints"] = kwargs.get("domain_constraints")
        return "SENTINEL"

    monkeypatch.setattr(engine_mod.MicroPrimeEngine, "process_file", _fake_process_file, raising=True)

    eng = engine_mod.MicroPrimeEngine()
    ctx = MicroPrimeContext(
        manifest=_manifest(),
        target_files=["app/job_export.py"],
        binding_constraints=["existing binding constraint"],
        upstream_interfaces="FIELD-SET-AUTHORITY",
        convention_guidance="CONVENTION-IDIOM",
    )
    result = eng.process_file_with_context(file_spec=None, context=ctx, skeleton=None)
    assert result == "SENTINEL"

    dc = captured["domain_constraints"]
    assert "FIELD-SET-AUTHORITY" in dc
    assert "CONVENTION-IDIOM" in dc
    # Order: binding constraints, then field-set authority (per-project truth), then convention idiom.
    assert dc.index("FIELD-SET-AUTHORITY") < dc.index("CONVENTION-IDIOM")
    assert "existing binding constraint" in dc


# --- FR-MPF-1 self-cap (v0.3) -------------------------------------------------------------------
# The field-set block merges into domain_constraints, which prompt_builder._truncate_to_budget NEVER
# trims. Without a cap, a large block evicts the few-shot examples (a primary cheap-model adherence
# lever) and can still overflow the input budget. These tests lock that regression shut.


def test_cap_authority_block_bounds_and_marks():
    """An oversized block is truncated to <= max_chars, at a whole-line boundary, with a marker."""
    from startd8.micro_prime.engine import _AUTHORITY_TRUNCATION_MARKER, _cap_authority_block

    big = "\n".join(f"- Entity{i}: id, name, value, createdAt" for i in range(200))
    capped = _cap_authority_block(big, 300)

    assert len(capped) <= 300
    assert _AUTHORITY_TRUNCATION_MARKER in capped
    # Whole-line truncation: every retained body line is a complete field-set line (nothing dangles).
    body = capped.rsplit("\n", 1)[0]  # drop the marker line
    assert all(ln == "" or ln.startswith("- Entity") for ln in body.splitlines())


def test_cap_authority_block_passthrough():
    """Small blocks and a disabled cap (<=0) pass through unchanged."""
    from startd8.micro_prime.engine import _cap_authority_block

    small = "- JobDescription: id, title, company, rawText, createdAt"
    assert _cap_authority_block(small, 1000) == small
    assert _cap_authority_block(small, 0) == small


def test_process_file_with_context_caps_oversized_upstream(monkeypatch):
    """The merge applies the budget-derived cap, so a huge field-set block reaches process_file bounded."""
    from startd8.micro_prime import engine as engine_mod

    captured = {}

    def _fake_process_file(self, file_spec, manifest, skeleton, **kwargs):
        captured["dc"] = kwargs.get("domain_constraints")
        return "OK"

    monkeypatch.setattr(engine_mod.MicroPrimeEngine, "process_file", _fake_process_file, raising=True)

    eng = engine_mod.MicroPrimeEngine()
    huge = "\n".join(f"- Entity{i}: id, name, value" for i in range(500))
    ctx = MicroPrimeContext(
        manifest=_manifest(),
        target_files=["app/x.py"],
        upstream_interfaces=huge,
    )
    eng.process_file_with_context(file_spec=None, context=ctx, skeleton=None)

    cap = (eng._config.input_token_budget * engine_mod._CHARS_PER_TOKEN) // engine_mod._AUTHORITY_BUDGET_DIVISOR
    authority_element = next(c for c in captured["dc"] if "Entity0" in c)
    assert len(authority_element) <= cap
    assert len(authority_element) < len(huge)  # it was actually capped


def test_cap_prevents_fewshot_eviction():
    """Non-regression: an uncapped authority block evicts the few-shot example; the cap keeps it.

    Exercises the real helper + the real budget trimmer together. The example header is in
    _truncate_to_budget's removable set; the domain-constraints section is NOT — so only bounding the
    authority block keeps the prompt under budget without sacrificing the few-shot example.
    """
    from startd8.micro_prime.engine import _cap_authority_block
    from startd8.micro_prime.prompt_builder import _truncate_to_budget

    token_budget = 200
    core = "# Task: implement\n# Now implement this:\nstub\n\n"
    example = "# Example (completed):\n" + ("x" * 300) + "\n\n"
    big_authority = "- " + ("y" * 2000)  # one giant field-set line

    def _prompt(domain_block: str) -> str:
        return (
            core
            + "# Domain constraints (MUST follow these):\n"
            + domain_block
            + "\n\n"
            + example
        )

    # Uncapped: trimmer removes the few-shot example (and is STILL over budget) — the regression.
    uncapped = _truncate_to_budget(_prompt(big_authority), token_budget)
    assert "# Example (completed):" not in uncapped

    # Capped (same cap the engine uses ≈ token_budget chars): the few-shot example survives.
    cap = (token_budget * 4) // 4
    capped = _truncate_to_budget(_prompt(_cap_authority_block(big_authority, cap)), token_budget)
    assert "# Example (completed):" in capped
