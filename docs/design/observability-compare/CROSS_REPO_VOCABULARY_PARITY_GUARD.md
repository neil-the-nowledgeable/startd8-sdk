# Cross-Repo Vocabulary Parity Guard — What & Why

**Status:** shipped · **Provenance:** CEP CH-1 (PR #413) + homebrew CH-2 (PR #414), from the
[contract-health backlog](./CROSS_REPO_CONTRACT_HEALTH_ENHANCEMENT_BACKLOG.md).
**How-to / maintenance:** [`HOWTO_CHECK_CONTEXTCORE_PARITY.md`](./HOWTO_CHECK_CONTEXTCORE_PARITY.md).

---

## TL;DR

ContextCore **owns** the observability vocabulary — the set of legal service *kinds*, signal *kinds*,
metrics *surfaces*, deployment *runtimes*, and non-k8s *target kinds* (`#226` / `REQ-CCL-106`). The
startd8 SDK **hand-copies** that vocabulary as plain string sets, because it reads those values as
strings across an **optional-dependency boundary** (it can't hard-import ContextCore's enums). If the
two drift — ContextCore renames or adds a kind and the SDK's copy goes stale — the SDK **silently
mis-generates** observability artifacts (a new service kind falls back to the HTTP transport default; a
renamed surface re-opens the dead-SLI `#274` class).

This guard makes that drift **fail loudly** instead of shipping silently — and, crucially, it does so
**in normal SDK CI**, where ContextCore isn't installed.

---

## The problem (and the trap we fell into)

There *was* a parity test — `tests/unit/observability/test_vocabulary_parity_contextcore.py` — that
compared the SDK's mirror sets against ContextCore's live enums. But it opens with:

```python
ctypes = pytest.importorskip("contextcore.contracts.types")
```

ContextCore is an **optional dependency, absent from the SDK venv**, so `importorskip` makes the
**entire file skip in every SDK CI run**. The guard existed but never fired.

Worse: a later change (**#359**) *expanded* that file to **seven** parity guards (service kinds, the
signal triplet, two metrics-surface sets, the deployment-runtime gate token, and non-k8s target kinds)
— all behind the same dead `importorskip`. So the surface being guarded grew while the guard stayed
asleep. That's the classic "green that's lying": the test file looks like coverage, but it's a no-op in
the one environment (SDK CI) that matters.

---

## What we built

Three cooperating pieces (plus a local runner):

| Piece | File | Role |
|---|---|---|
| **The snapshot** | `tests/unit/observability/data/contextcore_vocab_snapshot.json` | A committed, point-in-time copy of ContextCore's five vocabulary sets, with `_provenance` (source commit + refresh instructions). The offline source of truth. |
| **Offline guards** | `tests/unit/observability/test_vocabulary_parity_offline.py` | The seven parity assertions, re-expressed against the **snapshot** with **no `importorskip`** — so they **fire in SDK CI**. |
| **Freshness guard** | same file, `test_snapshot_matches_live_contextcore` | Asserts the snapshot `==` the **live** ContextCore enums *when ContextCore is importable*. Skips **only itself** when CC is absent. Keeps the snapshot from silently rotting. |
| **Local runner (homebrew CH-2)** | `scripts/check_contextcore_parity.sh` | Points at a ContextCore checkout and runs the offline + freshness + original-`importorskip` guards with CC on `PYTHONPATH`, so *everything* fires. A local alternative to a GitHub Actions lane. |

The original `test_vocabulary_parity_contextcore.py` is **left untouched** — it stays the "SDK mirror vs
live ContextCore" upgrade-path check for when CC *is* present.

---

## Why this design

- **Vendored snapshot, not a hard import.** The SDK can't import ContextCore (optional dep). A committed
  snapshot is the only way to check parity *offline*. The cost — the snapshot can go stale — is paid by
  the freshness guard.
- **Two guards, opposite directions.**
  - *Offline* catches **SDK-side drift** immediately, everywhere: the SDK adds/renames a kind not in the
    snapshot, or stops handling one → fail at PR time in SDK CI.
  - *Freshness* catches **ContextCore-side drift**: ContextCore adds/renames a value → the snapshot no
    longer equals live → fail wherever CC is present (a dev machine, or the local runner).
  Together they close the loop the single `importorskip` test left open.
- **Local runner "for now" instead of a CI lane.** The full CH-2 is a cross-repo GitHub Actions lane
  that installs both repos and diffs. The homebrew script delivers the same *value* (fire the CC-present
  guards on demand) without any GitHub Actions setup — the right first step, and enough for a
  single-maintainer workflow. The CI lane remains the deferred `new-capability` half of CH-2.
- **Fail loud, not silent-degrade.** Every assertion carries the reconcile instruction in its message,
  so a failure tells you *exactly* which value drifted and what to do.

---

## The vocabulary it guards

Five sets, each **owned by ContextCore**, **mirrored by the SDK**:

| Vocabulary | ContextCore owner (source of truth) | startd8 mirror(s) |
|---|---|---|
| Service kinds | `contextcore.contracts.types.SERVICE_KIND_VALUES` | `REQUEST_KINDS`, `_KIND_DEFAULTS`, `UNGROUNDED_KINDS` (`metric_descriptor.py`) |
| Signal kinds | `…types.SIGNAL_KIND_VALUES` | `_TRIPLET_SIGNAL_KINDS` (`artifact_generator_generators.py`) |
| Metrics surfaces | `…types.METRICS_SURFACE_VALUES` | `NON_EMITTING_CONVENTION_SURFACES`, `NON_SCRAPEABLE_SURFACES` (`metric_descriptor.py`) |
| Deployment runtimes | `…types.DEPLOYMENT_RUNTIME_VALUES` | the `"unknown"` fail-closed gate token (`artifact_generator.py`) |
| Non-k8s target kinds | `contextcore.models.core.NON_K8S_TARGET_KINDS` | `_NON_K8S_TARGET_KINDS` (`artifact_generator.py`) |

Each assertion direction matters — e.g. for service kinds we check **both** "no SDK kind is unknown to
ContextCore" *and* "the SDK partitions every real ContextCore kind (except `unknown`)", because the
second is the dangerous one: a new upstream kind the SDK doesn't handle falls silently to the transport
default.

---

## Where it fits

This is one guard in a broader **cross-repo contract-health** effort that hardened the ContextCore→SDK
onboarding-metadata boundary this cycle:

- **Golden round-trips** — `test_onboarding_metadata_golden_roundtrip.py` (HTTP idiom, #352/#356) and
  `test_grpc_thanos_idiom_roundtrip.py` (gRPC/Thanos idiom, #361): the *real producer-shape* metadata
  driven through the real SDK loader, so a field rename/re-nesting can't pass as it would for two mirror
  tests.
- **Loader robustness** — legible failures on malformed onboarding-metadata (#357, CH-7/CH-8).
- **This parity guard** — the *vocabulary* half: the enums the metadata's fields draw from.

Full opportunity map + what's still open: the
[contract-health backlog](./CROSS_REPO_CONTRACT_HEALTH_ENHANCEMENT_BACKLOG.md) (CH-3…CH-6 remain).
