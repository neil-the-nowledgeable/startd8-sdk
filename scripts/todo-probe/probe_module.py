"""Canonical TODO-completion probe — exercises Categories A, B, and C.

Drop this file into a run's generated/ tree (or scan it directly) to validate
that the post-generation TODO scanner detects and routes all three categories:

  A = uncomment shortcut ($0, deterministic)   -> configure_retry_policy()
  B = instrumentation stub (LLM implement)      -> init_metrics()
  C = generic TODO (detected, NOT injected)     -> parse_config()
"""

import json


# --- Category A: commented-out code block adjacent to a TODO (uncomment) ---
def configure_retry_policy():
    # TODO: re-enable once the backoff helper is wired in
    # policy = RetryPolicy(max_attempts=5)
    # policy.set_backoff(ExponentialBackoff(base=0.2))
    # policy.register(default_registry)
    # return policy
    raise NotImplementedError


# --- Category B: instrumentation stub with vocab + empty body (implement) ---
def init_metrics():
    # TODO: implement OpenTelemetry metrics
    pass


# --- Category C: generic, non-instrumentation TODO in a real body (left alone) ---
def parse_config(raw):
    # TODO: support YAML in addition to JSON
    data = json.loads(raw)
    return data
