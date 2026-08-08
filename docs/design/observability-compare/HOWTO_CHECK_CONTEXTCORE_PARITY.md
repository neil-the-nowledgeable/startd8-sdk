# How-To: Check & Maintain Cross-Repo Vocabulary Parity

Operational runbook for the vocabulary-parity guard. For *what it is and why*, see
[`CROSS_REPO_VOCABULARY_PARITY_GUARD.md`](./CROSS_REPO_VOCABULARY_PARITY_GUARD.md).

**One-liner:** the SDK copies ContextCore's observability vocabulary as strings; this checks the copy
hasn't drifted, and tells you how to fix it when it has.

---

## 1. The two layers (what runs where)

| Layer | Where it runs | Needs ContextCore? | Catches |
|---|---|---|---|
| **Offline guards** (`test_vocabulary_parity_offline.py`, 7 tests) | **every** `pytest` run, incl. SDK CI | **No** (uses the committed snapshot) | SDK mirror drifting from the snapshot |
| **Freshness guard** (`test_snapshot_matches_live_contextcore`) | only when ContextCore is importable | **Yes** (skips itself otherwise) | the **snapshot** drifting from the real ContextCore |
| **Live sibling** (`test_vocabulary_parity_contextcore.py`, 7 tests) | only when ContextCore is importable | **Yes** (whole file `importorskip`s) | SDK mirror drifting from the real ContextCore |

In plain SDK CI you get the **offline** layer for free. To exercise the **freshness + live** layers you
run the local checker below (or, eventually, the CH-2 CI lane).

---

## 2. Run the local check

```bash
# from the startd8-sdk repo root
scripts/check_contextcore_parity.sh
```

It auto-finds ContextCore in this order: **first arg → `$CONTEXTCORE_SRC` → `~/Documents/dev/ContextCore/src`
→ `../ContextCore/src`**. Override when your checkout is elsewhere:

```bash
scripts/check_contextcore_parity.sh /path/to/ContextCore/src
# or
CONTEXTCORE_SRC=/path/to/ContextCore/src scripts/check_contextcore_parity.sh
```

Extra pytest args pass through (e.g. `-v`):

```bash
scripts/check_contextcore_parity.sh -v
```

### Reading the result

**In sync (exit 0):**
```
ContextCore: …/ContextCore/src (commit c3cc7b8)
15 passed
✅ In sync — startd8 mirrors + the committed vocabulary snapshot match ContextCore (c3cc7b8).
```

**Drift (exit ≠ 0):**
```
❌ DRIFT — startd8's mirror sets or the committed snapshot are out of sync with ContextCore (<commit>).
   Fix one of:
     • reconcile the mirror in metric_descriptor.py / artifact_generator*.py, OR
     • refresh tests/unit/observability/data/contextcore_vocab_snapshot.json (see its _provenance), then re-run.
```

The failing test name tells you which layer tripped — read on.

---

## 3. Diagnose & fix a failure

There are two distinct failure modes. The failing **test name** tells you which:

### A. A `..._offline` test failed → the SDK mirror drifted from the snapshot
The SDK now references a vocabulary value the snapshot doesn't have, or stopped handling one it does.
This usually means **you (or a recent SDK change) touched the vocabulary** in `metric_descriptor.py` /
`artifact_generator*.py`.

- If the SDK change is **correct** and reflects a real ContextCore value → **refresh the snapshot**
  (§4), because the snapshot is behind.
- If the SDK change is **wrong** (a typo'd or invented kind/surface) → **fix the mirror** in the source
  module the assertion message names.

### B. `test_snapshot_matches_live_contextcore` failed → the snapshot drifted from ContextCore
ContextCore added/renamed/removed a vocabulary value; the committed snapshot is now stale. The failure
prints the exact per-set `{snapshot: [...], live: [...]}` diff.

→ **Refresh the snapshot** (§4). Then re-run the check — if an `..._offline` test *now* fails, ContextCore
added a value the SDK doesn't yet handle: **update the SDK mirror** to handle it (add the kind to
`REQUEST_KINDS`/`_KIND_DEFAULTS`/`UNGROUNDED_KINDS`, add the surface to the right set, etc.), which is
the whole point — the guard just caught a silent-mis-generation before it shipped.

---

## 4. Refresh the snapshot (the "keep it up to date" step)

The snapshot is a point-in-time copy; refresh it whenever the freshness guard flags drift, or right after
you intentionally add a vocabulary value in either repo.

**Step 1 — re-capture from ContextCore.** From the **ContextCore repo root**:

