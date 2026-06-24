# Round 3 Containment Spike — Can the existing sandbox co-run N untrusted servers?

**Date:** 2026-06-23
**Question:** Can `benchmark_matrix/sandbox.py`'s `run_service_sandboxed` safely co-run the 9
Online Boutique microservices (all model-generated, all untrusted) wired to each other over
loopback — or is Docker-per-service required for Round 3?
**Status:** Spike complete. **Verdict: B — current sandbox works, with a named containment
weakening that must be recorded (FR-7a).**

---

## 1. Platform + actual sandbox mechanism (MEASURED)

| Property | Value |
|---|---|
| Platform | `Darwin` (macOS) |
| `sandbox_caps()` on this host | `{rlimits: true, sandbox_exec: true, unshare: false, docker: true}` |
| Network isolation mechanism | **macOS Seatbelt** via `/usr/bin/sandbox-exec` (`isolation_level = rlimits+seatbelt-loopback`) |
| Loopback-only profile (`_wrap_loopback_only`) | `(allow default)(deny network*)` then re-allow `network-bind`/`network-inbound`/`network-outbound` scoped to `localhost:*` |

**Isolation granularity: PER-PROCESS, NOT per-network-namespace.** On macOS the mechanism is a
Seatbelt *policy profile* applied to each `sandbox-exec` child process; there is **no network
namespace**. Process-group containment comes from `os.setsid()` in `_rlimit_preexec` +
`os.killpg` teardown. The Linux `unshare -rn` path (which *would* give each server its own netns
with an isolated loopback) is **not available here** (`unshare: false`).

**Consequence — SHARED loopback plane (INFERRED from mechanism, CONFIRMED by experiment):** every
Seatbelt-sandboxed process binds and connects on the **same host `127.0.0.1`**. The profile allows
loopback bind/connect but does **not** restrict *which* loopback port a process may dial. So all N
co-located servers share one loopback plane; there is no per-server loopback isolation on macOS.

---

## 2. Experiment run + raw results (MEASURED unless noted)

Two experiments driving the real `run_service_sandboxed` with throwaway `http.server`-style
servers (script probes a peer, an external host, and an arbitrary host loopback port from *inside*
the sandbox), each launched in its own thread to force concurrency.

**Property 1 — Co-existence (MEASURED, PASS).** Exp 2 ran **3 sandboxed servers concurrently**;
all three reported `ready=True`, the A-probe completed in `0.87s` wall (no serialization/wedging).
The harness does not serialize: each `run_service_sandboxed` is an independent `Popen` + readiness
poll, so N threads/processes scale fine. Exp 1 ran 2 concurrent in `1.45s` wall.

**Property 2 — Loopback peer reachability (MEASURED, PASS).** With deterministic ordering (B bound
first, held open 6s), sandboxed **A reached sandboxed B**: `peer_reach: true` for
`127.0.0.1:<B_port>`. The dependency-wiring Round 3 needs (service A dials service B) works under
Seatbelt loopback. (Exp 1 showed `ConnectionRefusedError` only as a timing artifact — B not yet
bound when A probed — not an isolation block; Exp 2 corrected the ordering and got `true`.)

**Property 3 — Egress containment (MEASURED, PASS for external; MEASURED WEAKNESS for siblings).**
- External egress: **all** servers got `egress: DENIED:PermissionError` connecting to
  `1.1.1.1:53`. The public-internet block holds per-process for a co-located fleet — Seatbelt is
  applied to each child independently, so adding more servers does not erode external denial.
- **Sibling/host loopback (the weakness): a sandboxed server reached an arbitrary loopback port it
  was never wired to.** Exp 1: a sandboxed server reached an **unsandboxed host service** on a
  random `127.0.0.1` port → `host_loopback_reach: true`. Because the profile allows
  `network-outbound (remote ip "localhost:*")` with no port allowlist, **any** sandboxed server can
  dial **any** loopback port — a sibling it shouldn't talk to, OR a host-side service on 127.0.0.1.

**Teardown (MEASURED, PASS).** After both experiments, `pgrep -f srv.py` returned empty and the
server ports were unbound — `_terminate_group` (SIGTERM→SIGKILL on the process group) reaped every
server with **zero orphans**, even with N concurrent.

---

