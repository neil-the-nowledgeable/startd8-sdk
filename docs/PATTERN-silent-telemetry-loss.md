# Pattern: Silent Telemetry Loss via Environment Variable Evaporation

## Classification

| Field | Value |
|-------|-------|
| Pattern type | Reliability anti-pattern + defense-in-depth fix |
| Root cause class | Ephemeral configuration for durable infrastructure |
| Affected component | `src/startd8/otel.py` — `get_otel_runtime_state()` |
| Fix commits | `25e68c9`, `fc9cd1a`, `ff05ef5` |
| SDK version | 0.4.0 |
| Date | 2026-02-15 |

## Problem Statement

OTel telemetry repeatedly went silent across shell sessions. The Kind cluster with Alloy on `localhost:4317` was healthy, the SDK's OTel instrumentation was wired end-to-end, and historical metrics in Mimir proved the pipeline worked when active. But after opening a new terminal (or rebooting), telemetry silently stopped — logs showed `trace_id: ""` confirming OTel was never configured.

### Root Cause

```
otel.py:523-532 (before fix)
```

In `auto` mode (the default), `get_otel_runtime_state()` checked for an explicit `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable. If absent, it returned early — **no probe, no configuration, no warning**. The env var, set in a previous shell session via `export`, evaporated when that session ended.

```python
# BEFORE: auto + no env var = immediate silent skip
if mode == "auto":
    if not endpoint_env:
        state.update(reason="auto_endpoint_unset", ...)
        return state  # <-- silent loss
```

### Why It Recurred

1. **Single point of failure**: One ephemeral env var was the sole input for telemetry activation
2. **Silent failure**: No log, no banner, no CLI diagnostic — operator had no feedback
3. **No persistence**: No way to set "always connect to localhost:4317" durably
4. **No discovery**: The SDK never attempted to detect a running collector, even though `_otlp_endpoint_reachable()` already existed in the same file

## Fix: 5-Layer Defense-in-Depth

Each layer independently prevents the failure. If any single layer works, telemetry activates.

### Layer 1: Auto-probe localhost:4317 (Core)

`get_otel_runtime_state()` now implements a 3-tier resolution cascade in `auto` mode:

```
1. OTEL_EXPORTER_OTLP_ENDPOINT env var     (existing, unchanged)
2. ~/.startd8/config.json → otel.endpoint  (Layer 2)
3. Auto-probe http://localhost:4317         (NEW — core fix)
```

If the collector is running locally, telemetry activates without any env var. Cost: up to 1s socket probe on startup when no collector is present (same pattern already used when env var IS set). CI environments have no collector, so the probe returns False and behavior is unchanged.

### Layer 2: Persistent config file

Added `otel.endpoint` and `otel.mode` to `~/.startd8/config.json` via `ConfigManager.get_otel_setting()` / `set_otel_setting()`. Survives shell restarts, reboots, and session changes.

### Layer 3: Startup telemetry banner

`auto_configure_otel()` now logs a one-line banner at INFO:

```
Telemetry: ACTIVE -> http://localhost:4317 (auto-discovered)
Telemetry: INACTIVE -- no collector found
```

The artisan workflow also emits this banner before starting its root span, so every artisan run explicitly shows telemetry status.

### Layer 4: CLI diagnostics

```bash
startd8 otel-status      # Rich panel: mode, endpoints, reachability, suggestions
startd8 otel-configure    # Persist: --endpoint, --mode, --clear
```

`otel-status` shows actionable suggestions when telemetry is inactive (e.g., "Start a collector on localhost:4317" or "Run: startd8 otel-configure --endpoint ...").

### Layer 5: `.env.example` documentation

Documents all OTel env vars with the new auto-discovery behavior explained in comments.

## Programmatic Prevention Strategies

These patterns prevent this class of failure in any system, not just this SDK.

### 1. Never gate durable infrastructure on ephemeral configuration alone

**Anti-pattern**: Requiring an env var (set via `export` in a shell) to activate a connection to a long-running service.

**Pattern**: Use a resolution cascade with at least 3 tiers:
```
env var (explicit override) → config file (persistent) → auto-discovery (convention)
```

**Implementation checklist**:
- [ ] Env var for explicit override (CI, containers, custom endpoints)
- [ ] Config file for persistent user preference (survives shell restart)
- [ ] Convention-based auto-discovery for common defaults (localhost, well-known ports)
- [ ] Each tier is independently sufficient

### 2. Fail visible, not silent

**Anti-pattern**: Returning early from configuration with no feedback when a subsystem is inactive.

**Pattern**: Always emit a status line when a subsystem is initialized or skipped.

```python
# BEFORE (silent)
if not endpoint:
    return  # operator has no idea telemetry is off

