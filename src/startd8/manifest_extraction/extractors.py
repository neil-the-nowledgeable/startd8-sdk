"""Per-manifest extractors (§2.2–§2.7) — each returns (data | None, records appended).

All pure functions over parsed sections + the §2.1 :class:`EntityGraph`. No I/O, no LLM.
``None`` data ⇒ no manifest emitted (absent source section ⇒ the wireframe's own absence
semantics apply: ``defaults`` for app/completeness, ``not_defined`` for pages/views/ai).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .entities import EntityGraph, _lower_camel
from .grammar import (
    Section,
    find_section,
    key_lines,
    md_tables,
    nfkd_kebab,
    strip_annotations,
)
from .models import ExtractionRecord, SourceRef, Status

# --------------------------------------------------------------------------- #
# §2.2 Pages → pages.yaml
# --------------------------------------------------------------------------- #

def extract_pages(
    doc_label: str, sections: List[Section], records: List[ExtractionRecord]
) -> Optional[dict]:
    sec = find_section(sections, "Pages")
    if sec is None:
        return None
    tables = md_tables(sec.body)
    if not tables:
        records.append(ExtractionRecord(
            "pages.yaml", "/pages", Status.NOT_EXTRACTED,
            source=SourceRef(doc_label, sec.heading_path),
            reason="Pages section has no table",
        ))
        return None
    pages: List[dict] = []
    for i, row in enumerate(tables[0].dicts()):
        name = strip_annotations(row.get("page", ""))
        content = strip_annotations(row.get("content file", ""))
        if not name or not content:
            records.append(ExtractionRecord(
                "pages.yaml", f"/pages/{i}", Status.NOT_EXTRACTED,
                source=SourceRef(doc_label, sec.heading_path, row_index=i),
                reason="row missing Page or Content file",
            ))
            continue
        # Routes are DERIVED, never authored (contract §2.2): kebab(name); Home → "/".
        slug = "/" if name.lower() == "home" else "/" + nfkd_kebab(name)
        pages.append({"slug": slug, "title": name, "content": f"pages/{content}"})
        records.append(ExtractionRecord(
            "pages.yaml", f"/pages/{len(pages) - 1}/slug", Status.EXTRACTED,
            value=f"{slug} ← {name}",
            source=SourceRef(doc_label, sec.heading_path, row_index=i),
        ))
    if not pages:
        return None
    out: dict = {"pages": pages}
    # Optional Nav table (Label | Target) — overrides when nav ≠ pages. Targets are OPAQUE
    # route strings (CRP R2): emitted verbatim, never validated against page/view routes.
    if len(tables) >= 2 and {"label", "target"} <= set(tables[1].headers):
        nav = []
        for i, row in enumerate(tables[1].dicts()):
            label = strip_annotations(row.get("label", ""))
            target = strip_annotations(row.get("target", ""))
            if label and target:
                nav.append({"label": label, "href": target})
        if nav:
            out["nav"] = nav
            records.append(ExtractionRecord(
                "pages.yaml", "/nav", Status.EXTRACTED,
                value=f"{len(nav)} items (opaque targets, table order)",
                source=SourceRef(doc_label, sec.heading_path),
            ))
    return out


# --------------------------------------------------------------------------- #
# §2.3 Views → views.yaml (runs AFTER the entities pass — fks from join models)
# --------------------------------------------------------------------------- #

# `import-flow` (FR-10 restore) + `computed-panel` (FR-9) are **contract-driven** archetypes: they
# carry no entity fields (parse_views loud-fails entity keys on them), so extract_views emits them
# minimally (route, +compute for the panel) and skips the relations/aggregates derivation.
_KINDS = {"dashboard", "board", "workspace", "detail-compose", "export-package",
          "import-flow", "computed-panel"}
_CONTRACT_KINDS = {"import-flow", "computed-panel"}
_ARROW_RE = re.compile(r"(\w+)\s*(?:→|->)\s*(\w+)")
_COUNTS_RE = re.compile(r"counts of\s+(.+?)(?:\s+per\s+\w+)?$", re.IGNORECASE)


def extract_views(
    doc_label: str,
    sections: List[Section],
    graph: EntityGraph,
    records: List[ExtractionRecord],
) -> Optional[dict]:
    blocks = [s for s in sections if s.title.lower().startswith("view:")]
    if not blocks:
        return None
    views: List[dict] = []
    routes_by_name: Dict[str, str] = {}

    for sec in blocks:
        name = strip_annotations(sec.title.split(":", 1)[1]).strip()
        ident = nfkd_kebab(name).replace("-", "_")
        src = SourceRef(doc_label, sec.heading_path)
        keys, order = key_lines(sec.body)
        kind = keys.get("Kind", "").strip()
        if kind not in _KINDS:
            records.append(ExtractionRecord(
                "views.yaml", f"/views/{ident}", Status.NOT_EXTRACTED, source=src,
                reason=f"Kind {kind!r} outside the published vocabulary",
            ))
            continue

        # Contract-driven archetypes (import-flow / computed-panel): minimal views, no entity logic.
        if kind in _CONTRACT_KINDS:
            route = keys["Route"].split()[0] if keys.get("Route") else f"/{nfkd_kebab(name)}"
            cview: dict = {"name": ident, "kind": kind, "route": route}
            if kind == "computed-panel":
                from ..view_codegen.renderers import compute_binding_names
                compute = keys.get("Compute", "").strip()
                if compute not in compute_binding_names():
                    records.append(ExtractionRecord(
                        "views.yaml", f"/views/{ident}", Status.NOT_EXTRACTED, source=src,
                        reason=f"computed-panel `Compute: {compute or '(missing)'}` is not a registered "
                               f"binding {sorted(compute_binding_names())}",
                    ))
                    continue
                cview["compute"] = compute
            vi = len(views)
            views.append(cview)
            routes_by_name[ident] = route
            records.append(ExtractionRecord(
                "views.yaml", f"/views/{vi}", Status.EXTRACTED, value=f"{name} ({kind})", source=src,
            ))
            continue

        view: dict = {"name": ident, "kind": kind}
        vi = len(views)  # value-path index once appended

        # AR-1: `Scope: model` makes a detail-compose a whole-model compose (the Value Map — every
        # root + relations on ONE page). This is the only archetype that exposes a no-rows surface,
        # so it is also the gate that lets view-copy author an `empty:` (see extract_view_prose).
        _scope = keys.get("Scope", "").strip().lower()
        if _scope == "model" and kind == "detail-compose":
            view["scope"] = "model"
            records.append(ExtractionRecord(
                "views.yaml", f"/views/{vi}/scope", Status.EXTRACTED, value="model", source=src,
            ))
        elif _scope and _scope not in ("", "row"):
            records.append(ExtractionRecord(
                "views.yaml", f"/views/{vi}/scope", Status.NOT_EXTRACTED, source=src,
                reason=f"`Scope: {_scope}` only supports `model` on a detail-compose (else row, default)",
            ))

        # Root (export-package may instead carry Of: — the workspace it bundles).
        root = graph.resolve_entity(keys.get("Root", "")) if keys.get("Root") else None
        of_route: Optional[str] = None
        if kind == "export-package":
            of_name = keys.get("Of", "")
            of_ident = nfkd_kebab(of_name).replace("-", "_")
            of_view = next((v for v in views if v["name"] == of_ident), None)
            if of_view is None:
                records.append(ExtractionRecord(
                    "views.yaml", f"/views/{ident}", Status.NOT_EXTRACTED, source=src,
                    reason=f"export-package Of: {of_name!r} does not reference a prior view",
                ))
                continue
            root = root or of_view["root"]
            of_route = routes_by_name[of_view["name"]]
            if "Formats" in keys:
                records.append(ExtractionRecord(
                    "views.yaml", f"/views/{vi}/formats", Status.NOT_EXTRACTED, source=src,
                    reason="generator-gap: ViewSpec has no format-selection field",
                ))
        if not root:
            records.append(ExtractionRecord(
                "views.yaml", f"/views/{ident}", Status.NOT_EXTRACTED, source=src,
                reason=f"Root {keys.get('Root', '')!r} unresolvable against declared entities",
            ))
            continue
        view["root"] = root

        # board requires Group by: (the column discriminator); optional Order:.
        if kind == "board":
            group_by = keys.get("Group by", "")
            if not group_by:
                records.append(ExtractionRecord(
                    "views.yaml", f"/views/{ident}", Status.NOT_EXTRACTED, source=src,
                    reason="board requires `Group by:` (Root-entity field)",
                ))
                continue
            view["group_by"] = group_by
            if keys.get("Order"):
                view["order"] = [o.strip() for o in keys["Order"].split(",") if o.strip()]

        # Route: kind-aware derivation; explicit `- Route:` overrides (authored format data).
        if keys.get("Route"):
            view["route"] = keys["Route"].split()[0]
            records.append(ExtractionRecord(
                "views.yaml", f"/views/{vi}/route", Status.EXTRACTED,
                value=view["route"], source=src,
            ))
        else:
            if kind == "workspace":
                view["route"] = f"/{nfkd_kebab(root)}/{{id}}"
            elif kind == "export-package":
                view["route"] = f"{of_route}/export"
            else:  # detail-compose / dashboard / board
                view["route"] = f"/{nfkd_kebab(name)}"
            records.append(ExtractionRecord(
                "views.yaml", f"/views/{vi}/route", Status.DEFAULTED,
                value=view["route"], reason=f"kind-aware derivation ({kind})", source=src,
            ))

        # Shows: A→B arrows → relations via the derived join models; counts → aggregates.
        for key in ("Shows", "Also shows"):
            if key not in keys:
                continue
            text = keys[key]
            for left_raw, right_raw in _ARROW_RE.findall(text):
                left = graph.resolve_entity(left_raw)
                right = graph.resolve_entity(right_raw)
                join = graph.join_between(left, right) if left and right else None
                if join is None:
                    records.append(ExtractionRecord(
                        "views.yaml", f"/views/{vi}/relations/{left_raw}-{right_raw}",
                        Status.NOT_EXTRACTED, source=src,
                        reason="fk-unavailable: no §2.1-derived join model for this pair "
                               "(never a guessed `<entity>Id`)",
                    ))
                    continue
                fk = join.fk_left if join.left == (left or "") else join.fk_right
                view.setdefault("relations", []).append(
                    {"name": join.name, "from": join.name, "fk": fk}
                )
                records.append(ExtractionRecord(
                    "views.yaml", f"/views/{vi}/relations/{join.name}", Status.EXTRACTED,
                    value=f"from={join.name} fk={fk}", source=src,
                ))
            counts = _COUNTS_RE.search(text)
            if counts:
                for phrase in re.split(r"\s+and\s+|,", counts.group(1)):
                    phrase = phrase.strip()
                    if not phrase:
                        continue
                    ent = graph.resolve_entity(phrase)
                    if ent is None:
                        records.append(ExtractionRecord(
                            "views.yaml", f"/views/{vi}/aggregates/{nfkd_kebab(phrase)}",
                            Status.NOT_EXTRACTED, source=src,
                            reason=f"entity phrase {phrase!r} unresolvable",
                        ))
                        continue
                    fk = f"{_lower_camel(root)}Id"
                    view.setdefault("aggregates", []).append({
                        "name": f"{nfkd_kebab(phrase).replace('-', '_')}_count",
                        "of": ent, "fk": fk,
                    })
                    records.append(ExtractionRecord(
                        "views.yaml", f"/views/{vi}/aggregates/{ent}", Status.EXTRACTED,
                        value=f"of={ent} fk={fk}", source=src,
                    ))
            if not _ARROW_RE.findall(text) and not counts:
                records.append(ExtractionRecord(
                    "views.yaml", f"/views/{vi}/{key.lower().replace(' ', '_')}",
                    Status.NOT_EXTRACTED, source=src,
                    reason=f"`{key}:` line matches neither the arrow nor the counts grammar "
                           f"(prose): {text[:60]!r}",
                ))

        # Gap callout: → gap.needs_from requires Root-field resolution — flag (F5 posture).
        if "Gap callout" in keys:
            records.append(ExtractionRecord(
                "views.yaml", f"/views/{vi}/gap", Status.NOT_EXTRACTED, source=src,
                reason="`Gap callout:` field-name resolution from prose not in grammar v0.2",
            ))
        # `Empty state:` (and `Title:`/`Intro:`) are view-COPY, owned by extract_view_prose →
        # view_prose.yaml (no longer a dead-end here). They are not structural views.yaml fields.

        views.append(view)
        routes_by_name[ident] = view["route"]
        records.append(ExtractionRecord(
            "views.yaml", f"/views/{vi}", Status.EXTRACTED,
            value=f"{name} ({kind}, root={root})", source=src,
        ))
    return {"views": views} if views else None


# --------------------------------------------------------------------------- #
# §2.3b View copy → view_prose.yaml (the WORDS layer — outside the drift hash)
# --------------------------------------------------------------------------- #

def extract_view_prose(
    doc_label: str,
    sections: List[Section],
    records: List[ExtractionRecord],
) -> Optional[dict]:
    """Harvest authored view COPY from each ``### View:`` block → ``{view-name: {title,intro,…}}``.

    The producer half of the kickoff→``view_prose.yaml`` loop (the consumer ``parse_view_prose`` ships).
    Per-archetype validity is enforced end-to-end; a key on the wrong archetype is **silently dropped**
    (recorded NOT_EXTRACTED, no error — the renderer would raise on it):
    - ``title``/``intro`` — any HTML view;
    - ``empty`` — model-scoped detail-compose only (``Scope: model``, the only no-rows surface);
    - ``success``/``error``/``controls`` — import-flow only (its restore-outcome + button labels).
    View idents match :func:`extract_views` (same ``nfkd_kebab``), so the round-trip's ``known_views``
    (taken from the views candidate, not the entity graph) lines up.
    """
    blocks = [s for s in sections if s.title.lower().startswith("view:")]
    if not blocks:
        return None
    out: Dict[str, dict] = {}
    for sec in blocks:
        name = strip_annotations(sec.title.split(":", 1)[1]).strip()
        ident = nfkd_kebab(name).replace("-", "_")
        src = SourceRef(doc_label, sec.heading_path)
        keys, _ = key_lines(sec.body)
        kind = keys.get("Kind", "").strip()
        scope = keys.get("Scope", "").strip().lower()
        entry: Dict[str, str] = {}
        for src_key, dest_key in (("Title", "title"), ("Intro", "intro")):
            val = _strip_quotes(keys.get(src_key, ""))
            if val:
                entry[dest_key] = val
                records.append(ExtractionRecord(
                    "view_prose.yaml", f"/{ident}/{dest_key}", Status.EXTRACTED,
                    value=val[:60], source=src,
                ))
        empty = _strip_quotes(keys.get("Empty state", ""))
        if empty:
            if kind == "detail-compose" and scope == "model":
                entry["empty"] = empty
                records.append(ExtractionRecord(
                    "view_prose.yaml", f"/{ident}/empty", Status.EXTRACTED,
                    value=empty[:60], source=src,
                ))
            else:
                records.append(ExtractionRecord(
                    "view_prose.yaml", f"/{ident}/empty", Status.NOT_EXTRACTED, source=src,
                    reason="`empty` has a no-rows surface only on a model-scoped detail-compose "
                           "(`Scope: model`); dropped off-archetype to stay back-compatible",
                ))
        # success/error: import-flow RESTORE outcome copy — the only archetype with an outcome surface.
        for src_key, dest_key in (("Success", "success"), ("Error", "error")):
            val = _strip_quotes(keys.get(src_key, ""))
            if not val:
                continue
            if kind == "import-flow":
                entry[dest_key] = val
                records.append(ExtractionRecord(
                    "view_prose.yaml", f"/{ident}/{dest_key}", Status.EXTRACTED, value=val[:60], source=src,
                ))
            else:
                records.append(ExtractionRecord(
                    "view_prose.yaml", f"/{ident}/{dest_key}", Status.NOT_EXTRACTED, source=src,
                    reason=f"`{dest_key}` is import-flow restore-outcome copy; dropped off-archetype",
                ))
        # controls: `id = "label"` pairs, archetype-filtered (import-flow: validate/restore/confirm).
        controls_raw = keys.get("Controls", "").strip()
        if controls_raw:
            if kind != "import-flow":
                records.append(ExtractionRecord(
                    "view_prose.yaml", f"/{ident}/controls", Status.NOT_EXTRACTED, source=src,
                    reason="`controls` is authored only on import-flow today (export-link labels deferred)",
                ))
            else:
                parsed = dict(_CONTROL_RE.findall(controls_raw))
                good = {cid: lbl for cid, lbl in parsed.items() if cid in _IMPORT_CONTROL_IDS}
                if good:
                    entry["controls"] = good
                    records.append(ExtractionRecord(
                        "view_prose.yaml", f"/{ident}/controls", Status.EXTRACTED,
                        value=",".join(sorted(good)), source=src,
                    ))
                for cid in sorted(set(parsed) - _IMPORT_CONTROL_IDS):
                    records.append(ExtractionRecord(
                        "view_prose.yaml", f"/{ident}/controls/{cid}", Status.NOT_EXTRACTED, source=src,
                        reason=f"unknown import-flow control-id {cid!r} (allowed: "
                               f"{sorted(_IMPORT_CONTROL_IDS)})",
                    ))
        if entry:
            out[ident] = entry
    return out if out else None


_CONTROL_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')
_IMPORT_CONTROL_IDS = frozenset({"validate", "restore", "confirm"})


# --------------------------------------------------------------------------- #
# §2.3c Form help → form_prose.yaml (the form WORDS layer — outside the drift hash, FR-FH-8)
# --------------------------------------------------------------------------- #

def extract_form_prose(
    doc_label: str,
    sections: List[Section],
    graph: EntityGraph,
    records: List[ExtractionRecord],
) -> Optional[dict]:
    """Harvest authored form help from each ``### Form: <Entity>`` block → the ``form_prose.yaml`` shape.

    The producer half of the kickoff→``form_prose.yaml`` loop (the consumer ``parse_form_prose`` ships).
    Per block: an optional ``Intro:`` line (key_lines) + a ``Field | Help | Placeholder`` table
    (md_tables). Entity + field targets resolve against the live entity graph — an unknown entity or
    field is recorded ``NOT_EXTRACTED`` (sourced, advisory) and dropped, never guessed, so a typo never
    silently becomes help on the wrong field (the dangling-target discipline, FR-FH-5). The emitted key
    is the **canonical** entity name (so the round-trip's ``known_entities`` lines up), and the canonical
    field name (tolerating case drift in the prose)."""
    blocks = [s for s in sections if s.title.lower().startswith("form:")]
    if not blocks:
        return None
    out: Dict[str, dict] = {}
    for sec in blocks:
        raw_name = strip_annotations(sec.title.split(":", 1)[1]).strip()
        src = SourceRef(doc_label, sec.heading_path)
        ename = graph.resolve_entity(raw_name)
        if ename is None:
            records.append(ExtractionRecord(
                "form_prose.yaml", f"/{nfkd_kebab(raw_name)}", Status.NOT_EXTRACTED, source=src,
                reason=f"`Form: {raw_name}` names no declared entity — author the contract first",
            ))
            continue
        by_lower = {f.name.lower(): f.name for f in graph.entities[ename].fields}
        keys, _ = key_lines(sec.body)
        entry: Dict[str, object] = {}
        intro = _strip_quotes(keys.get("Intro", ""))
        if intro:
            entry["intro"] = intro
            records.append(ExtractionRecord(
                "form_prose.yaml", f"/{ename}/intro", Status.EXTRACTED, value=intro[:60], source=src,
            ))
        fields: Dict[str, dict] = {}
        tables = md_tables(sec.body)
        table = next((t for t in tables if "field" in t.headers), None)
        for i, row in enumerate(table.dicts() if table else ()):
            raw_field = strip_annotations(row.get("field", "")).strip()
            if not raw_field:
                continue
            rsrc = SourceRef(doc_label, sec.heading_path, row_index=i)
            field = raw_field if raw_field in by_lower.values() else by_lower.get(raw_field.lower())
            if field is None:
                records.append(ExtractionRecord(
                    "form_prose.yaml", f"/{ename}/fields/{raw_field}", Status.NOT_EXTRACTED, source=rsrc,
                    reason=f"{ename} has no field {raw_field!r} — help dropped (dangling target)",
                ))
                continue
            spec: Dict[str, str] = {}
            for col in ("help", "placeholder"):
                val = _strip_quotes(row.get(col, ""))
                if val:
                    spec[col] = val
            if spec:
                fields[field] = spec
                records.append(ExtractionRecord(
                    "form_prose.yaml", f"/{ename}/fields/{field}", Status.EXTRACTED,
                    value=spec.get("help", spec.get("placeholder", ""))[:60], source=rsrc,
                ))
        if fields:
            entry["fields"] = fields
        if entry:
            out[ename] = entry
    return {"forms": out} if out else None


def _strip_quotes(value: str) -> str:
    """Authored copy may be quoted (the template shows `- Title: "..."`) or bare; strip one matched
    surrounding pair so the emitted manifest carries the words, not the delimiters."""
    s = value.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


# --------------------------------------------------------------------------- #
# §2.4 Completeness → completeness.yaml (after entities — category expansion)
# --------------------------------------------------------------------------- #

_INTRO_RE = re.compile(r"is complete when it has", re.IGNORECASE)
_SIGNAL_RE = re.compile(r"at least (\d+) ([A-Za-z]+)(?:\s*\(weight (\d+)\))?")
_DONT_COUNT_RE = re.compile(r"Don'?t count:\s*([^)\n]+)", re.IGNORECASE)
_CATEGORY_WORDS = {"connection records", "join tables"}


def extract_completeness(
    doc_label: str,
    sections: List[Section],
    graph: EntityGraph,
    records: List[ExtractionRecord],
) -> Optional[dict]:
    sec = next(
        (s for s in sections if _INTRO_RE.search(s.body) or s.title.lower().startswith("completeness")),
        None,
    )
    if sec is None or not _INTRO_RE.search(sec.body):
        return None
    src = SourceRef(doc_label, sec.heading_path)
    entities: Dict[str, dict] = {}
    for m in _SIGNAL_RE.finditer(sec.body):
        n, surface, weight = m.groups()
        ent = graph.resolve_entity(surface)
        line = m.group(0)
        if ent is None:
            records.append(ExtractionRecord(
                "completeness.yaml", f"/entities/{surface}", Status.NOT_EXTRACTED,
                source=SourceRef(doc_label, sec.heading_path, line=line),
                reason=f"entity {surface!r} not declared",
            ))
            continue
        spec: dict = {"min_rows": int(n)}
        if weight:
            spec["weight"] = int(weight)
        entities[ent] = spec
        records.append(ExtractionRecord(
            "completeness.yaml", f"/entities/{ent}", Status.EXTRACTED,
            value=str(spec), source=SourceRef(doc_label, sec.heading_path, line=line),
        ))
        # Nudge suffix: tolerated, but the SDK manifest can't hold it — TWO rows per entry.
        tail = sec.body[m.end():m.end() + 120].split("\n", 1)[0]
        if "nudge:" in tail:
            records.append(ExtractionRecord(
                "completeness.yaml", f"/entities/{ent}/nudge", Status.NOT_EXTRACTED,
                source=SourceRef(doc_label, sec.heading_path, line=line),
                reason="generator-gap: SDK completeness manifest has no nudge-text field",
            ))
    if not entities:
        return None
    out: dict = {"entities": entities}
    m = _DONT_COUNT_RE.search(sec.body)
    if m:
        exclude: List[str] = []
        for item in m.group(1).split(","):
            item = item.strip().rstrip(".")
            if item.lower() in _CATEGORY_WORDS:
                # Category words expand to the §2.1-derived join models — deterministic,
                # schema-derived, never guessed (CRP R2 + spike F4).
                for jn in graph.join_names:
                    if jn not in exclude:
                        exclude.append(jn)
                records.append(ExtractionRecord(
                    "completeness.yaml", f"/exclude/{item.replace(' ', '_')}",
                    Status.EXTRACTED,
                    value=f"category → {len(graph.join_names)} join models", source=src,
                ))
                continue
            ent = graph.resolve_entity(item)
            if ent:
                if ent not in exclude:
                    exclude.append(ent)
                records.append(ExtractionRecord(
                    "completeness.yaml", f"/exclude/{ent}", Status.EXTRACTED, source=src,
                ))
            else:
                records.append(ExtractionRecord(
                    "completeness.yaml", f"/exclude/{item}", Status.NOT_EXTRACTED, source=src,
                    reason=f"{item!r} is neither a category word nor a declared entity",
                ))
        if exclude:
            out["exclude"] = exclude
    return out


# --------------------------------------------------------------------------- #
# §2.5 AI assists → ai_passes.yaml
# --------------------------------------------------------------------------- #

# Multi-value cell splitting (F-1, strtd8 fidelity note 2026-06-06): REQUIREMENTS authors pack
# several entities into one Reads/Writes cell using any human separator — comma, "·", "+",
# " and ". The deriver must split on ALL of them, or every entity past the first is silently
# lost (4 of 5 strtd8 passes lost a Reads entity; see prisma/ai_passes.yaml corrections).
_MULTI_VALUE_SEP_RE = re.compile(r",|·|\+|\s+and\s+", re.IGNORECASE)


def _split_multi_value(cell: str) -> List[str]:
    """Split a multi-value manifest cell into trimmed, non-empty parts."""
    return [part.strip() for part in _MULTI_VALUE_SEP_RE.split(cell or "") if part.strip()]


def _resolve_entity_phrase(graph: EntityGraph, phrase: str) -> Optional[str]:
    """Resolve *phrase* to a declared entity, tolerating leading qualifier words.

    Reads cells qualify their entities ("confirmed ProofPoints"): try the whole phrase
    first, then drop leading words one at a time so the head noun still resolves. Pure
    prose ("pasted free text") resolves to nothing — the text-mode posture is unchanged.
    """
    words = phrase.split()
    for start in range(len(words)):
        hit = graph.resolve_entity(" ".join(words[start:]))
        if hit:
            return hit
    return None


def extract_ai_passes(
    doc_label: str,
    sections: List[Section],
    graph: EntityGraph,
    records: List[ExtractionRecord],
) -> Optional[dict]:
    sec = find_section(sections, "AI assists") or find_section(sections, "AI-assists")
    if sec is None:
        return None
    tables = md_tables(sec.body)
    if not tables or "assist" not in tables[0].headers:
        return None
    passes: List[dict] = []
    for i, row in enumerate(tables[0].dicts()):
        name = strip_annotations(row.get("assist", ""))
        if not name:
            continue
        src = SourceRef(doc_label, sec.heading_path, row_index=i)
        vi = len(passes)
        writes_raw = re.sub(r"\([^)]*\)", "", row.get("writes", ""))  # "(except value)" = policy, lives in human_inputs
        outputs: List[str] = []
        for part in _split_multi_value(writes_raw):
            ent = graph.resolve_entity(part)
            if ent and ent not in outputs:
                outputs.append(ent)
        if not outputs:
            records.append(ExtractionRecord(
                "ai_passes.yaml", f"/passes/{name}", Status.NOT_EXTRACTED, source=src,
                reason=f"Writes column resolves to no declared entity: {row.get('writes', '')!r}",
            ))
            continue
        # F-1: split multi-value Reads cells on every separator, resolve each part with
        # qualifier tolerance ("confirmed ProofPoints, Outcomes" → [ProofPoint, Outcome]).
        inputs: List[str] = []
        for part in _split_multi_value(row.get("reads", "")):
            ent = _resolve_entity_phrase(graph, part)
            if ent and ent not in inputs:
                inputs.append(ent)
        # non-entity prose ("uploaded resume") ⇒ text-mode pass, no input_entities
        route = f"/{nfkd_kebab(name)}"
        entry: dict = {
            "name": name,
            "output_entities": outputs,
            "route_path": route,
            "prompt": f"prompts/{name}.md",
        }
        if inputs:
            entry["input_entities"] = inputs
        passes.append(entry)
        records.append(ExtractionRecord(
            "ai_passes.yaml", f"/passes/{vi}", Status.EXTRACTED,
            value=f"{name} → {', '.join(outputs)}", source=src,
        ))
        # No Route column exists in the §2.5 grammar; the derived value is honest `defaulted`
        # — the strtd8 hand file shows routes are NOT name-derivable (authored-wins at diff).
        records.append(ExtractionRecord(
            "ai_passes.yaml", f"/passes/{vi}/route_path", Status.DEFAULTED,
            value=route, reason="derived from assist name (no Route column in grammar v0.2)",
            source=src,
        ))
        records.append(ExtractionRecord(
            "ai_passes.yaml", f"/passes/{vi}/prompt", Status.DEFAULTED,
            value=entry["prompt"], reason="prompt path derives from name (contract §2.5)",
            source=src,
        ))
    return {"passes": passes} if passes else None


# --------------------------------------------------------------------------- #
# §2.6 Owned fields → human_inputs.yaml (line + §2.1 field notes, merged)
# --------------------------------------------------------------------------- #

_ONLY_HUMANS_RE = re.compile(r"Only humans enter:\s*([^\n]+)", re.IGNORECASE)


def extract_human_inputs(
    doc_label: str,
    doc_text: str,
    graph: EntityGraph,
    records: List[ExtractionRecord],
) -> Optional[dict]:
    targets: List[str] = []

    def add(target: str, src: SourceRef) -> None:
        if target not in targets:
            targets.append(target)
            records.append(ExtractionRecord(
                "human_inputs.yaml", f"/fields/{target}", Status.EXTRACTED, source=src,
            ))

    m = _ONLY_HUMANS_RE.search(doc_text)
    if m:
        for raw in m.group(1).split(","):
            raw = raw.strip().rstrip(".")
            if "." in raw:
                ent_raw, _, fld = raw.partition(".")
                ent = graph.resolve_entity(ent_raw)
                if ent:
                    add(f"{ent}.{fld}", SourceRef(doc_label, (), line=m.group(0)))
                else:
                    records.append(ExtractionRecord(
                        "human_inputs.yaml", f"/fields/{raw}", Status.NOT_EXTRACTED,
                        source=SourceRef(doc_label, (), line=m.group(0)),
                        reason=f"entity {ent_raw!r} not declared",
                    ))
    # Field-note source (reinforced inline): ONLY HUMANS ENTER THIS in §2.1 tables.
    for ent in graph.entities.values():
        for f in ent.fields:
            if f.human_only:
                add(
                    f"{ent.name}.{f.name}",
                    SourceRef(doc_label, ent.heading_path, row_index=f.row_index),
                )
    if not targets:
        return None
    return {"fields": [{"target": t, "authored_by": "human"} for t in targets]}


# --------------------------------------------------------------------------- #
# §2.7 Scaffold & runtime → app.yaml (subset rule — sweep-2/F-gap)
# --------------------------------------------------------------------------- #

# Settings with no AppManifest home (sweep 2): flagged, never emitted as unknown keys.
_NO_MANIFEST_HOME = {"port", "sqlite mode", "env keys"}


def extract_app(
    doc_label: str, sections: List[Section], records: List[ExtractionRecord]
) -> Optional[dict]:
    sec = find_section(sections, "Scaffold & runtime")
    if sec is None:
        return None  # optional section — absent ⇒ scaffold defaults (the wireframe shows them)
    tables = md_tables(sec.body)
    if not tables:
        return None
    out: dict = {}

    def put(section: str, key: str, value, src: SourceRef) -> None:
        out.setdefault(section, {})[key] = value
        records.append(ExtractionRecord(
            "app.yaml", f"/{section}/{key}", Status.EXTRACTED, value=str(value), source=src,
        ))

    for i, row in enumerate(tables[0].dicts()):
        setting = strip_annotations(row.get("setting", "")).lower()
        value = strip_annotations(row.get("value", ""))
        src = SourceRef(doc_label, sec.heading_path, row_index=i)
        if setting in _NO_MANIFEST_HOME:
            records.append(ExtractionRecord(
                "app.yaml", f"/{setting.replace(' ', '_')}", Status.NOT_EXTRACTED, source=src,
                reason="generator-gap: no AppManifest field (scaffold-codegen backlog)",
            ))
            continue
        if setting == "package name":
            put("app", "package", value, src)
        elif setting == "display name":
            put("app", "name", value, src)
        elif setting == "python version":
            put("app", "python_version", value, src)
        elif setting == "database":
            m = re.search(r"sqlite:///(\S+)", value)
            put("persistence", "path", m.group(1) if m else value, src)
        elif setting == "logging":
            put("logging", "file", value.split(",")[0].strip(), src)
        elif setting == "migrations":
            put("migrations", "enabled", not value.lower().startswith("no"), src)
        elif setting == "container":
            put("container", "dockerfile", value.lower().startswith("yes"), src)
        else:
            records.append(ExtractionRecord(
                "app.yaml", f"/{setting.replace(' ', '_') or i}", Status.NOT_EXTRACTED,
                source=src, reason=f"setting {setting!r} outside the §2.7 vocabulary",
            ))
    return out or None


# --------------------------------------------------------------------------- #
# §2.8 Imports → imports.yaml (FR-IMP-3)
# --------------------------------------------------------------------------- #

_TRUTHY = {"yes", "y", "true", "1", "✓", "x", "✔"}


def extract_imports(
    doc_label: str,
    sections: List[Section],
    graph: EntityGraph,
    records: List[ExtractionRecord],
) -> Optional[dict]:
    """§2.8 ``## Imports`` table → ``imports.yaml`` (FR-IMP-3).

    Columns (closed grammar): **Entity | Format | Identity | Provenance | Extract via | Surface**.
    The Entity is resolved against the graph; the other cross-refs (Provenance → human_inputs,
    Extract via → ai_passes) are validated at the round-trip gate where the sibling candidates are
    known. OQ-IMP-5: a ``source`` identity with a blank Provenance is recorded ``not_extracted`` and
    dropped here (so the gate never sees an unsatisfiable source import).
    """
    sec = find_section(sections, "Imports") or find_section(sections, "Bulk import")
    if sec is None:
        return None  # optional section — absent ⇒ no import owned-kind (opt-in, FR-IMP-3)
    tables = md_tables(sec.body)
    if not tables or "entity" not in tables[0].headers:
        return None
    imports: Dict[str, dict] = {}
    for i, row in enumerate(tables[0].dicts()):
        ent_raw = strip_annotations(row.get("entity", ""))
        if not ent_raw:
            continue
        src = SourceRef(doc_label, sec.heading_path, row_index=i)
        entity = graph.resolve_entity(ent_raw)
        if not entity:
            records.append(ExtractionRecord(
                "imports.yaml", f"/imports/{ent_raw}", Status.NOT_EXTRACTED, source=src,
                reason=f"Entity column resolves to no declared entity: {ent_raw!r}",
            ))
            continue
        if entity in imports:
            records.append(ExtractionRecord(
                "imports.yaml", f"/imports/{entity}", Status.NOT_EXTRACTED, source=src,
                reason=f"duplicate import row for {entity!r} (first wins)",
            ))
            continue

        fmt = strip_annotations(row.get("format", "")).lower() or "json"
        identity = strip_annotations(row.get("identity", ""))
        provenance = strip_annotations(row.get("provenance", ""))
        extract_via = strip_annotations(row.get("extract via", "")) or strip_annotations(
            row.get("extract_via", "")
        )
        surface_cell = strip_annotations(row.get("surface", "")).lower()
        surface = surface_cell in _TRUTHY

        # OQ-IMP-5: source-scoped identity needs a provenance field — drop loudly if missing.
        if identity.lower().startswith("source") and not provenance:
            records.append(ExtractionRecord(
                "imports.yaml", f"/imports/{entity}", Status.NOT_EXTRACTED, source=src,
                reason="identity is source-scoped but no Provenance field declared (OQ-IMP-5)",
            ))
            continue

        spec: dict = {"format": fmt}
        if identity:
            spec["identity"] = identity
        if provenance:
            spec["provenance"] = provenance
        if extract_via:
            spec["extract_via"] = extract_via
        if surface:
            spec["surface"] = True
        imports[entity] = spec
        records.append(ExtractionRecord(
            "imports.yaml", f"/imports/{entity}", Status.EXTRACTED,
            value=f"{entity} ({fmt})", source=src,
        ))
    return {"imports": imports} if imports else None


# --------------------------------------------------------------------------- #
# §2.12 Observability → observability.yaml (Slice 1: Thresholds + Receivers)
# --------------------------------------------------------------------------- #
def extract_observability(
    label: str, text: str, records: List[ExtractionRecord]
) -> Optional[dict]:
    """§2.12 ``## Observability`` prose → observability.yaml candidate + traceability records.

    Reuses the strict ``ObservabilitySpec`` parser (no grammar duplication). A malformed row (bad
    op, non-numeric value, literal-secret receiver target) is reported as one ``not_extracted`` flag
    for the section (the strict parser loud-fails on the first); fix the flagged prose and re-check
    (the §3 friction loop). Returns ``None`` when there is no ``## Observability`` section.
    """
    from ..observability.spec_from_prose import extract_observability as _to_spec

    try:
        spec = _to_spec(text)
    except ValueError as exc:
        records.append(ExtractionRecord(
            "observability.yaml", "/alerting", Status.NOT_EXTRACTED,
            source=SourceRef(doc=label, heading_path=("Observability",)),
            reason=str(exc),
        ))
        return None

    if not spec.signals and not spec.receivers:
        return None  # absent / empty ## Observability section

    for sig in spec.signals:
        val = (
            f"{sig.name} {sig.threshold.op} {sig.threshold.value}"
            if sig.threshold is not None else (sig.expr or "")
        )
        records.append(ExtractionRecord(
            "observability.yaml", f"/alerting/metric_thresholds/{sig.name}", Status.EXTRACTED,
            value=val,
            source=SourceRef(doc=label, heading_path=("Observability", "Alerting", "Thresholds")),
        ))
    for r in spec.receivers:
        records.append(ExtractionRecord(
            "observability.yaml", f"/alerting/receivers/{r.name}", Status.EXTRACTED,
            value=r.target,
            source=SourceRef(doc=label, heading_path=("Observability", "Alerting", "Receivers")),
        ))
    # Slices 2-3 (context) — one record per present section + per channel.
    obs_src = SourceRef(doc=label, heading_path=("Observability",))
    for key in ("service_levels", "collection", "runbook"):
        if key in spec.context:
            records.append(ExtractionRecord(
                "observability.yaml", f"/{key}", Status.EXTRACTED, source=obs_src,
            ))
    for i, ch in enumerate(spec.context.get("alerting", {}).get("channels", [])):
        records.append(ExtractionRecord(
            "observability.yaml", f"/alerting/channels/{i}", Status.EXTRACTED, value=ch,
            source=SourceRef(doc=label, heading_path=("Observability", "Alerting", "Channels")),
        ))
    # Full observability.yaml candidate (context + alerting + scalars) — complete + round-trippable.
    candidate = dict(spec.context)
    alerting = dict(candidate.get("alerting", {}))
    alerting["metric_thresholds"] = spec.metric_thresholds()
    alerting["receivers"] = spec.receivers_list()
    candidate["alerting"] = alerting
    if spec.provenance_default:
        candidate["provenance_default"] = spec.provenance_default
    if spec.industry_dataset:
        candidate["industry_dataset"] = spec.industry_dataset
    return candidate


# --------------------------------------------------------------------------- #
# §2.9 Technology conventions → conventions.yaml (the value-input proving slice — FR-VIP)
# --------------------------------------------------------------------------- #

# `### Naming` aspect synonyms → the conventions.yaml `naming` keys (FR-VIP §4). Open vocab otherwise
# (D-VIP-3): an unrecognized aspect normalizes by spaces→underscore rather than being dropped.
_NAMING_SYNONYMS = {
    "routes": "route_style", "route": "route_style", "route style": "route_style",
    "files": "files", "file": "files",
    "classes": "classes", "class": "classes",
    "metric prefix": "metric_prefix", "metrics prefix": "metric_prefix",
}
_DATA_MODEL_SCALAR_ENUMS = {
    "money": frozenset({"cents", "float"}),
    "datetime": frozenset({"utc", "local"}),
    "recurrence": frozenset({"structured", "rrule", "none"}),
    "references": frozenset({"fk-only", "loose-allowed"}),
    "weekday": frozenset({"iso", "us"}),
}


def _norm_key(text: str) -> str:
    """A table Role/Layer cell → a YAML key: lower-cased, spaces→underscore (``data layer``→``data_layer``)."""
    return "_".join(strip_annotations(text).strip().lower().split())


def _bullets(body: str) -> List[str]:
    """Top-level ``- `` bullets in *body*, verbatim (one line each, the leading marker stripped). Stops
    at the first sub-heading is unnecessary — a Section's body already excludes child-heading content."""
    out: List[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("- "):
            out.append(s[2:].strip())
    return out


def _child_section(sections: List[Section], parent: str, title: str) -> Optional[Section]:
    """The section whose heading is *title* and whose heading_path contains *parent* (so a subsection is
    resolved unambiguously even if the title recurs elsewhere — the same scoping the form/view extractors use)."""
    tl = title.lower()
    for s in sections:
        if s.title.lower() == tl and parent in s.heading_path:
            return s
    return None


def extract_conventions(
    doc_label: str,
    sections: List[Section],
    records: List[ExtractionRecord],
) -> Optional[dict]:
    """§2.9 ``## Technology conventions`` prose → ``conventions.yaml`` candidate + traceability records.

    The value-input proving slice (FR-VIP-1). Reads the section's key-lines (``Language``/``Field
    authorship``/``Provenance default``) + the ``| Layer | Choice |`` stack table, and the subsections
    ``### Module layout`` (``| Role | Path |``), ``### Naming`` (``| Aspect | Style |``, aspect synonyms),
    ``### Data-model conventions`` (FR-F6 enums + ``#### Computed fields``/``#### Deferred`` bullets), and
    ``### Architecture invariants`` (bullets, verbatim). Emits ``domain: conventions``. A bad data-model
    enum or an unknown data-model key is recorded ``NOT_EXTRACTED`` (flag, never guess — contract §3);
    the round-trip gate validates the whole candidate through ``parse_conventions``. Returns ``None`` when
    there is no ``## Technology conventions`` section (project-agnostic — FR-VIP-9)."""
    root = find_section(sections, "Technology conventions")
    if root is None:
        return None
    parent = root.title  # the heading_path anchor for the subsections
    src = SourceRef(doc_label, root.heading_path)

    out: Dict[str, object] = {"domain": "conventions"}
    keys, _ = key_lines(root.body)  # leading prose tolerated; the stack table terminates the key block
    language = strip_annotations(keys.get("Language", "")).strip()
    if not language:
        records.append(ExtractionRecord(
            "conventions.yaml", "/language", Status.NOT_EXTRACTED, source=src,
            reason="`## Technology conventions` has no `- Language:` line (required)",
        ))
        return None  # without the required field there is no valid candidate to round-trip
    out["language"] = language
    records.append(ExtractionRecord(
        "conventions.yaml", "/language", Status.EXTRACTED, value=language, source=src))
    for src_key, dest in (("Field authorship", "field_authorship"),
                          ("Provenance default", "provenance_default")):
        val = strip_annotations(keys.get(src_key, "")).strip()
        if val:
            out[dest] = val
            records.append(ExtractionRecord(
                "conventions.yaml", f"/{dest}", Status.EXTRACTED, value=val, source=src))

    # stack: the `| Layer | Choice | … |` table in the root body (Layer→key, Choice→value).
    stack_tables = [t for t in md_tables(root.body) if "layer" in t.headers and "choice" in t.headers]
    if stack_tables:
        stack = {}
        for i, row in enumerate(stack_tables[0].dicts()):
            layer, choice = _norm_key(row.get("layer", "")), strip_annotations(row.get("choice", "")).strip()
            if layer and choice:
                stack[layer] = choice
                records.append(ExtractionRecord(
                    "conventions.yaml", f"/stack/{layer}", Status.EXTRACTED, value=choice,
                    source=SourceRef(doc_label, root.heading_path, row_index=i)))
        if stack:
            out["stack"] = stack

    # module_paths: `### Module layout` `| Role | Path |`.
    ml = _child_section(sections, parent, "Module layout")
    if ml is not None:
        mtables = [t for t in md_tables(ml.body) if "role" in t.headers and "path" in t.headers]
        if mtables:
            paths = {}
            for i, row in enumerate(mtables[0].dicts()):
                role, path = _norm_key(row.get("role", "")), strip_annotations(row.get("path", "")).strip()
                if role and path:
                    paths[role] = path
                    records.append(ExtractionRecord(
                        "conventions.yaml", f"/module_paths/{role}", Status.EXTRACTED, value=path,
                        source=SourceRef(doc_label, ml.heading_path, row_index=i)))
            if paths:
                out["module_paths"] = paths

    # naming: `### Naming` `| Aspect | Style |` (aspect synonyms → the canonical naming keys).
    nm = _child_section(sections, parent, "Naming")
    if nm is not None:
        ntables = [t for t in md_tables(nm.body) if "aspect" in t.headers and "style" in t.headers]
        if ntables:
            naming = {}
            for i, row in enumerate(ntables[0].dicts()):
                raw = strip_annotations(row.get("aspect", "")).strip().lower()
                key = _NAMING_SYNONYMS.get(raw, _norm_key(raw))
                style = strip_annotations(row.get("style", "")).strip()
                if key and style:
                    naming[key] = style
                    records.append(ExtractionRecord(
                        "conventions.yaml", f"/naming/{key}", Status.EXTRACTED, value=style,
                        source=SourceRef(doc_label, nm.heading_path, row_index=i)))
            if naming:
                out["naming"] = naming

    # data_model: `### Data-model conventions` (FR-F6) — enum scalars + computed/deferred bullet lists.
    dm = _child_section(sections, parent, "Data-model conventions")
    if dm is not None:
        dm_src = SourceRef(doc_label, dm.heading_path)
        dmodel: Dict[str, object] = {}
        dm_keys, _ = key_lines(dm.body)
        for raw_key, raw_val in dm_keys.items():
            key = raw_key.strip().lower()
            val = strip_annotations(raw_val).strip().lower()
            allowed = _DATA_MODEL_SCALAR_ENUMS.get(key)
            if allowed is None:
                records.append(ExtractionRecord(
                    "conventions.yaml", f"/data_model/{key}", Status.NOT_EXTRACTED, source=dm_src,
                    reason=f"unknown data-model key {raw_key!r} (allowed: {sorted(_DATA_MODEL_SCALAR_ENUMS)})"))
            elif val not in allowed:
                records.append(ExtractionRecord(
                    "conventions.yaml", f"/data_model/{key}", Status.NOT_EXTRACTED, source=dm_src,
                    reason=f"`{key}` value {val!r} outside the vocabulary {sorted(allowed)}"))
            else:
                dmodel[key] = val
                records.append(ExtractionRecord(
                    "conventions.yaml", f"/data_model/{key}", Status.EXTRACTED, value=val, source=dm_src))
        for sub, dest in (("Computed fields", "computed_fields"), ("Deferred", "deferred")):
            child = _child_section(sections, "Data-model conventions", sub)
            items = _bullets(child.body) if child is not None else []
            if items:
                dmodel[dest] = items
                records.append(ExtractionRecord(
                    "conventions.yaml", f"/data_model/{dest}", Status.EXTRACTED,
                    value=f"{len(items)} item(s)", source=dm_src))
        if dmodel:
            out["data_model"] = dmodel

    # architecture_notes: `### Architecture invariants` bullets, verbatim (the load-bearing rules).
    ai = _child_section(sections, parent, "Architecture invariants")
    if ai is not None:
        notes = _bullets(ai.body)
        if notes:
            out["architecture_notes"] = notes
            records.append(ExtractionRecord(
                "conventions.yaml", "/architecture_notes", Status.EXTRACTED,
                value=f"{len(notes)} invariant(s)", source=SourceRef(doc_label, ai.heading_path)))

    return out


# --------------------------------------------------------------------------- #
# §2.11 Build preferences → build-preferences.yaml (value-input fan-out — FR-VIP)
# --------------------------------------------------------------------------- #

_BOOL_TRUE = {"true", "yes", "y", "1"}
_BOOL_FALSE = {"false", "no", "n", "0"}
_INT_RE = re.compile(r"^-?\d+$")

# `### <Subsection>` → conventions-style `- Key: value` group. `unattended.non_interactive` is the
# one bool field (the how-to mapping); everything else is a string (model TIER names, never versions).
_BP_GROUPS = (
    ("Budgets", "budgets", frozenset()),
    ("Model routing", "model_routing", frozenset()),
    ("Generation", "generation", frozenset()),
    ("Unattended", "unattended", frozenset({"non_interactive"})),
)


def extract_build_preferences(
    doc_label: str,
    sections: List[Section],
    records: List[ExtractionRecord],
) -> Optional[dict]:
    """§2.11 ``## Build preferences`` prose → ``build-preferences.yaml`` candidate + records (FR-VIP).

    A ``Provenance default`` key-line + one ``### <group>`` per ``budgets``/``model_routing``/
    ``generation``/``unattended`` (each a block of ``- Key: value`` lines, key→snake_case).
    ``unattended.non_interactive`` coerces to a bool; a non-bool there is flagged, never guessed.
    Emits ``domain: build-preferences``. Returns ``None`` when there is no section (FR-VIP-9)."""
    root = find_section(sections, "Build preferences")
    if root is None:
        return None
    parent = root.title
    src = SourceRef(doc_label, root.heading_path)
    out: Dict[str, object] = {"domain": "build-preferences"}

    keys, _ = key_lines(root.body)
    prov = strip_annotations(keys.get("Provenance default", "")).strip()
    if prov:
        out["provenance_default"] = prov
        records.append(ExtractionRecord(
            "build-preferences.yaml", "/provenance_default", Status.EXTRACTED, value=prov, source=src))

    for title, dest, bool_keys in _BP_GROUPS:
        sec = _child_section(sections, parent, title)
        if sec is None:
            continue
        gsrc = SourceRef(doc_label, sec.heading_path)
        gkeys, _ = key_lines(sec.body)
        group: Dict[str, object] = {}
        for raw_key, raw_val in gkeys.items():
            k = _norm_key(raw_key)
            v = strip_annotations(raw_val).strip()
            if k in bool_keys:
                low = v.lower()
                if low in _BOOL_TRUE:
                    group[k] = True
                elif low in _BOOL_FALSE:
                    group[k] = False
                else:
                    records.append(ExtractionRecord(
                        "build-preferences.yaml", f"/{dest}/{k}", Status.NOT_EXTRACTED, source=gsrc,
                        reason=f"`{k}` must be a boolean (true/false), got {v!r}"))
                    continue
            else:
                group[k] = v
            records.append(ExtractionRecord(
                "build-preferences.yaml", f"/{dest}/{k}", Status.EXTRACTED,
                value=str(group[k])[:60], source=gsrc))
        if group:
            out[dest] = group

    return out


# --------------------------------------------------------------------------- #
# §2.10 Business targets → business-targets.yaml (value-input fan-out — FR-VIP)
# --------------------------------------------------------------------------- #

# `### <Subsection>` → the metric-group key (the only recognized groups; anything else is flagged).
_BT_METRIC_GROUPS = {"outcomes": "product_funnel", "usage": "traction", "unit economics": "unit_economics"}
# The v1 monetization vocabulary: `not-applicable` expands to the full block (the only supported value).
_MONETIZATION_NA = {
    "mode_now": "not-applicable",
    "conversion_rate": {"target": "N/A", "status": "not-applicable"},
    "price_point": {"target": "N/A", "status": "not-applicable"},
}


def _target_literal(text: str):
    """A `Target` cell → int when it is a bare integer (`0`/`3`/`20`), else the string verbatim."""
    s = text.strip()
    return int(s) if _INT_RE.match(s) else s


def extract_business_targets(
    doc_label: str,
    sections: List[Section],
    records: List[ExtractionRecord],
) -> Optional[dict]:
    """§2.10 ``## Business targets`` prose → ``business-targets.yaml`` candidate + records (FR-VIP).

    A ``Provenance default`` + optional ``Monetization`` key-line (``not-applicable`` expands to the full
    block); one ``| Metric | Target | Why |`` table per group (``### Outcomes``→``product_funnel``,
    ``### Usage``→``traction``, ``### Unit economics``→``unit_economics``); a ``### Per-role goals``
    ``| Role | Goal |`` table → ``per_role_top_goals``. ``Target`` is an int when bare, else a string. An
    unrecognized ``###`` group is flagged ``not_extracted(unknown-group)``, never guessed. Emits
    ``domain: business-targets``. Returns ``None`` when there is no section (FR-VIP-9)."""
    root = find_section(sections, "Business targets")
    if root is None:
        return None
    parent = root.title
    src = SourceRef(doc_label, root.heading_path)
    out: Dict[str, object] = {"domain": "business-targets"}

    keys, _ = key_lines(root.body)
    prov = strip_annotations(keys.get("Provenance default", "")).strip()
    if prov:
        out["provenance_default"] = prov
        records.append(ExtractionRecord(
            "business-targets.yaml", "/provenance_default", Status.EXTRACTED, value=prov, source=src))
    monet = strip_annotations(keys.get("Monetization", "")).strip().lower()
    if monet:
        if monet == "not-applicable":
            out["monetization"] = dict(_MONETIZATION_NA)
            records.append(ExtractionRecord(
                "business-targets.yaml", "/monetization", Status.EXTRACTED, value="not-applicable", source=src))
        else:
            records.append(ExtractionRecord(
                "business-targets.yaml", "/monetization", Status.NOT_EXTRACTED, source=src,
                reason=f"only `not-applicable` is supported in v1 (got {monet!r}); a live funnel needs its own sub-grammar"))

    # One `### <group>` per metric table; `### Per-role goals` is the role table; anything else flagged.
    for sec in [s for s in sections if parent in s.heading_path and s.title != parent
                and len(s.heading_path) == len(root.heading_path) + 1]:
        title = sec.title.strip()
        low = title.lower()
        gsrc = SourceRef(doc_label, sec.heading_path)
        if low in _BT_METRIC_GROUPS:
            dest = _BT_METRIC_GROUPS[low]
            tables = [t for t in md_tables(sec.body) if "metric" in t.headers and "target" in t.headers]
            metrics: Dict[str, dict] = {}
            for i, row in enumerate(tables[0].dicts() if tables else ()):
                metric = _norm_key(row.get("metric", ""))
                if not metric:
                    continue
                entry = {"target": _target_literal(row.get("target", ""))}
                why = strip_annotations(row.get("why", "")).strip()
                if why:
                    entry["why"] = why
                metrics[metric] = entry
                records.append(ExtractionRecord(
                    "business-targets.yaml", f"/{dest}/{metric}", Status.EXTRACTED,
                    value=str(entry["target"]), source=SourceRef(doc_label, sec.heading_path, row_index=i)))
            if metrics:
                out[dest] = metrics
        elif low in ("per-role goals", "per role goals"):
            tables = [t for t in md_tables(sec.body) if "role" in t.headers and "goal" in t.headers]
            roles: Dict[str, str] = {}
            for i, row in enumerate(tables[0].dicts() if tables else ()):
                role = strip_annotations(row.get("role", "")).strip()
                goal = strip_annotations(row.get("goal", "")).strip()
                if role and goal:
                    roles[role] = goal
                    records.append(ExtractionRecord(
                        "business-targets.yaml", f"/per_role_top_goals/{role}", Status.EXTRACTED,
                        value=goal[:60], source=SourceRef(doc_label, sec.heading_path, row_index=i)))
            if roles:
                out["per_role_top_goals"] = roles
        else:
            records.append(ExtractionRecord(
                "business-targets.yaml", f"/{_norm_key(title)}", Status.NOT_EXTRACTED, source=gsrc,
                reason=f"unknown business-targets group {title!r} (allowed: Outcomes, Usage, "
                       "Unit economics, Per-role goals)"))

    return out
