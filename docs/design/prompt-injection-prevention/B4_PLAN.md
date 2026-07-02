# FR-B4 Implementation Plan (paired with B4_REQUIREMENTS.md)

**Version:** 0.1 (Draft) → discoveries below feed the v0.2 requirements update
**Date:** 2026-07-02

Anchors from `src/startd8/backend_codegen/ai_layer.py` on `feat/prompt-injection-2b-i`.

---

## Discoveries (planning vs. v0.1 assumptions)

| v0.1 assumed | Planning revealed | Impact |
|---|---|---|
| **FR-B4-4: add a TTL + `holder_id` + `expires_at` lease for stale-lock recovery** (the substrate handoff said "ContextCore has no TTL — must add") | **PROVEN: a held `flock` is auto-released by the OS when the holder process dies** (`/tmp` experiment: parent acquires after a child holding the lock exits without unlocking). So if the pass **holds the flock across the whole `call_ai_service`**, a crashed/killed worker's claim is reclaimed automatically — **no TTL, no `expires_at`, no `holder_id`, no steal logic, no sweep.** | **FR-B4-4 largely DELETED.** The TTL machinery was premised on the *short-held-flock + written claim record* design (OQ-2 alt B), which leaves stale records. The *held-flock* design (OQ-2 alt A) doesn't. Massive simplification. |
| **FR-B4-3: vendor ContextCore `file_lock` (`state.py:55-90`) as-is** | ContextCore's POSIX `_lock_file` uses **blocking `LOCK_EX`** (Windows uses non-blocking `LK_NBLCK`) — a divergence. **Blocking is WRONG for us**: a contender would *wait* for the lock, not fail-fast reject. | Vendor the *pattern*, not the code: use **`LOCK_EX | LOCK_NB`** (POSIX) so a held lock raises `BlockingIOError` → immediate `in_flight` reject. Windows `LK_NBLCK` already non-blocking. OQ-3 resolved. |
| **OQ-2: held-flock vs. flock-guarded claim record — planning to decide** | Held-flock is both **simpler** AND gets crash recovery free (above). The claim-record approach adds TTL complexity for no benefit here. | **Held-flock chosen.** |
| **OQ-1: lock-file lifecycle (delete vs. leave vs. sweep)** | With held-flock the lock files are **0-byte sentinels**, created once per key-tuple, reused. Accumulation is bounded-ish (one empty file per distinct key ever seen) and cheap. | Leave-and-reuse; a periodic sweep is a deferrable nicety, not required. OQ-1 resolved. |
| **FR-B4-4 key resolution unclear (OQ-4)** | Both target shapes are `def <pass>(<request_field>: str, session, source_id: str)` (`ai_layer.py:842, 956`). The only sensible keys are **`source_id`** and the **`request_field`** (signature params). | Keys MUST be a subset of the pass's signature params; validate at build time. Simple. OQ-4 resolved. |
| Reject contract shape unknown | Existing shapes: `{"status": "needs_more_data"/"rejected"/"ok", "created": {Entity: n}}` (`ai_layer.py:785, 958, 1023`). | `{"status": "in_flight", "created": {out: 0}}` fits exactly. FR-B4-5 confirmed. |

**Heuristic check:** 1 of 9 requirements largely deleted (FR-B4-4), 4 open questions resolved, 1 requirement corrected (FR-B4-3 non-blocking). ~55% of the substance moved — the loop caught real over-engineering *before* code.

---

## Plan (post-discovery, held-flock design)

### Step 1 — Grammar (FR-B4-1)
- `Guards` gains `single_in_flight_by: Tuple[str, ...] = ()`.
- Add `single_in_flight_by` to `_GUARDS_KEYS`; parse in `_parse_guards` (must be a list of strings).
- Build-time validation deferred to render (where the pass signature params are known): each key MUST be
  `source_id` or the pass's `request_field` — else `ValueError`.

### Step 2 — guards.py lease primitive (FR-B4-3/8/9), bump to v5
Emit into `app/ai/guards.py` a stdlib helper:
```python
@contextlib.contextmanager
def in_flight_claim(key: str):
    """Non-blocking, cross-process (same-host) exclusive claim over `key`, held for the block.
    Yields True if acquired, False if another live holder holds it (fail-fast). A crashed holder's
    claim is auto-released by the OS (flock on fd close) — no TTL needed."""
    import fcntl / msvcrt (platform)
    d = _inflight_dir()                      # <tempdir>/<app>/ai-inflight/, mkdir -p, fallback
    p = d / (hashlib.sha256(key.encode()).hexdigest()[:32] + ".lock")
    f = open(p, "w")
    try:
        try:
            _flock_nb(f)                     # LOCK_EX|LOCK_NB  /  LK_NBLCK
        except (BlockingIOError, OSError):
            yield False; return
        yield True
    finally:
        try: _unlock(f)
        finally: f.close()
```
- `_inflight_dir()`: `Path(tempfile.gettempdir()) / <app-slug> / "ai-inflight"`, created lazily, with a
  fallback (mirrors ContextCore `state.py` fallback). Never writes into the source tree (FR-B4-9).
- Pure stdlib (`fcntl`/`msvcrt`, `contextlib`, `hashlib`, `tempfile`, `pathlib`). Bump `__guards_version__` → "5".

### Step 3 — Emission (FR-B4-2/5/6) in source-bound + scoped shapes
Only when `ps.guards.single_in_flight_by`:
- import `in_flight_claim`.
- key expr = `f"{ps.name}|" + "|".join(str(<param>) for <param> in keys)`.
- wrap the call + persist:
```python
    with in_flight_claim(_key) as _ok:
        if not _ok:
            logger.warning("in-flight rejected %s", <name>, extra={"event": "ai_in_flight_rejected", ...})
            return {"status": "in_flight", "created": {<out>: 0}}
        result = call_ai_service(...)
        ...existing validate/provenance/persist...
```
Indent the existing call+persist body under the `with`. (Read passes untouched — FR-B4-6.)

### Step 4 — Observability (FR-B4-7)
`ai_in_flight_rejected` structured log in the emitted pass (app runtime logger). No steal event (no TTL).

### Step 5 — Tests
- Grammar: parse `single_in_flight_by`; reject non-list; reject a key not in the pass params.
- guards.py: `in_flight_claim` yields True first, False while held (same process, second claim on same key);
  releases on exit; **subprocess** test — a child holds the claim, parent gets False; child dies → parent True.
- Emission: rendered source-bound + scoped pass with the guard imports `in_flight_claim`, wraps the call,
  returns `in_flight`; a pass without the guard is unchanged (no import).

### Cross-cutting
- The held-flock spans `call_ai_service` (30–60s). Acceptable: flock is advisory + cheap; a hung worker is
  bounded by the uvicorn/gunicorn worker timeout (→ fd closed → released). Document this.
- NR-1 (multi-host) unchanged — flock is node-local; k8s multi-replica is a documented boundary.

## Open risks / notes
- **OQ-5 (TTL configurability)** → moot (no TTL). **OQ-7 (force on auto-send)** → keep independent (don't
  force; a `stricter` pass MAY add it). **OQ-6 (testing)** → subprocess test is feasible + gated.
