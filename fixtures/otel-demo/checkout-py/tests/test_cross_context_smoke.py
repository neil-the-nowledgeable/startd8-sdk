# GENERATED from prisma/schema.prisma (+ contexts.yaml) — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-tests-cross-context
# Source of truth: the Prisma schema and the contexts manifest.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba
# contexts-sha256: 074ccef8b51da9de39da42467d525aa1967723ddaaa0844f34156d15d1826547

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest


def test_email_remote_producer_smoke():
    """FR-6 remote: live producer round-trip when base URL is configured."""
    from pathlib import Path

    from startd8.backend_codegen.context_manifest import (
        filter_spec_for_context,
        load_contract_spec,
        parse_contexts,
    )
    from startd8.deploy_harness.context_smoke import (
        context_base_url_env_key,
        resolve_context_base_url,
        run_remote_producer_smoke,
    )

    contexts_text = Path("prisma/contexts.yaml").read_text(encoding="utf-8")
    (ctx,) = [c for c in parse_contexts(contexts_text) if c.id == 'email']
    base_url = resolve_context_base_url(ctx)
    if not base_url:
        pytest.skip(
            f"set {context_base_url_env_key('email')} or contexts.yaml base_url"
        )
    root = Path(".").resolve()
    raw = load_contract_spec(ctx.contract, project_root=root)
    schema_text = (root / "prisma" / "schema.prisma").read_text(encoding="utf-8")
    spec = filter_spec_for_context(raw, schema_text, ctx)
    outcome = run_remote_producer_smoke(base_url, spec=spec)
    assert outcome.status == "pass", outcome.reason or outcome.status

