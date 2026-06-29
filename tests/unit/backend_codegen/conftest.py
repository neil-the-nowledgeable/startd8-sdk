"""Backend-codegen test isolation for the process-global SQLModel registry.

Generated apps define ``class X(SQLModel, table=True)`` in SQLModel's **process-global** declarative
registry (``SQLModel._sa_registry``) + ``SQLModel.metadata``. The app-importing runtime tests purge
``app.*`` from ``sys.modules`` and re-import, but that does **not** unregister the previously-defined
classes/tables. So when a later test reuses a model name (e.g. ``Capability``, ``Outcome``) the global
registry already holds it, and the re-import/configure fails with::

    Table 'capability' is already defined for this MetaData instance
    Multiple classes found for path "Capability" in the registry of this declarative base

That made every app-importing test pass in isolation but fail when the whole suite runs in one process
(test_runtime_smoke, test_import_runtime, test_scoped_pass, test_nav_runtime, …). The historical
workaround was "use a unique model name per test", which is fragile and easy to forget.

This autouse fixture removes exactly the **generated-app** classes (``__module__`` under ``app``) and
their tables from the global registry after each test, so the next test starts from a clean slate and
the full-suite run matches per-file runs. It is a no-op for the many tests that never import an app.
"""

from __future__ import annotations

import sys

import pytest


def _purge_generated_app_state() -> None:
    """Reset generated-app modules + SQLModel's process-global registry to the empty baseline.

    Removing the classes from ``_class_registry`` alone is **not** enough — SQLAlchemy keeps the
    configured *mappers* alive, so a stale ``Outcome`` mapper would still reference a now-deleted
    ``Capability`` ('failed to locate a name'). A full dispose (``clear_mappers`` + ``metadata.clear``)
    is the correct reset. This is safe here because the SDK owns **no** persistent SQLModel
    ``table=True`` models — the registry's baseline is empty, so the only mapped classes are ever the
    generated app's. (If the SDK ever defines a global SQLModel model, narrow this to app-only disposal.)
    """
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[name]

    try:
        from sqlalchemy.orm import clear_mappers
        from sqlmodel import SQLModel
    except Exception:  # sqlmodel isn't an SDK dep; nothing to isolate when it's absent
        return

    registry = getattr(SQLModel, "_sa_registry", None)
    class_registry = getattr(registry, "_class_registry", None)
    if class_registry is None:
        return

    # No-op unless a generated app actually registered classes this test (keeps non-app tests untouched).
    has_generated = any(
        isinstance(getattr(class_registry.get(k), "__module__", ""), str)
        and (class_registry.get(k).__module__ == "app" or class_registry.get(k).__module__.startswith("app."))
        for k in list(class_registry)
    )
    if not has_generated:
        return

    clear_mappers()
    SQLModel.metadata.clear()
    for cls_name in list(class_registry):
        if not cls_name.startswith("_"):
            del class_registry[cls_name]


@pytest.fixture(autouse=True, scope="module")
def _isolate_sqlmodel_registry():
    """Reset generated-app SQLModel state after each backend_codegen test *module* (registry isolation).

    **Module**-scoped, not function-scoped, on purpose. The collision is *cross-file*: different test
    files generate apps that reuse model names (``Capability``/``Outcome``/``Metric``) with different
    schemas. Within one file, re-importing the *same* schema only triggers a benign replace, and some
    files (e.g. test_import_runtime) import the app once and run many functions against it — a
    per-function ``clear_mappers`` would de-instrument those classes mid-file ('Can't locate an
    instrumentation manager'). Cleaning up once per file fixes the cross-file collision without
    disturbing intra-file reuse.
    """
    yield
    _purge_generated_app_state()
