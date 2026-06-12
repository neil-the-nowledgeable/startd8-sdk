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
