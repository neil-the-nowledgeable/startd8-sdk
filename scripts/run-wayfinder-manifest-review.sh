#!/usr/bin/env bash
set -euo pipefail

cd /Users/neilyashinsky/Documents/dev/startd8-sdk

exec ./run-defense-review.sh \
  --document-path /Users/neilyashinsky/Documents/dev/wayfinder/plans/wayfinder-contextcore-manifest-generate-plan.md \
  --feature-requirements /Users/neilyashinsky/Documents/dev/ContextCore/docs/ARTIFACT_MANIFEST_CONTRACT.md \
  --scope "Requirements traceability and architecture review — manifest generation plan vs contract spec" \
  --context-files "" \
  "$@"
