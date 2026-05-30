"""Transient import-alias bridge — lead-contractor removal (FR-6 migration window).

This module was renamed to ``primary_contractor_workflow`` in Phase 2. This shim re-exports
the canonical module under the old path so external consumers that still import
``startd8.workflows.builtin.lead_contractor_workflow`` keep resolving during the staged
consumer migration (the SDK is consumed source/editable, so there is no version-pin cushion).

TRANSIENT: removed in Phase 5 (FR-5) once all consumers are migrated to the primary path.
See docs/design/LEAD_CONTRACTOR_REMOVAL_FR6_CONSUMER_CHECKLIST.md.
"""
import sys as _sys

from . import primary_contractor_workflow as _canonical

# Alias the old module name to the canonical module object so every symbol
# (public and private) resolves through the old import path.
_sys.modules[__name__] = _canonical
