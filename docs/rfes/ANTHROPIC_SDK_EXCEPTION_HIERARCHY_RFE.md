# RFE: Anthropic SDK Exception Hierarchy — Multiple Inheritance for Built-in Compatibility

**Date:** 2026-02-21
**SDK:** `anthropic` Python SDK
**Severity:** Low (workaround exists)
**Category:** Exception design

## Summary

`anthropic.APIConnectionError` and `anthropic.APITimeoutError` do not inherit from Python's built-in `ConnectionError` and `TimeoutError`. This causes generic retry infrastructure that catches built-in exception types to silently miss Anthropic-specific connection failures.

## Current Hierarchy

```
Exception
  └── APIError
        ├── APIConnectionError      ← does NOT extend ConnectionError
        │     └── APITimeoutError    ← does NOT extend TimeoutError
        ├── APIStatusError
        │     ├── BadRequestError
        │     ├── AuthenticationError
        │     ├── RateLimitError
        │     └── InternalServerError
        └── ...
```

## Proposed Hierarchy

```
Exception
  └── APIError
        ├── APIConnectionError(APIError, ConnectionError)
        │     └── APITimeoutError(APIConnectionError, TimeoutError)
        ├── APIStatusError
        │     └── ...
        └── ...
```

## Problem

Any retry logic that uses Python's built-in exception types will not catch Anthropic SDK connection errors:

```python
# Generic retry wrapper — standard pattern
RETRYABLE = (ConnectionError, TimeoutError, OSError)

async def with_retry(func, retryable=RETRYABLE):
    for attempt in range(max_attempts):
        try:
            return await func()
        except retryable:      # ← misses APIConnectionError
            await backoff()
    raise RetriesExhausted()
```

The exception passes through the retry logic unhandled and immediately fails the caller, even though the error is transient and retryable.

### Impact

- Transient connection errors cause immediate failure instead of retry
- Every SDK consumer that builds retry infrastructure outside the SDK must discover this gap independently and add provider-specific exception handling
- The SDK's own `max_retries` parameter works correctly (it knows its own types), masking the issue from users who rely solely on built-in retry — until they build custom retry logic

## Workaround

SDK consumers can augment their retry configuration per-provider:

```python
from anthropic import APIConnectionError

retry_config.retryable_exceptions += (APIConnectionError,)
```

## Rationale for Multiple Inheritance

Python's own stdlib uses this pattern throughout:

```
OSError
  └── ConnectionError          ← is both an OSError and a ConnectionError
        ├── ConnectionRefusedError
        ├── ConnectionResetError
        └── ConnectionAbortedError
```

Adding `ConnectionError` as a base class to `APIConnectionError`:

- **Zero breaking changes** — it only widens what catches the exception; existing `except APIError` handlers are unaffected
- **Follows stdlib convention** — Python's built-in exception hierarchy was designed for this
- **Eliminates a class of downstream bugs** — any retry/resilience library that catches `ConnectionError` automatically handles SDK connection failures
- **MRO is clean** — Python's C3 linearization handles diamond inheritance correctly; the exception is caught once by whichever `except` clause appears first

## Affected SDKs

The OpenAI Python SDK has the identical hierarchy and the same gap. A coordinated fix across both SDKs would benefit the broader ecosystem, as many projects use generic retry wrappers across multiple LLM providers.

## References

- Python built-in exception hierarchy: https://docs.python.org/3/library/exceptions.html#exception-hierarchy
- startd8 SDK workaround: `src/startd8/agents/claude.py` — augments `RetryConfig.retryable_exceptions` with `AnthropicAPIConnectionError` in `ClaudeAgent.__init__()`
