# Shared Network-Namespace Substrate — the Linux fix for the macOS-Seatbelt dial-out gap (OQ-7)

**Date:** 2026-06-24
**Status:** **PROTOTYPE — implemented + unit-tested on macOS; live-validated ONLY via a Linux-gated
smoke (NOT run on this macOS dev host).**
**Module:** `src/startd8/benchmark_matrix/netns_substrate.py`
**Tests:** `tests/unit/test_netns_substrate.py` (macOS, 18) · `tests/integration/test_netns_substrate_smoke.py` (Linux-gated, skips here)
**Resolves:** OQ-7 — the substrate the verified gap in `CONTAINMENT_SPIKE.md` §0 named as **REQUIRED**
(not optional) for the dial-out cells and the Round 3 fleet.

---

## 1. The problem this fixes (from CONTAINMENT_SPIKE §0, VERIFIED)

OB services dial each other over **gRPC**. Under the macOS Seatbelt `_wrap_loopback_only` profile,
gRPC outbound to `127.0.0.1` is **DENIED** — and the only way to make it connect is to re-open
`remote ip "*"`, which **re-opens full external egress**. Seatbelt's `(remote ip …)` filter accepts
only `*` or `localhost` (an IP-literal rule is a hard parse error), and gRPC is denied under
`localhost`. **There is no Seatbelt profile that permits sandboxed gRPC loopback dial-out while
denying egress — it is strictly either/or.**

Consequence: leaf (inbound) services score fine sandboxed on macOS, but **dial-out** services —
checkout (6 stubs), recommendation (1 stub), and the **entire Round 3 inter-service fleet** — cannot
be both wired-over-loopback AND contained on macOS. Today their suites pass only via the
**non-sandboxed** path, so the gap is latent.

## 2. Why a fresh Linux netns fixes it — by construction (not by filter)

A fresh Linux network namespace has:
- **its OWN isolated loopback** (`127.0.0.1`), separate from the host and from every other netns →
  processes that **share** one netns reach each other over that loopback, so **gRPC dial-out WORKS**;
- **no veth / no route out** → **external egress is IMPOSSIBLE**. Containment is *structural* — there
  is no egress filter to mis-scope, so the macOS either/or simply does not arise.

So a fresh shared netns gives **gRPC-loopback + egress-deny + hermeticity SIMULTANEOUSLY** — exactly
the combination Seatbelt cannot.

## 3. The critical architecture (shared, not per-process)

This is the easy-to-get-wrong part:

- The **existing** `sandbox.py` netns branch wraps EACH command in its own `unshare -rn`. Two peers
  launched as **separate** `unshare -rn` commands get **two isolated loopbacks** → they CANNOT reach
  each other, and the host harness cannot reach a service inside an isolated netns over `127.0.0.1`.
  **That per-process model is WRONG for dial-out.**
- Therefore the **whole behavioral cell** — dependency stubs + the SUT + the gRPC scoring **client** —
  must run inside **ONE SHARED netns**. They share that netns's loopback (dial-out works); egress is
  impossible (no route out).
- **`lo` in a fresh netns is DOWN.** We MUST `ip link set lo up` **inside** the netns **before**
  anything binds/connects, or every loopback bind/connect fails. (The existing `_wrap_loopback_only`
  netns branch notes this but does NOT do it — a real defect for that path.)
- **Rootless:** `unshare -rn` == `--user --map-root-user --net` — maps the caller to root in a new
  user+net namespace, so **no real root** is needed. We run **ONE** such namespace and host the
  cell's processes as its children.

## 4. The substrate API

```python
run_cell_in_shared_netns(cell_runner_cmd, *, timeout, cwd=None, extra_env=None) -> NetnsCellResult
```

A primitive that:
1. Checks `netns_available()` (Linux + functional rootless `unshare -rn`). If not → returns
   `available=False` with a clear `violation` — a **no-op-skip** (the macOS reality), never a score.
2. Wraps `cell_runner_cmd` in a **single** `unshare -rn sh -c 'ip link set lo up && exec <runner>'`
   (`build_netns_command`). The whole cell shares the one netns; `lo` is brought up first; `exec`
   replaces the shell so killpg reaps the real runner.
