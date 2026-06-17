# Per-Runtime rlimit Profiles — Fair Resource Bounds for Java/C#/Go Cells

**Version:** 0.1 (Draft sketch)
**Date:** 2026-06-17
**Scope:** cross-corpus (Online Boutique + OTel demo), cross-track (structural `run_sandboxed`
+ behavioral `run_service_sandboxed`)
**Related:** `benchmark_matrix/sandbox.py` (FR-44), `MOCK_LLM_SIDECAR_SPEC.md` §5,
[[project_summer2026_model_benchmark]]

---

## 1. Problem

The sandbox applies **one uniform `SandboxConfig`** to every language (`sandbox.py`):

```
cpu_seconds=60   mem_mb=2048   max_processes=256   max_file_mb=64   wall_timeout_s=120
```

`mem_mb` is enforced as **`RLIMIT_AS` / `RLIMIT_DATA`** — i.e. **virtual address space**, not RSS.
That is the wrong tool for reserve-heavy runtimes:

- **JVM** (`ad`, fraud-detection) reserves multi-GB of *virtual* address space at boot (max heap +
  metaspace + per-thread stacks + code cache) regardless of actual usage → a 2 GB `RLIMIT_AS` makes it
  fail to start ("Could not reserve enough space" / "insufficient memory").
- **.NET CoreCLR** (`cart`, accounting) similarly reserves large virtual ranges.
- **Go** reserves very large virtual arenas on 64-bit — `RLIMIT_AS` is notoriously hostile to Go.
- **V8/Node** reserves a sizable virtual heap too.

Because a tripped limit kills the process → readiness fails → the cell **degrades** (FR-T2-2,
correctly *not* scored 0). The bug: a Java/C#/Go cell that the model implemented **correctly** can
silently `degrade` purely because the *uniform* virtual-memory cap doesn't fit the runtime. CPU
(60s) and wall (120s) are likewise too tight for cold-start-slow toolchains (Gradle daemon + JIT;
`dotnet restore`/build), compounding false degrades. Net effect: **Java/C#/Go look worse than they are
— exactly the languages the OTel corpus adds to bolster.**

## 2. Key distinction

`RLIMIT_AS` bounds **virtual** memory; the thing we actually want to bound is **physical (RSS)**.
RSS bounding isn't available via `setrlimit` (RLIMIT_RSS is a no-op on modern Linux; absent on macOS).
So for reserve-heavy runtimes, `RLIMIT_AS` should be **dropped**, with runaway memory bounded instead
by the *other* guards (wall timeout + nproc + fsize) until a v2 cgroup/container path lands (consistent
with the existing FR-44 "kernel isolation deferred" note). Tighter `RLIMIT_AS` stays only where it
works (Python).

## 3. Design

### 3.1 Per-language profiles (starting values — calibrate per §6)

| Language | RLIMIT_AS (mem_mb) | cpu_seconds | max_processes | wall_timeout_s | rationale |
|---|---|---|---|---|---|
| python | 2048 (keep) | 60 | 256 | 120 | CPython modest virtual; baseline |
| nodejs | 4096 | 90 | 256 | 150 | V8 virtual heap + npm |
| go | **unset** | 120 | 512 | 240 | huge virtual arenas; compile CPU-heavy |
| java | **unset** | 180 | 1024 | 300 | multi-GB virtual at boot + many threads; Gradle+JIT cold start |
| csharp | **unset** | 180 | 1024 | 300 | CoreCLR virtual reserve + slow dotnet restore/build |

"unset" = do **not** call `setrlimit(RLIMIT_AS/RLIMIT_DATA)` for that language; rely on CPU + wall +
nproc + fsize. (Optionally a very-high ceiling, but for Go/JVM even 16 GB virtual can be too low, so
unset is cleaner than a guessed ceiling.)

