"""Transient import-alias bridge — lead-contractor removal (FR-6 migration window).

Renamed to ``primary_contractor_models`` in Phase 2. This shim re-exports the canonical
module under the old path so external consumers that still import
``startd8.workflows.builtin.lead_contractor_models`` keep resolving during the staged
consumer migration.

TRANSIENT: removed in Phase 5 (FR-5). See docs/design/LEAD_CONTRACTOR_REMOVAL_FR6_CONSUMER_CHECKLIST.md.
"""
import sys as _sys

from . import primary_contractor_models as _canonical

_sys.modules[__name__] = _canonical