3. Launches it as its own session/process-group leader (`start_new_session=True`), captures stdout,
   and **parses the marked JSON payload** the runner prints.
4. **Guarantees teardown** of the whole process group (`_terminate_group`: SIGTERM→grace→SIGKILL on
   the group → stubs/SUT/client reaped, no orphans) on EVERY path (success, timeout, launch error).

`NetnsCellResult`: `available`, `ready`, `payload` (`{"coverage", "results", …}`), `returncode`,
`stdout`/`stderr`, `duration_s`, `isolation_level`, `violation`, `network_isolated`.

### The cell-runner contract (`CellRunnerSpec`)

`run_cell_in_shared_netns` owns only the **substrate**; the in-netns "cell runner" owns the cell. The
contract (a runner exec'd under the substrate MUST, once inside the shared netns):
1. start every declared stub on a **free loopback port** (`bind 127.0.0.1:0`);
2. inject each stub's address as its `*_SERVICE_ADDR` env var (the SUT dials it over the shared
   `127.0.0.1`);
3. launch the SUT (`resolve_serve_command`) with `$PORT` on a free loopback port; wait for readiness;
4. run the scoring suite **client** against the live SUT over `127.0.0.1`;
5. `print(emit_cell_payload({"coverage": …, "results": […]}))` and exit.

`CellRunnerSpec` (suite, `serve_argv`, `serve_env`, `stub_env_names`, `tier`, `readiness_timeout_s`)
is the serializable boundary the host hands the runner (JSON arg or temp file). This is a **contract
+ thin helpers**, NOT a rewrite of `execute.py` — any script honoring it integrates.

### How the SuiteResult JSON crosses the boundary

The runner runs in a separate `unshare` process, so the result returns **out-of-band via stdout**.
The runner prints `<CELL_RESULT_BEGIN>{json}<CELL_RESULT_END>`; the host `parse_cell_payload` does
`rfind(BEGIN)` → `find(END)` and `json.loads` only the marked span. This means **incidental stdout
(server logs) cannot corrupt the result channel**, and a re-emit (the LAST marked span) supersedes
earlier output. `emit_cell_payload` is shared by producer and consumer so there is one definition of
the protocol. The existing suite `SuiteResult.to_dict()` already produces exactly the
`{"coverage", "results", …}` shape the runner emits.

## 5. How it detects unavailability + degrades (the macOS skip path)

`netns_available()`:
- non-Linux → `False` immediately (macOS/Darwin: `unshare` is absent);
- `unshare` not on PATH → `False`;
- otherwise **functionally probe** `unshare -rn true` (a hardened kernel can forbid unprivileged user
  namespaces even with the binary present) → `False` if it fails.

