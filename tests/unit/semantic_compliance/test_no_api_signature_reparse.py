"""WI-6 / FR-CL-3c anti-regression guard.

After E1/E2/E3, the Semantic Compliance Reviewer reads the structured forward
manifest (contracts + element specs) instead of re-parsing raw ``api_signatures``.
The single sanctioned residual is ``signature_check._NAME_RE`` (the variable arm +
no-manifest fallback, kept because variable api_signatures carry no contract — OQ-5).

This guard pins that: ``signature_check`` is the ONLY module in the
``semantic_compliance`` package that imports ``re``. If a future change re-introduces
a second api_signatures parser anywhere in the SCR, it will import ``re`` in a new
module and trip this test — forcing the author to route through the manifest instead.

Scope note: FR-CL-3c is scoped to the SCR (the consolidation's domain). Legitimate
upstream parsers of api_signatures remain (the canonical
``forward_manifest_extractor._extract_api_signatures``, and pipeline consumers
``plan_ingestion_micro_ingest._parse_api_signature`` / ``micro_prime`` element gen) —
those feed the manifest the SCR now reads; they are not the asymmetry E1/E2 closed.
"""

from __future__ import annotations

import re
from pathlib import Path

import startd8.semantic_compliance as scr_pkg

_IMPORT_RE = re.compile(r"^\s*(?:import re(?:\s|,|$)|from re import )", re.MULTILINE)

# The lone allowlisted regex module in the SCR (FR-CL-3 narrowed E1 residual).
_ALLOWLISTED = {"signature_check.py"}


def _scr_modules() -> list[Path]:
    pkg_dir = Path(scr_pkg.__file__).parent
    return sorted(p for p in pkg_dir.glob("*.py") if p.name != "__init__.py")


def test_signature_check_is_the_only_re_importer_in_scr() -> None:
    importers = {
        p.name
        for p in _scr_modules()
        if _IMPORT_RE.search(p.read_text(encoding="utf-8"))
    }
    assert importers == _ALLOWLISTED, (
        "FR-CL-3c: a new module in semantic_compliance imports `re`. The SCR must not "
        "re-parse api_signatures — read the structured forward manifest instead. If a new "
        f"regex parser is genuinely required, justify it and update the allowlist. Found: {importers}"
    )


def test_allowlisted_parser_module_exists() -> None:
    """Guard integrity: the allowlisted module must actually be present."""
    names = {p.name for p in _scr_modules()}
    assert _ALLOWLISTED <= names
