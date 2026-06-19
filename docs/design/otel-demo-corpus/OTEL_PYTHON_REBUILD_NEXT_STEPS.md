# OTel Demo Python Rebuild — Next Steps

**Date:** 2026-06-19  
**Branch:** `feat/otel-python-rebuild` (worktree: `~/Documents/dev/startd8-otel-python-rebuild`)  
**Baseline commit:** Steps 0–6 landed in `aa1535d6`  
**Requirements / plan:** [OTEL_PYTHON_REBUILD_OPENAPI_REQUIREMENTS.md](./OTEL_PYTHON_REBUILD_OPENAPI_REQUIREMENTS.md) · [OTEL_PYTHON_REBUILD_OPENAPI_PLAN.md](./OTEL_PYTHON_REBUILD_OPENAPI_PLAN.md)

---

## Session outcome (done)

| Deliverable | Location |
| --- | --- |
| Steps 0–6 fixtures | `fixtures/otel-demo/{accounting-py,checkout-kafka-py,email-py,cart-py,product-reviews-py,payment-py}/` |
| Resolver + analyzer hooks | `scripts/python_capability_resolver.py`, `scripts/analyze_otel_demo_python_coverage.py` |
| Behavioral seed (Python payment) | `docs/design/model-benchmark/seeds-otel/seed-payment-py.json` (via `--emit-payment-python`) |
| GenAI optional seed | `seed-product-reviews-genai.json` (via `--include-genai-rpc`) |
| Unit tests | `tests/unit/test_otel_demo_fixtures.py` |
| Fixtures-only coverage | **59.0%** — `docs/design/python-capability-index/otel-demo-fixtures-coverage.json` |

---

## Outstanding (ordered execution)

### 1. Rebase and integrate with `main`

**Why:** Worktree was ahead 2 / behind 2 vs `origin/main` at handoff (docs benchmark merge landed on main).

```bash
cd ~/Documents/dev/startd8-otel-python-rebuild
git fetch origin
git rebase origin/main
# resolve conflicts if any
pytest tests/unit/test_otel_demo_fixtures.py tests/unit/test_python_capability_resolver.py -q
```

**Done when:** Branch rebased cleanly; unit tests green.

---

### 2. email-py OpenAPI deterministic codegen (Step 3 acceptance A2/A3)

**Why:** Wireframe has `schema.prisma` + `api.yaml` but hand-written `app/main.py` only; plan requires Role 1 contract emission.

```bash
cd ~/Documents/dev/startd8-otel-python-rebuild/fixtures/otel-demo/email-py
source ../../../.venv/bin/activate   # or repo-root venv
startd8 generate backend --check --gate
# if drift: startd8 generate backend && re-run --check --gate
```

**Done when:** `--check --gate` exits 0; generated `openapi_contract.py` / contract tests present.

**Follow-on (deferred unless codegen succeeds):**

- Role 3 `contexts.yaml` checkout→email consumer wiring
- Wave 0.3 locust / typed ApiClient for email HTTP

---

### 3. Merged coverage (upstream demo + fixtures)

**Why:** Fixtures-only report (59%) does not reflect combined corpus; gap doc target is ≥65% merged.

```bash
cd ~/Documents/dev/startd8-otel-python-rebuild
# Requires upstream clone at .otel-demo or /tmp/otel-demo-proto-fetch
python3 scripts/analyze_otel_demo_python_coverage.py \
  --fixture-root fixtures/otel-demo
# writes otel-demo-python-coverage.json (merged)
```

**Done when:** `docs/design/python-capability-index/otel-demo-python-coverage.json` refreshed; update gap doc if threshold met.

**Test hygiene:** `test_otel_demo_coverage_artifact_present` still asserts legacy **56%** upstream-only artifact — update assertion or split fixtures vs merged artifacts after refresh.

---

### 4. Behavioral matrix dry-run (Step 6)

**Why:** `seed-payment-py.json` is first behavioral-eligible **Python** OTel cell; validates payment-py leaf gRPC.

```bash
cd ~/Documents/dev/startd8-otel-python-rebuild
python3 scripts/run_behavioral_pilot.py --dry-run \
  --services payment-py \
  --seeds-dir docs/design/model-benchmark/seeds-otel \
  --repetitions 1
# optional spend: doppler run -p startd8 -c dev -- python3 scripts/run_behavioral_pilot.py --run \
#   --services payment-py --seeds-dir docs/design/model-benchmark/seeds-otel
```

**Done when:** Dry-run reports cell wiring OK (serve command, proto paths, charge suite target).

---

### 5. Push, PR, primary-clone hygiene

**Why:** Implementation exists only in worktree; primary clone still on stale `feat/otel-python-rebuild-openapi`.

```bash
cd ~/Documents/dev/startd8-otel-python-rebuild
git push -u origin feat/otel-python-rebuild
gh pr create --base main --title "..." --body "..."
```

Primary clone options:

- `git fetch && git checkout feat/otel-python-rebuild` in `~/Documents/dev/startd8-sdk`, or
- Retire `feat/otel-python-rebuild-openapi` after merge.

**Done when:** PR open against `main`; team knows canonical branch name.

---

## Optional / later

| Item | Notes |
| --- | --- |
| CRP prompt R1 on rebuild requirements | Plan checklist; not blocking |
| cap-dev-pipe pass on payment-py or product-reviews-genai | Full integration bucket 3 |
| Role 3 `contexts.yaml` for email consumer | After Step 3 codegen stable |
| Retire hand-written `email-py/app/main.py` | After generated backend owns routes |

---

## Progress log

| Step | Status | Notes |
| ---: | --- | --- |
| 1 | done | Rebased onto `origin/main`; 18 unit tests green |
| 2 | done | `email-py`: `generate backend --check --gate` passes (26 artifacts) |
| 3 | done | Merged coverage **70.6%** (`otel-demo-python+fixtures`) |
| 4 | done | Dry-run: `payment-py` × 3 models, ~$0.31 est.; added `--seeds-dir` |
| 5 | done | PR [#32](https://github.com/neil-the-nowledgeable/startd8-sdk/pull/32); primary clone stays on `feat/otel-python-rebuild-openapi` until worktree removed |
