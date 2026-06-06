#!/usr/bin/env python3
"""SPIKE: deterministic manifest extraction from REAL strtd8 kickoff prose (FR-WPI-1/2/4).

Throwaway-quality by design. Measures: how far does stdlib parsing of the authoring-contract
formats get against docs/kickoff/REQUIREMENTS_v0.5-draft.md, and what does the round-trip
through the SDK's own parsers say. Emits a mini extraction report (the FR-WPI-3 shape) and
extracted manifests to ./manifests/.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/Users/neilyashinsky/Documents/dev/startd8-sdk/src")

DOC = Path(
    "/Users/neilyashinsky/Documents/dev/strtd8/strtd8/docs/kickoff/REQUIREMENTS_v0.5-draft.md"
).read_text(encoding="utf-8")
OUT = Path("/tmp/wireframe_spike/manifests")
OUT.mkdir(parents=True, exist_ok=True)

RECORDS = []  # the FR-WPI-3 mini report


def rec(manifest, field, status, value=None, source=None, reason=None):
    RECORDS.append(
        {k: v for k, v in dict(
            manifest=manifest, field=field, status=status, value=value,
            source=source, reason=reason,
        ).items() if v is not None}
    )


# ---------------------------------------------------------------- P0 primitives

def sections(text):
    """heading -> body (## and ### levels, flat)."""
    out = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            cur = m.group(2).strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def find_section(secs, prefix):
    for k in secs:
        if k.lower().startswith(prefix.lower()):
            return k, secs[k]
    return None, None


def all_md_tables(body):
    """ALL markdown tables in body -> list of (headers, rows). Tables are maximal runs of
    consecutive |-prefixed lines (the spike-1 bug: flattening runs merged adjacent tables)."""
    def cells(l):
        return [c.strip() for c in l.strip().strip("|").split("|")]
    tables, run = [], []
    for line in body.splitlines() + [""]:
        if line.strip().startswith("|"):
            run.append(line)
        elif run:
            if len(run) >= 2:
                headers = [h.lower() for h in cells(run[0])]
                rows = [cells(l) for l in run[2:] if not re.match(r"^\|[\s\-|]+\|?$", l.strip())]
                tables.append((headers, [r for r in rows if any(r)]))
            run = []
    return tables


def parse_md_table(body):
    """First markdown table in body."""
    tables = all_md_tables(body)
    return tables[0] if tables else ([], [])


def strip_annotations(cell):
    """Drop italic asides: 'jobs.md *(not written yet)*' -> 'jobs.md'."""
    return re.sub(r"\*\([^)]*\)\*", "", cell).strip()


def kebab(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


SECS = sections(DOC)

# ---------------------------------------------------------------- pages.yaml (§2.2)

def extract_pages():
    _, body = find_section(SECS, "Pages")
    if body is None:
        rec("pages.yaml", "*", "not_extracted", reason="no Pages section")
        return None
    tables = all_md_tables(body)
    if not tables:
        rec("pages.yaml", "*", "not_extracted", reason="Pages section has no table")
        return None
    headers, rows = tables[0]
    pages = []
    for row in rows:
        page = dict(zip(headers, row))
        name = page.get("page", "")
        content = strip_annotations(page.get("content file", ""))
        slug = "/" if name.lower() == "home" else "/" + kebab(name)
        pages.append({"slug": slug, "title": name, "content": f"pages/{content}"})
        rec("pages.yaml", f"page:{slug}", "extracted",
            value=f"{name} -> {content}", source="## Pages table row")
    # Nav table (Label | Target) — the second table in the section, when present.
    nav = []
    if len(tables) >= 2:
        nav_headers, nav_rows = tables[1]
        for row in nav_rows:
            item = dict(zip(nav_headers, row))
            if item.get("label") and item.get("target"):
                nav.append({"label": item["label"], "href": item["target"]})
        rec("pages.yaml", "nav", "extracted",
            value=f"{len(nav)} nav items", source="Navigation table")
    out = {"pages": pages}
    if nav:
        out["nav"] = nav
    return out


# ---------------------------------------------------------------- app.yaml (§2.7, subset rule)

APP_KEYMAP = {
    "package name": ("app", "package"),
    "display name": ("app", "name"),
    "python version": ("app", "python_version"),
    "database": ("persistence", "path"),
    "logging": ("logging", "file"),
    "migrations": ("migrations", "enabled"),
    "container": ("container", "dockerfile"),
}
NO_HOME = {"port", "sqlite mode", "env keys"}  # sweep-2: no AppManifest field


def extract_app():
    _, body = find_section(SECS, "Scaffold & runtime")
    if body is None:
        rec("app.yaml", "*", "defaulted", reason="no Scaffold & runtime section")
        return None
    headers, rows = parse_md_table(body)
    out = {}
    for row in rows:
        setting = dict(zip(headers, row))
        key = setting.get("setting", "").lower()
        val = setting.get("value", "")
        if key in NO_HOME:
            rec("app.yaml", key, "not_extracted",
                reason="generator-gap: no AppManifest field (scaffold-codegen backlog)")
            continue
        if key not in APP_KEYMAP:
            rec("app.yaml", key, "not_extracted", reason="unknown setting vocabulary")
            continue
        sec, field = APP_KEYMAP[key]
        if key == "database":
            m = re.search(r"sqlite:///(\S+)", val)
            val2 = m.group(1) if m else val
        elif key == "migrations":
            val2 = "alembic" in val.lower() or val.lower().startswith("yes")
        elif key == "container":
            val2 = val.lower().startswith("yes")
        elif key == "logging":
            m = re.match(r"([^,]+)", val)
            val2 = m.group(1).strip()
        else:
            val2 = val
        out.setdefault(sec, {})[field] = val2
        rec("app.yaml", f"{sec}.{field}", "extracted", value=str(val2),
            source=f"Scaffold & runtime row '{key}'")
    return out


# ---------------------------------------------------------------- views.yaml (§2.3, real prose)

def extract_views(known_entities, nav_routes):
    blocks = {k: v for k, v in SECS.items() if k.lower().startswith("view:")}
    if not blocks:
        rec("views.yaml", "*", "not_extracted", reason="no View blocks")
        return None
    views = []
    ent_by_lower = {e.lower(): e for e in known_entities}

    def resolve_entity(phrase):
        """'tailored matches' -> TailoredMatch (squash spaces, depluralize)."""
        squashed = re.sub(r"[^a-z]", "", phrase.lower())
        for cand in (squashed, squashed.rstrip("s"), squashed[:-2] + ("" if not squashed.endswith("es") else "")):
            if cand in ent_by_lower:
                return ent_by_lower[cand]
        return None

    for heading, body in blocks.items():
        name = heading.split(":", 1)[1].strip()
        name = re.sub(r"\*\(.*?\)\*", "", name).strip()  # strip '*(P2 preview)*'
        fields = dict(
            re.findall(r"^- (\w[\w ]*?):\s*(.+)$", body, re.MULTILINE)
        )
        kind = fields.get("Kind", "").strip()
        root = fields.get("Root", "").strip()
        view = {"name": kebab(name).replace("-", "_")}
        if not kind or (not root and kind != "export-package"):
            rec("views.yaml", f"view:{name}", "not_extracted",
                reason=f"missing Kind/Root (got kind={kind!r} root={root!r})")
            continue
        view["kind"] = kind
        # export-package: 'Of: Job Workspace' — root = the referenced view's root
        if kind == "export-package" and not root:
            of = fields.get("Of", "")
            ref = kebab(of).replace("-", "_")
            src = next((v for v in views if v["name"] == ref), None)
            if src:
                root = src["root"]
                rec("views.yaml", f"{view['name']}.root", "extracted",
                    value=root, source=f"Of: {of} (resolved via referenced view)")
            else:
                rec("views.yaml", f"view:{name}", "not_extracted",
                    reason=f"Of-reference {of!r} not resolvable")
                continue
        view["root"] = root
        # Route: nav table wins; else kind-aware derivation.
        nav_hit = nav_routes.get(name.lower())
        view["route"] = nav_hit or f"/views/{kebab(name)}"
        rec("views.yaml", f"{view['name']}.route",
            "extracted" if nav_hit else "defaulted",
            value=view["route"],
            source="Navigation table" if nav_hit else "kind-aware derivation (kebab)")
        # 'Shows: counts of X and Y per <root>' -> aggregates (dashboard only, spike scope)
        shows = fields.get("Shows", "")
        if kind == "dashboard" and "count" in shows.lower():
            aggs = []
            for phrase in re.findall(r"(?:counts of |and )([\w ]+?)(?= and | per |$)", shows):
                ent = resolve_entity(phrase.strip())
                if ent:
                    fk = None  # FK resolution needs the schema — spike: look for <root squashed>Id
                    fk = root[0].lower() + root[1:] + "Id"
                    aggs.append({"name": f"{kebab(phrase.strip()).replace('-', '_')}_count",
                                 "of": ent, "fk": fk})
                    rec("views.yaml", f"{view['name']}.aggregate:{ent}", "extracted",
                        value=f"fk={fk} (schema-resolved)", source=f"Shows: '{phrase.strip()}'")
                else:
                    rec("views.yaml", f"{view['name']}.aggregate", "not_extracted",
                        reason=f"entity phrase {phrase.strip()!r} not resolvable")
            if aggs:
                view["aggregates"] = aggs
        elif shows:
            rec("views.yaml", f"{view['name']}.shows", "not_extracted",
                reason=f"'{shows[:60]}…' — relation/panel resolution beyond spike scope ({kind})")
        for extra in ("Also shows", "Empty state", "Gap callout", "Formats"):
            if extra in fields:
                rec("views.yaml", f"{view['name']}.{extra.lower().replace(' ', '_')}",
                    "not_extracted", reason=f"'{extra}:' line — no grammar rule yet")
        views.append(view)
    return {"views": views}


# ---------------------------------------------------------------- completeness.yaml (§2.4)

def extract_completeness(known_entities):
    _, body = find_section(SECS, "Completeness")
    if body is None:
        rec("completeness.yaml", "*", "defaulted", reason="no Completeness section")
        return None
    entities = {}
    for m in re.finditer(r"at least (\d+) (\w+?)s?\b(?:\s*\(weight (\d+)\))?", body):
        n, ent_raw, weight = m.groups()
        ent = next((e for e in known_entities if e.lower() == ent_raw.lower()
                    or e.lower() == ent_raw.lower().rstrip("s")), None)
        # handle 'ProofPoints' style plural of CamelCase
        if ent is None:
            ent = next((e for e in known_entities
                        if re.sub(r"[^a-z]", "", e.lower()) == re.sub(r"[^a-z]", "", ent_raw.lower()).rstrip("s")), None)
        if ent is None:
            rec("completeness.yaml", f"signal:{ent_raw}", "not_extracted",
                reason=f"entity {ent_raw!r} not in contract")
            continue
        spec = {"min_rows": int(n)}
        if weight:
            spec["weight"] = int(weight)
        entities[ent] = spec
        rec("completeness.yaml", f"entities.{ent}", "extracted",
            value=str(spec), source=f"'at least {n} {ent_raw}'")
    if re.search(r"nudge:", body):
        rec("completeness.yaml", "nudges", "not_extracted",
            reason="generator-gap: SDK completeness manifest has no nudge-text field")
    exclude = []
    m = re.search(r"Don'?t count:\s*([^)\n]+)", body)
    if m:
        for item in m.group(1).split(","):
            item = item.strip().rstrip(".")
            ent = next((e for e in known_entities if e.lower() == item.lower()), None)
            if ent:
                exclude.append(ent)
                rec("completeness.yaml", f"exclude:{ent}", "extracted", source="Don't count line")
            else:
                rec("completeness.yaml", f"exclude:{item}", "not_extracted",
                    reason=f"{item!r} is a category/unknown, not an entity name — needs"
                           " contract-vocabulary tightening or category expansion rule")
    out = {"entities": entities}
    if exclude:
        out["exclude"] = exclude
    return out


# ---------------------------------------------------------------- run + round-trip

import yaml

from startd8.backend_codegen.pages_generator import parse_pages
from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.scaffold_codegen.manifest import parse_app_manifest
from startd8.view_codegen.manifest import parse_views
from startd8.backend_codegen.derived import load_completeness_manifest

schema_text = Path(
    "/Users/neilyashinsky/Documents/dev/strtd8/strtd8/prisma/schema.prisma"
).read_text(encoding="utf-8")
schema = parse_prisma_schema(schema_text)
known = frozenset(schema.models)
print(f"contract: {len(schema.models)} models")

pages_data = extract_pages()
nav_routes = {}
if pages_data and "nav" in pages_data:
    nav_routes = {i["label"].lower(): i["href"] for i in pages_data["nav"]}

app_data = extract_app()
views_data = extract_views(known, nav_routes)
completeness_data = extract_completeness(known)

results = {}
for fname, data, parser in (
    ("pages.yaml", pages_data, lambda t: parse_pages(t)),
    ("app.yaml", app_data, lambda t: parse_app_manifest(t)),
    ("views.yaml", views_data, lambda t: parse_views(t, known_entities=known)),
    ("completeness.yaml", completeness_data,
     lambda t: load_completeness_manifest(t) or (_ for _ in ()).throw(ValueError("not a mapping"))),
):
    if data is None:
        results[fname] = "SKIPPED (no source section)"
        continue
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    (OUT / fname).write_text(text, encoding="utf-8")
    try:
        parser(text)
        results[fname] = "ROUND-TRIP CLEAN"
    except Exception as exc:
        results[fname] = f"ROUND-TRIP FAILED: {exc}"

print("\n=== round-trip ===")
for k, v in results.items():
    print(f"  {k:22s} {v}")

by_status = {}
for r in RECORDS:
    by_status.setdefault(r["status"], []).append(r)
print("\n=== extraction report ===")
print(f"  extracted: {len(by_status.get('extracted', []))} | defaulted: "
      f"{len(by_status.get('defaulted', []))} | not_extracted: {len(by_status.get('not_extracted', []))}")
print("\n  -- not_extracted (the findings) --")
for r in by_status.get("not_extracted", []):
    print(f"  [{r['manifest']}] {r['field']}: {r['reason']}")

(Path("/tmp/wireframe_spike") / "extraction-report.json").write_text(
    json.dumps(RECORDS, indent=2) + "\n", encoding="utf-8"
)
