#!/usr/bin/env bash
set -euo pipefail

cd /Users/neilyashinsky/Documents/dev/startd8-sdk
source .venv/bin/activate

startd8 workflow run architectural-review-log -c /dev/stdin <<'EOF'
{
  "document_path": "/Users/neilyashinsky/Documents/dev/ContextCore/docs/plans/implementation-plan-defense-in-depth.md",
  "feature_requirements": ["/Users/neilyashinsky/Documents/dev/ContextCore/docs/plans/feature-enhancement-defense-in-depth.md"],
  "agents": ["anthropic:claude-opus-4-20250514"],
  "max_suggestions": 20,
  "scope": "Requirements traceability and architecture review — dual-document gap-hunting mode",
  "context_files": [
    "/Users/neilyashinsky/Documents/dev/ContextCore/contextcore_governance_docs/SECURITY_AND_RBAC.md",
    "/Users/neilyashinsky/Documents/dev/ContextCore/docs/reference-architecture-contextcore.md",
    "/Users/neilyashinsky/Documents/dev/ContextCore/docs/OPERATIONAL_RESILIENCE.md",
    "/Users/neilyashinsky/Documents/dev/ContextCore/docs/OPERATIONAL_RUNBOOK.md",
    "/Users/neilyashinsky/Documents/dev/ContextCore/docs/OTEL_CONVENTIONS_AUDIT.md",
    "/Users/neilyashinsky/Documents/craft/Lessons_Learned/sdk/Design_Docs_LESSONS_LEARNED.md"
  ],
  "max_context_chars": 200000,
  "warn_cost_usd": 0.50,
  "max_cost_usd": 2.00,
  "enable_triage": true,
  "substantially_addressed_threshold": 3,
  "init_if_missing": true
}
EOF
