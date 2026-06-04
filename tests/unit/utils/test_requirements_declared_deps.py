"""RUN-036 #4: requirements.in must declare deps of files generated AFTER the scan.

`external_packages_from_imports` harvests third-party PyPI names from a SPEC's *declared*
imports (ordering-independent), so e.g. sqlmodel/sqlalchemy land in requirements.in even
when their importing file is produced later in the run — the RUN-036 import-resolution gap.
"""

from startd8.utils.requirements_generator import (
    external_packages_from_imports,
    generate_requirements_in,
)


class TestExternalPackagesFromImports:
    def test_harvests_third_party_filters_local_stdlib_relative(self):
        mods = [
            "sqlmodel", "sqlalchemy.orm", "fastapi",  # third-party → kept
            "app.tables", "app.models",               # local → dropped
            "os", "typing",                           # stdlib → dropped
            ".relative",                              # relative → dropped
            "",                                       # empty → dropped
        ]
        got = external_packages_from_imports(mods, local_prefixes={"app"})
        assert got == {"sqlmodel", "sqlalchemy", "fastapi"}

    def test_empty_inputs(self):
        assert external_packages_from_imports([]) == set()
        assert external_packages_from_imports(["app.x"], local_prefixes={"app"}) == set()

    def test_no_local_prefixes_keeps_nonstdlib(self):
        # Without local_prefixes, only stdlib/relative are filtered.
        assert external_packages_from_imports(["requests", "os"]) == {"requests"}


class TestGenerateRequirementsInBaseline:
    def test_scanner_emits_orm_deps(self):
        # Regression lock: the scanner DOES emit sqlmodel/sqlalchemy from file content
        # (proves the #4 gap was scan-coverage/ordering, not the generator).
        src = (
            "from __future__ import annotations\n"
            "from sqlmodel import Session, select\n"
            "import sqlalchemy\n"
            "from fastapi import APIRouter\n"
            "from app.tables import JobDescription\n"
        )
        out = generate_requirements_in({"app/jobs.py": src})
        pkgs = set(out.split())
        assert {"sqlmodel", "sqlalchemy", "fastapi"} <= pkgs
        assert "app" not in pkgs  # local import filtered
