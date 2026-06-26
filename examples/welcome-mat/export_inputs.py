"""Welcome Mat — export the generated input app's DB rows into the kickoff inputs/*.yaml.

Closes the Option-B loop: the deterministically-generated CRUD UI (`startd8 generate backend` over
`prisma/schema.prisma`) collects values into SQLite; this maps each column to a kickoff `value_path`
and writes it back through the M6 capture path (allow-listed, comment-preserving, round-trip-gated).

Usage:
    python examples/welcome-mat/export_inputs.py <project_root> <db_path>
e.g. python examples/welcome-mat/export_inputs.py examples/welcome-mat <workdir>/wm.db
"""

from __future__ import annotations

import sys

from startd8.kickoff_experience.db_export import FieldMapping, export_db_rows

# DB table.column  ->  kickoff value_path (must be in the M3 default_config allow-list).
MAPPING = [
    FieldMapping("conventioninput", "language", "conventions.yaml#/language"),
    FieldMapping("conventioninput", "framework", "conventions.yaml#/stack.framework"),
    FieldMapping("conventioninput", "money", "conventions.yaml#/data_model.money"),
    FieldMapping("conventioninput", "tzPolicy", "conventions.yaml#/data_model.datetime"),
    FieldMapping(
        "buildpreferenceinput", "perPipelineRun",
        "build-preferences.yaml#/budgets.per_pipeline_run",
    ),
    FieldMapping("buildpreferenceinput", "profile", "build-preferences.yaml#/generation.profile"),
]


def main(project_root: str, db_path: str) -> int:
    results = export_db_rows(project_root, db_path, MAPPING)
    failures = 0
    for r in results:
        mark = "ok   " if r.ok else f"{r.code}"
        print(f"  [{mark}] {r.value_path} = {r.value!r}" + (f"  ({r.error})" if r.error else ""))
        if not r.ok and r.code != "no_row":
            failures += 1
    print(f"exported {sum(1 for r in results if r.ok)}/{len(results)} fields")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