```bash
PYTHONPATH=src python3 - <<'PY'
import json
from contextcore.contracts import types as t
snap = {
    "SERVICE_KIND_VALUES":      sorted(t.SERVICE_KIND_VALUES),
    "SIGNAL_KIND_VALUES":       sorted(t.SIGNAL_KIND_VALUES),
    "METRICS_SURFACE_VALUES":   sorted(getattr(t, "METRICS_SURFACE_VALUES", []) or []),
    "DEPLOYMENT_RUNTIME_VALUES": sorted(getattr(t, "DEPLOYMENT_RUNTIME_VALUES", []) or []),
}
from contextcore.models.core import NON_K8S_TARGET_KINDS as nk
snap["NON_K8S_TARGET_KINDS"] = sorted(nk)
print(json.dumps(snap, indent=2))
print("# captured from ContextCore commit:", end=" ")
PY
git rev-parse --short HEAD   # ← the commit to record in _provenance
```

**Step 2 — update the JSON.** Paste the five value arrays into
`tests/unit/observability/data/contextcore_vocab_snapshot.json`, and update the `_provenance` block:
- `contextcore_commit` → the short SHA from Step 1
- `captured` → today's date

Keep the `_provenance` key — the tests ignore it; it's for humans and for reproducing the capture.

**Step 3 — verify & commit.**
```bash
scripts/check_contextcore_parity.sh          # expect ✅ In sync
git add tests/unit/observability/data/contextcore_vocab_snapshot.json
git commit -m "chore(observability): refresh ContextCore vocabulary snapshot (@ <sha>)"
```
If a new ContextCore value now trips an `..._offline` test, handle the SDK mirror in the **same** commit
or a follow-up (§3.B) — don't commit a snapshot the SDK can't satisfy.

---

## 5. When to run the check

- **After editing the SDK vocabulary** — any change to `REQUEST_KINDS` / `_KIND_DEFAULTS` /
  `UNGROUNDED_KINDS` / `NON_EMITTING_CONVENTION_SURFACES` / `NON_SCRAPEABLE_SURFACES` /
  `_TRIPLET_SIGNAL_KINDS` / `_NON_K8S_TARGET_KINDS`, or the `deployment_runtime=="unknown"` gate.
- **After pulling a ContextCore update** — especially anything touching `contracts/types.py` or
  `models/core.py`.
- **Before cutting a release / a pilot run** (Harbor / Thanos / Istio) — a new subject can exercise a
  kind/surface a stale mirror would mis-generate.
- The **offline** layer runs automatically in every `pytest` — you never have to remember it; you only
  run the script to exercise the **freshness/live** layers.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `❌ ContextCore not found` | The script couldn't locate a checkout. Pass the path: `scripts/check_contextcore_parity.sh <path/to/ContextCore/src>` or set `CONTEXTCORE_SRC`. It looks for `contextcore/contracts/types.py`. |
| `test_snapshot_matches_live_contextcore` **SKIPPED** even via the script | ContextCore isn't actually importable on the path given (wrong dir, or missing deps). The script prints the `ContextCore src:` it used — confirm `contextcore/contracts/types.py` lives under it. |
| Freshness passes but an older ContextCore lacks `METRICS_SURFACE_VALUES` etc. | Expected — the freshness guard compares only the sets the installed ContextCore actually exposes (older CC predates some), so it won't false-fail against an older CC. |
| Offline guards fail right after a `git pull` you didn't make | Someone changed the SDK vocabulary. Run the script against ContextCore: if it's a real upstream value, refresh the snapshot (§4); if not, the mirror change was wrong. |

---

## 7. Extending it (adding a new guarded vocabulary set)

When ContextCore introduces a *new* owned vocabulary the SDK starts mirroring, add a guard for it:

1. **ContextCore** exposes the value set (e.g. `FOO_VALUES` in `contracts/types.py`).
2. **SDK** mirrors it (a constant in `metric_descriptor.py` / `artifact_generator*.py`).
3. **Snapshot**: add a `FOO_VALUES` key to `contextcore_vocab_snapshot.json` (capture it in §4's snippet).
4. **Offline guard**: add a `test_..._offline` in `test_vocabulary_parity_offline.py` asserting the SDK
   mirror ⊆ `_SNAPSHOT["FOO_VALUES"]` (and the reverse direction if a missing handler is dangerous).
5. **Freshness**: add `FOO_VALUES` to the `live` dict in `test_snapshot_matches_live_contextcore` (guarded
   by `hasattr` if it may be absent on older ContextCore).
6. Run `scripts/check_contextcore_parity.sh` → expect ✅, commit.

> **Nice-to-have (not built):** a `--refresh`/`--write` flag on the script that regenerates the snapshot
> in place. Today the refresh is the manual §4 capture — deliberate, so a refresh is always a reviewed
> commit, never a silent overwrite.