# AFTER (visible)
banner = format_status_banner(state)
logger.info(banner)  # always emitted, active or inactive
```

**Implementation checklist**:
- [ ] Log a one-liner at startup showing subsystem status (ACTIVE/INACTIVE + reason)
- [ ] Include the resolved configuration source (env var, config file, auto-discovered)
- [ ] Provide a CLI diagnostic command (`<tool> <subsystem>-status`)
- [ ] Show actionable suggestions when inactive

### 3. Provide a "sticky" configuration mechanism

**Anti-pattern**: Requiring operators to add env vars to shell profiles, which are per-shell, per-user, and brittle.

**Pattern**: Offer a CLI command that persists configuration to a file that the tool reads on every invocation.

```bash
# One-time setup, survives forever
mytool otel-configure --endpoint http://localhost:4317

# vs. the fragile alternative
echo 'export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317' >> ~/.zshrc
source ~/.zshrc  # easy to forget, doesn't affect other terminals
```

**Implementation checklist**:
- [ ] `<tool> <subsystem>-configure` persists settings to a well-known config file
- [ ] `<tool> <subsystem>-status` shows current effective configuration and its source
- [ ] `<tool> <subsystem>-configure --clear` resets to defaults
- [ ] Env vars always override config file (escape hatch for CI/containers)

### 4. Auto-discover well-known local services

**Anti-pattern**: Requiring explicit configuration for services running on standard ports on localhost.

**Pattern**: Probe `localhost:<well-known-port>` with a short timeout before giving up.

```python
def _auto_discover_service(default_endpoint, timeout=1.0):
    """Probe a local service before requiring explicit configuration."""
    if _is_reachable(default_endpoint, timeout):
        return default_endpoint
    return None
```

**Well-known ports to probe**:
| Service | Port | Protocol |
|---------|------|----------|
| OTel Collector (gRPC) | 4317 | gRPC |
| OTel Collector (HTTP) | 4318 | HTTP |
| Prometheus | 9090 | HTTP |
| Grafana | 3000 | HTTP |
| Loki | 3100 | HTTP |

**Risks & mitigations**:
- **Startup latency**: Socket probe adds up to `timeout` seconds. Use 1s max; the probe is a TCP SYN only.
- **False positives**: Another service on the same port. Mitigate with a health-check endpoint if the protocol supports it.
- **Security**: Don't auto-send data to unknown endpoints in production. Gate auto-discovery on `auto` mode only; `enabled` mode requires explicit configuration.

### 5. Test the "nothing configured" path

**Anti-pattern**: Only testing the happy path (env var set, collector available).

**Pattern**: Test all tiers of the cascade, especially the "everything is unset" case.

```python
class TestResolutionCascade:
    def test_env_var_takes_priority(self): ...
    def test_config_file_used_when_env_unset(self): ...
    def test_auto_probe_used_when_config_unset(self): ...
    def test_no_collector_skips_gracefully(self): ...
    def test_banner_shows_inactive_reason(self): ...
```

## Verification Commands

```bash
# 1. Cluster up, no env var → should auto-discover
python3 -c "from startd8.otel import get_otel_runtime_state; print(get_otel_runtime_state())"
# Expected: will_configure: True, reason: auto_discovered_default

# 2. Cluster down, no env var → should skip gracefully
python3 -c "from startd8.otel import get_otel_runtime_state; print(get_otel_runtime_state())"
# Expected: will_configure: False, reason: auto_no_collector_found

# 3. CLI diagnostic
startd8 otel-status

# 4. Persist config
startd8 otel-configure --endpoint http://localhost:4317
startd8 otel-status  # should show "config file" as source

# 5. Run tests
pytest tests/unit/test_otel_auto_init.py -v  # 45 tests
```

## Related

- `docs/LOKI_SETUP_GUIDE.md` — Observability stack setup
- `src/startd8/otel.py` — OTel configuration module
- `src/startd8/config.py` — Persistent configuration
- MEMORY.md entry: "OTel Log Bridge Init Gap" (related silent-loss pattern)