### 3.2 Mechanism
- Add `RLIMIT_PROFILES: Dict[str, SandboxConfig]` in `sandbox.py` (or a `profile_for(language)` →
  `SandboxConfig`). `_rlimit_preexec` skips `RLIMIT_AS/RLIMIT_DATA` when `mem_mb is None`.
- **Selection by cell language:** `run_behavioral_cell` already resolves `target_files` →
  `resolve_language(...)`; pass that language to pick the profile. `run_sandboxed` (structural) gets the
  language from the scoring caller. Default profile = python (today's behavior) when language unknown.

### 3.3 Honesty / provenance (no silent relaxation)
- Record the applied profile name + the actual limits in `isolation_level` / the result (the module
  already tracks "controls actually applied"). A relaxation that isn't logged is a silent cap — the
  same anti-pattern the contamination firewall avoids. The report shows, e.g.,
  `isolation_level="rlimits(java: AS=unset,cpu=180,nproc=1024)+seatbelt-loopback"`.

## 4. Security posture

- **Bounded relaxation, network + secrets untouched.** This changes *resource* bounds only —
  `no_network`, `scrub_env`, loopback-only, and process-group teardown are unchanged. Runaway memory is
  still bounded (wall timeout + nproc + fsize); fork-bombs still bounded (nproc + setsid group kill).
- This is the legitimate "known-corpus" relaxation flagged in `MOCK_LLM_SIDECAR_SPEC.md` §5: the
  benchmark target is known, so we right-size resource envelopes to real runtimes — **without** opening
  egress (which would weaken the contamination/exfiltration guarantees that protect benchmark integrity;
  untrusted = the model's output, not the target app).
- True physical-memory (RSS) bounding for reserve-heavy runtimes is the v2 cgroup/Firecracker/Docker
  path (existing FR-44 deferral; ADR-style trigger when runs move to Linux/containers).

## 5. Impact
- Fixes false `degrade` on correctly-implemented **Java / C# / Go** cells across **both** corpora and
  **both** tracks. Directly unblocks the OTel corpus's reason for existing (Java=`ad`, C#=`cart`,
  Go=`checkout`/`product-catalog`) and de-noises OB's thin Java/C# cells.
- Pure environment fix — it changes *which cells are scorable*, not how quality is scored.

## 6. Open questions
- **OQ-RL-1 — empirical calibration.** The §3.1 numbers are informed starting points; boot a real JVM
  (`ad`) and .NET (`cart`) cell and measure peak virtual/RSS + cold-start CPU/wall to set defensible
  values. Don't ship guesses as if measured.
- **OQ-RL-2 — `RLIMIT_NPROC` is per-UID on Linux** (counts all processes of the user, not just this
  group). On this **multi-worktree/parallel-agent** host ([[reference_multiworktree_env]]), a low nproc
  could fail legitimate forks under concurrency. Consider raising it or noting the host caveat.
- **OQ-RL-3 — keep any AS ceiling for go/java/csharp,** or fully unset? Unset loses the virtual-runaway
  guard but is the only thing that reliably boots them; revisit when cgroup RSS bounding lands.
- **OQ-RL-4 — macOS vs Linux.** `RLIMIT_AS` is already noted "unreliable on macOS"; confirm the profile
  behaves on both (the dev host is macOS; real runs may move to Linux).

## 7. Effort
`RLIMIT_PROFILES` map + `mem_mb=None` skip in `_rlimit_preexec` + language→profile selection in the two
run entry points + provenance string: **small, ~½ session + calibration (OQ-RL-1).** No new deps, no
network/secret change. Offline-testable (assert the right profile + limits are chosen per language;
assert `RLIMIT_AS` is skipped when `mem_mb is None`).

---

*Draft 0.1 — sketch. Root cause is concrete: uniform `RLIMIT_AS=2 GB` (virtual, not RSS) silently
degrades correctly-built Java/C#/Go cells. Fix is a per-language profile that drops `RLIMIT_AS` for
reserve-heavy runtimes and right-sizes CPU/wall, recorded honestly, with the network/secret controls
deliberately untouched.*
