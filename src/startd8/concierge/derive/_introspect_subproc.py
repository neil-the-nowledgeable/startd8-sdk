"""Subprocess entrypoint for contained introspection (FR-DC-14).

Runs in a scrubbed-env subprocess spawned by ``containment.run_contained_introspection``. Reads a
JSON request from stdin (``{"modules": [...], "model_names": [...]|null}``), imports the target
modules, introspects their own-defined Pydantic models, and writes the ``IntrospectionResult`` as
JSON to stdout. Any failure is a non-zero exit (the parent maps that to a fail-closed
``DeriveImportError``) — this process never emits a partial result.

stdout is reserved for the JSON result; diagnostics go to stderr.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(f"bad request: {exc}", file=sys.stderr)
        return 2

    modules = request.get("modules") or []
    only = request.get("model_names")

    # Import here (not at module top) so an import failure is contained to this call.
    from startd8.concierge.derive.introspect import (
        DeriveImportError,
        introspect_models,
        resolve_models,
    )

    models = []
    try:
        for mod in modules:
            models.extend(resolve_models(mod, only=only))
    except DeriveImportError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 — fail-closed: any target-side error aborts
        print(f"introspection error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    result = introspect_models(models)
    sys.stdout.write(json.dumps(result.to_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