When unavailable, `run_cell_in_shared_netns` returns `available=False` + a precise `violation`
("netns unavailable on this platform (Darwin/macOS — `unshare` absent)" / "...kernel may forbid user
namespaces"), launches **no** subprocess, and the caller **degrades the cell** (FR-T2-2 analog) — it
is **never** scored as model quality. This makes the substrate a clean no-op on the macOS dev host
and live on Linux/CI.

## 6. The Linux-gated live smoke (the proof)

`tests/integration/test_netns_substrate_smoke.py` — the netns analog of the macOS Seatbelt repro. On
Linux with functional rootless `unshare` ONLY (else `pytest.skip` with a precise reason), it runs a
self-contained stdlib cell runner inside **one shared netns** and asserts BOTH:
- **(a) loopback peers reach each other** over the shared `127.0.0.1` (the gRPC-dial-out analog — the
  thing Seatbelt DENIED), AND
- **(b) external egress to `1.1.1.1:443` is UNREACHABLE** (timeout/refused — containment by
  construction).

Both true ⇒ **verdict: netns gives gRPC-loopback + egress-deny simultaneously.** It uses raw stdlib
sockets deliberately: under the broken Seatbelt profile raw loopback SUCCEEDED while gRPC failed, so a
netns that passes the raw test on a real shared loopback stack is the substrate on which gRPC (which
needs exactly that working loopback) also connects; a heavier gRPC variant layers on the same
substrate without changing the verdict.

**On this macOS dev host the smoke SKIPPED** with: *"shared-netns smoke requires Linux + functional
rootless `unshare -rn`; host is Darwin/macOS (`unshare` absent)."* The live assertion (a)+(b) has NOT
been executed here — it requires a Linux box/CI.

## 7. Integration path

### Dial-out cells (checkout / recommendation)
Today `execute.py` runs the stubs **in the host process** and the SUT under `run_service_sandboxed`
(its own netns on Linux) — which is the broken per-process split. To adopt the substrate:
- move the stub binding + `*_SERVICE_ADDR` injection + SUT launch + suite client **into the cell
  runner**, so all of them share the **one** netns (reuse `checkout_stubs.CheckoutStubHarness` /
  `recommendation_stubs.RecommendationDepHarness` and the `*_suite` clients — they already bind
  `127.0.0.1:0` and dial `127.0.0.1`, which is exactly netns-correct);
- the host calls `run_cell_in_shared_netns([...runner..., spec_json])`, parses `payload`, and folds
  `coverage` through the existing `compute_composite` path. Stub call-counts (the dial-proof) ride in
  `payload["results"]`/an extra field. On macOS the call degrades (skip), preserving today's
  non-sandboxed macOS behavior; on Linux it runs **contained**.

### Round 3 fleet (all 9 + journey driver)
The N-server generalization: the cell runner binds all 9 services on free loopback ports
(stubs-before-SUT / B4 ordering), injects each peer's `127.0.0.1:<port>` as the consumers'
`*_SERVICE_ADDR`, launches the journey driver, and emits the aggregate payload — **all inside one
shared netns**, so inter-service gRPC works and egress is impossible by construction. This **removes
the FR-7a macOS weakening** (no shared *host* loopback plane; the netns loopback is private to the
fleet) for Linux runs, while the macOS path stays the FR-7a non-sandboxed posture.

## 8. Honest status — proven vs. needs-Linux-CI

| Claim | Status |
|---|---|
| Command construction (`unshare -rn` + `ip link set lo up` + exec runner, quoting) | **PROVEN on macOS** (unit) |
| JSON result protocol (emit/parse, log-noise tolerance, last-span, malformed→None) | **PROVEN on macOS** (unit) |
| Process-group teardown / lifecycle / timeout / launch-error degrade | **PROVEN on macOS** (mocked unit) |
| Degrade-on-unavailable = no-op-skip (no subprocess, clear violation) | **PROVEN on macOS** (unit) |
| **gRPC-loopback WORKS inside the shared netns** | **NOT run here** — Linux-gated smoke (SKIPPED on macOS) |
| **External egress DENIED inside the netns** | **NOT run here** — Linux-gated smoke (SKIPPED on macOS) |

## 9. Limitations / risks

- **Rootless `unshare` may be restricted.** Hardened kernels set
  `kernel.unprivileged_userns_clone=0` (or seccomp/AppArmor blocks user namespaces). The functional
  `unshare -rn true` probe catches this → honest degrade, but it means **CI must allow user
  namespaces** for the live smoke + contained runs to execute (GitHub-hosted Ubuntu runners do;
  some hardened/locked-down hosts do not).
- **`ip` must be present in the netns** (`/sbin/ip` / iproute2). Absent → `lo` stays down and the cell
  degrades at readiness rather than misscoring. Document the runner image's deps.
- **Prototype scope.** A working substrate primitive + the cell-runner contract are delivered; wiring
  the existing dial-out cells (§7) into it is the follow-up integration, not done here.
- **Not multi-tenant kernel isolation.** A shared netns contains the fleet from the host network and
  external egress, but services within the netns still share one (private) loopback — fine for
  same-model OB fleets on a disposable host (FR-7a posture). Cross-tenant/Docker-per-service or
  gVisor/Firecracker remains the escalation path (unchanged from the spike's Option C trigger).
```
