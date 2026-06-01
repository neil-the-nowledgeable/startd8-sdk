"""Per-file TS validation must not fail on module-resolution errors (RUN-008).

A single file checked in isolation (temp dir, no node_modules / tsconfig paths)
cannot resolve `zod`/`next`/`@prisma/client` or `@/` imports — those TS2307-class
errors are false positives. Module resolution is the project-level gate's job
(FR-4), not the per-file syntax check that the pre-merge checkpoint runs.
"""

from __future__ import annotations

import shutil

import pytest

from startd8.languages.nodejs import (
    NodeLanguageProfile,
    _is_real_tsc_diagnostic,
    _strip_module_resolution_errors,
)

TSC_AVAILABLE = shutil.which("tsc") is not None


class TestStripModuleResolution:
    def test_strips_ts2307(self):
        out = "foo.ts(2,10): error TS2307: Cannot find module 'zod' or its corresponding type declarations."
        assert _strip_module_resolution_errors(out).strip() == ""
        assert _is_real_tsc_diagnostic(_strip_module_resolution_errors(out)) is False

    def test_keeps_real_syntax_error(self):
        out = (
            "foo.ts(2,10): error TS2307: Cannot find module 'zod'.\n"
            "foo.ts(5,1): error TS1005: ';' expected."
        )
        filtered = _strip_module_resolution_errors(out)
        assert "TS2307" not in filtered
        assert "TS1005" in filtered
        assert _is_real_tsc_diagnostic(filtered) is True

    def test_strips_member_resolution_codes(self):
        out = "f.ts(1,1): error TS2305: Module '\"x\"' has no exported member 'Y'."
        assert _is_real_tsc_diagnostic(_strip_module_resolution_errors(out)) is False


@pytest.mark.skipif(not TSC_AVAILABLE, reason="tsc not on PATH")
class TestEndToEndWithTsc:
    def test_zod_import_passes(self):
        code = "import { z } from 'zod';\nexport const S = z.object({ id: z.string() });\n"
        ok, msg = NodeLanguageProfile().validate_syntax(code, filename_hint="value-model.ts")
        assert ok is True, f"zod-importing file should pass per-file validation, got: {msg}"

    def test_real_syntax_error_still_fails(self):
        code = "export const x = ;\n"  # genuine syntax error
        ok, _ = NodeLanguageProfile().validate_syntax(code, filename_hint="bad.ts")
        assert ok is False