## 3. Verdict: **B — current sandbox suffices, with one recorded containment weakening**

**Single concrete reason:** all three Round-3-critical properties (concurrent co-existence,
loopback peer reachability, external-egress denial, clean teardown) are **measured working** for a
co-located fleet on this macOS host — so Docker is **not forced**. BUT the loopback plane is
**shared and unrestricted**: a malicious/buggy service can reach *any* sibling or host loopback
port, not just its declared dependencies. This is a real, honest weakening vs. a per-netns design,
but it is **bounded** (loopback only; external egress still denied; processes reaped) and acceptable
for a benchmark where all 9 services are built by the *same* model and run on a disposable host.

---

## 4. FR-7a — exact containment weakening to record

> **FR-7a (Round 3 isolation, recorded weakening).** On macOS (Seatbelt, no netns), the N
> co-located untrusted services share **one unrestricted loopback plane**. The sandbox guarantees
> (a) external-egress denial and (b) per-process resource limits and (c) process-group teardown,
> but does **NOT** restrict *which* `127.0.0.1:<port>` a sandboxed service may dial. Therefore a
> compromised service can reach **any sibling service AND any host-side loopback service**, not only
> its wired dependencies. Round 3 accepts this because: all 9 services are same-model output (no
> cross-tenant adversary), the host is disposable, and external exfiltration remains blocked.
> **Mitigations to record:** (i) run the fleet on free, randomized ports the host process does not
> reveal to the services beyond their declared deps; (ii) ensure **no sensitive host service** (no
> real DB, no secret-holding daemon) listens on `127.0.0.1` during a Round 3 run — the spike proved
> a sandboxed server *can* reach such a port; (iii) keep secrets out via existing `scrub_env`.
> **Escalation trigger (→ Option C):** if Round 3 ever mixes services from *different* models/tenants
> in one fleet, or runs on a non-disposable host with co-located sensitive services, the shared
> loopback plane becomes a cross-tenant breach surface and per-netns (`unshare -rn` on Linux) or
> Docker-per-service is required. (Linux's `unshare -rn` path already exists in `_wrap_loopback_only`
> and would give per-service isolated loopback — but is unavailable on this macOS host.)

---

## 5. Caveat that changes the Round 3 plan/size

- **No new isolation substrate needed → Round 3 build does not grow by a Docker layer.** The fleet
  orchestrator is the new work: bind 9 servers on free ports (stubs-before-SUT ordering already
  proven in `_run_checkout_cell` / B4), inject each peer's `127.0.0.1:<port>` as deps' `*_ADDR`
  env (the existing `extra_env`-post-scrub path), and tear all 9 down on every exit path. This is an
  **N-server generalization of the existing single-SUT + 6-stub checkout cell**, not a netns/Docker
  rebuild.
- **Port-ordering / readiness race scales with N:** the TOCTOU window (`_free_port` → bind) is per
  server; with 9 the chance of a collision rises. Reuse the B4 ordering discipline and the existing
  readiness-poll degrade (FR-T2-2) so a slow/failed peer degrades the cell rather than misscoring.
- **macOS-only finding.** If Round 3 runs are moved to Linux CI, `_wrap_loopback_only` auto-selects
  `unshare -rn` (per-netns, isolated loopback) — which *removes* the FR-7a weakness but also means
  peer services can no longer reach each other over a shared `127.0.0.1` and would need an explicit
  shared-netns or veth-bridge design. **The substrate decision is platform-dependent; FR-7a is the
  macOS-Seatbelt answer.**

---

## 6. Honest measured-vs-inferred summary

| Claim | Source |
|---|---|
| Mechanism = Seatbelt, per-process, no netns | MEASURED (`sandbox_caps`, isolation_level) |
| Shared single loopback plane | INFERRED from profile, CONFIRMED by host_loopback_reach |
| N servers co-exist without serialization | MEASURED (3 concurrent, 0.87s) |
| Sandboxed A reaches sandboxed B over loopback | MEASURED (`peer_reach: true`) |
| External egress denied per-process under load | MEASURED (`DENIED:PermissionError` ×3) |
| A sandboxed server can reach ANY loopback port | MEASURED (`host_loopback_reach: true`) |
| Clean teardown, no orphans, with N concurrent | MEASURED (`pgrep` empty, ports unbound) |
