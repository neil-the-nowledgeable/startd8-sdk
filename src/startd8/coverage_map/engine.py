"""Functional core for the structure -> OTel §5 communication coverage maps.

Two halves, both language-agnostic:

* **Generator core** — :func:`serialize`, :func:`sha`, :func:`write_or_check` (the ``--check``
  drift guard), :func:`build_index`, :func:`render_index_md`, driven by a
  :class:`LanguageIndexSpec` (the language's DATA) + a :class:`RenderSpec` (its prose + which
  optional table columns exist).
* **Analyzer core** — :class:`Detector` (``matches`` / ``hyp`` / ``coverage_report``) driven by
  a :class:`CoverageAdapter` (source extensions + exclusions, import extractor, path separator,
  ``has_annotations``).

The ONLY real per-language deltas (verified 2026-08-15 by reading all six scripts):

1. import extraction — a callable the adapter carries (go_parser / java_parser / inline regex);
2. path separator in the matcher — ``"/"`` (Go, Node) vs ``"."`` (Java);
3. source extensions + vendor/build/target exclusions;
4. whether an annotation axis exists (Java = import+annotation; Go, Node = import-only).

Everything else here was copy-paste-duplicated across the six scripts.

Why not reuse ``startd8.languages.protocol.LanguageProfile``? It is the ~30-member
code-generation-pipeline protocol (validation commands, docker images, prompt fragments,
dependency-file generation). This coverage lens needs 4 fields; ``source_extensions`` is the
only clean overlap, but the analyzers layer bespoke path exclusions and use the *parser's*
resolved-module import extractors (``parse_go_imports`` …), not ``LanguageProfile``'s
line-oriented ``extract_import_lines`` / grep-template ``import_pattern_template``. Instantiating
a full profile to borrow one field — then still needing a separate adapter for the other three —
would add indirection without removing duplication. So a lightweight :class:`CoverageAdapter`,
not a ``LanguageProfile`` extension. (Mottainai: reuse where it fits; note where it doesn't.)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Generator core
# ---------------------------------------------------------------------------

def serialize(doc: dict[str, Any]) -> str:
    """Canonical JSON serialization for an index artifact (stable, sorted, trailing newline)."""
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha(text: str) -> str:
    """SHA-256 of *text* (content-identity helper; parity with the legacy per-script ``_sha``)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RenderSpec:
    """Per-language render DATA for the human-readable index doc.

    The prose blocks are genuinely per-language English (a template DSL to generate them would be
    over-abstraction), so they live here as data. The engine owns only the shared *table* mechanics
    and the invariant floor table. ``forms_key`` names the composite→forms field
    (``go_forms`` / ``java_forms`` / ``node_forms``); ``l1_witnessable`` and ``l4_annotations``
    toggle the two Java-only columns.
    """

    header: list[str]                    # lines before the L1 table (title, banner, meta, intro)
    l1_heading: list[str]                # heading + blank lines introducing the L1 table
    l1_witnessable: bool                 # L1 table has a witnessable_at column (Java)
    l1_after: list[str]                  # lines between L1 table and L3 heading
    l3_heading: list[str]                # heading + column header for the L3 composites table
    forms_key: str                       # composite dict key holding form-id refs
    l3_field_col: bool                   # L3 table has a `field` column (Java)
    not_witnessable_line: Callable[[list[dict[str, Any]]], list[str]]  # -> the "not witnessable" block
    l4_heading: list[str]                # heading + column header for the L4 crosswalk table
    l4_annotations: bool                 # L4 table has an annotation-signatures column (Java)
    floor_heading: list[str]             # heading + column header for the floor table
    footer: list[str]                    # trailing lines after the floor table


@dataclass(frozen=True)
class LanguageIndexSpec:
    """A language's coverage-map DATA — everything ``build_index`` and the render need.

    ``structure_forms``, ``composites``, ``not_witnessable``, ``crosswalk`` and ``floor`` are the
    hand-authored L1/L3/L4/floor constants. ``meta`` carries the schema/generator/substrate/tier
    headers; ``detector_label`` is the crosswalk-file detector string; ``resolution_pending`` is the
    optional deferred-axis record (Java/Node). ``render`` supplies the doc's prose + column config.
    """

    meta: dict[str, Any]                          # schema_version, generator, pattern_ref, spec_ref, substrate, tier
    forms_file: str                               # e.g. "go-structure-forms.json"
    structure_forms: list[dict[str, Any]]
    composites: list[dict[str, Any]]
    not_witnessable: list[dict[str, Any]]
    crosswalk: list[dict[str, Any]]
    floor: list[dict[str, Any]]
    detector_label: str                           # crosswalk-file "detector" string
    index_doc: str                                # the .md filename
    render: RenderSpec
    resolution_pending: dict[str, Any] | None = None


def build_index(spec: LanguageIndexSpec) -> dict[str, Any]:
    """Assemble the in-memory index doc (the shape every generator's ``build_index`` returned)."""
    forms = spec.structure_forms
    crosswalk = spec.crosswalk
    floor = spec.floor
    composites = spec.composites
    achievable = [p for p in crosswalk if not p.get("floor")]
    doc: dict[str, Any] = {
        "schema_version": spec.meta["schema_version"],
        "generator": spec.meta["generator"],
        "pattern_ref": spec.meta["pattern_ref"],
        "spec_ref": spec.meta["spec_ref"],
        "substrate": spec.meta["substrate"],
        "tier": spec.meta["tier"],
        "counts": {
            "structure_forms": len(forms),
            "language_composites": len(composites),
            "communication_patterns": len(crosswalk),
            "achievable_patterns": len(achievable),
            "floor_patterns": len(floor),
        },
        "structure_forms": forms,
        "language_composites": composites,
        "composites_not_witnessable": spec.not_witnessable,
        "communication_crosswalk": crosswalk,
        "detectability_floor": floor,
    }
    if spec.resolution_pending is not None:
        doc["resolution_pending"] = spec.resolution_pending
    return doc


def index_files(spec: LanguageIndexSpec, doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The on-disk JSON artifacts this generator owns (index-meta / forms / composites / crosswalk)."""
    crosswalk_file: dict[str, Any] = {
        "schema_version": doc["schema_version"],
        "pattern_ref": doc["pattern_ref"],
        "invariant": "15 §5 keys key-for-key identical to "
                     "python-capability-index/communication-crosswalk.json",
        "detector": spec.detector_label,
        "patterns": doc["communication_crosswalk"],
        "detectability_floor": doc["detectability_floor"],
    }
    if spec.resolution_pending is not None:
        crosswalk_file["resolution_pending"] = doc["resolution_pending"]
    return {
        "index-meta.json": {
            k: doc[k]
            for k in ("schema_version", "generator", "pattern_ref", "spec_ref",
                      "substrate", "tier", "counts")
        },
        spec.forms_file: {
            "schema_version": doc["schema_version"],
            "substrate": doc["substrate"],
            "forms": doc["structure_forms"],
        },
        "language-composites.json": {
            "schema_version": doc["schema_version"],
            "composites": doc["language_composites"],
            "not_witnessable": doc["composites_not_witnessable"],
        },
        "communication-crosswalk.json": crosswalk_file,
    }


def render_index_md(spec: LanguageIndexSpec, doc: dict[str, Any]) -> str:
    """Render the human-readable index doc from the spec's prose + the shared table mechanics."""
    r = spec.render
    L: list[str] = list(r.header)

    # L1 — structural-element surface
    L += r.l1_heading
    if r.l1_witnessable:
        for f in doc["structure_forms"]:
            L.append(f"| `{f['id']}` | {f['form']} | `{f['parser_kind']}` | "
                     f"{f['witnessable_at']} | {f['note']} |")
    else:
        for f in doc["structure_forms"]:
            L.append(f"| `{f['id']}` | {f['form']} | `{f['parser_kind']}` | {f['note']} |")
    L += r.l1_after

    # L3 — language composites
    L += r.l3_heading
    if r.l3_field_col:
        for co in doc["language_composites"]:
            L.append(f"| `{co['id']}` | {co['name']} | {', '.join(co[r.forms_key])} | "
                     f"`{co['field']}` | {co['note']} |")
    else:
        for co in doc["language_composites"]:
            L.append(f"| `{co['id']}` | {co['name']} | {', '.join(co[r.forms_key])} | {co['note']} |")
    L += r.not_witnessable_line(doc["composites_not_witnessable"])

    # L4 — §5 communication crosswalk
    L += r.l4_heading
    for p in doc["communication_crosswalk"]:
        if p.get("floor"):
            continue
        if r.l4_annotations:
            imps = ", ".join(f"`{s}`" for s in p.get("import_signatures", [])) or "—"
            anns = ", ".join(f"`@{s}`" for s in p.get("annotation_signatures", [])) or "—"
            L.append(f"| `{p['id']}` | {p['semconv_domain']} | {p.get('grounding','-')} | {imps} | {anns} |")
        else:
            sigs = ", ".join(f"`{s}`" for s in p.get("import_signatures", []))
            L.append(f"| `{p['id']}` | {p['semconv_domain']} | {p.get('grounding','-')} | {sigs} |")

    # Detectability floor (identical table across all languages)
    L += r.floor_heading
    for fl in doc["detectability_floor"]:
        L.append(f"| `{fl['id']}` | {fl['semconv_domain']} | {fl['reason']} |")

    L += r.footer
    return "\n".join(L) + "\n"


def write_or_check(files: dict[str, dict[str, Any]], out_dir: Path,
                   md_path: Path, md_text: str, *, index_doc: str, generator: str,
                   counts: dict[str, int], check: bool) -> int:
    """Either write the artifacts, or (``check=True``) verify the on-disk copy matches — the drift guard.

    Returns a process exit code: 0 on success (written, or in sync), 1 on drift. This is the
    ``--check`` Kagami/single-source gate every generator ran; content-identity (not mtime).
    """
    if check:
        drift = False
        for name, payload in files.items():
            text = serialize(payload)
            path = out_dir / name
            current = path.read_text(encoding="utf-8") if path.is_file() else None
            if current != text:
                print(f"DRIFT: {name}")
                drift = True
        current_md = md_path.read_text(encoding="utf-8") if md_path.is_file() else None
        if current_md != md_text:
            print(f"DRIFT: {index_doc}")
            drift = True
        if drift:
            print(f"Index OUT OF SYNC — run {generator}")
            return 1
        print(f"OK: index in sync ({counts})")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        (out_dir / name).write_text(serialize(payload), encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    c = counts
    print(f"Wrote {len(files)} JSON files to {out_dir} + {index_doc}  "
          f"(forms={c['structure_forms']} composites={c['language_composites']} "
          f"patterns={c['communication_patterns']} achievable={c['achievable_patterns']} "
          f"floor={c['floor_patterns']})")
    return 0


# ---------------------------------------------------------------------------
# Analyzer core
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CoverageAdapter:
    """The per-language analyzer deltas (the 4 real differences, nothing else).

    * ``extensions`` — source-file suffixes to walk (incl. dot).
    * ``extract_imports`` — ``str -> Iterable[str]`` resolved import module paths/specifiers
      (go_parser.parse_go_imports, java_parser.parse_java_imports, or an inline ESM/CJS regex).
    * ``separator`` — sub-package boundary for collision-safe matching (``"/"`` or ``"."``).
    * ``exclude_segments`` — path parts that exclude a file (vendor / build / target / …).
    * ``exclude_suffixes`` — filename suffixes that exclude a file (Node's ``.d.ts`` / ``.min.js``).
    * ``has_annotations`` — whether the language carries an annotation axis (Java only). When True,
      ``extract_annotations`` supplies the per-file annotation set.
    """

    extensions: frozenset[str]
    extract_imports: Callable[[str], Iterable[str]]
    separator: str
    exclude_segments: frozenset[str] = frozenset()
    exclude_suffixes: tuple[str, ...] = ()
    has_annotations: bool = False
    extract_annotations: Callable[[str], set[str]] | None = None

    def source_files(self, workdir: Path) -> list[Path]:
        """Corpus files under *workdir*, applying the language's segment/suffix exclusions."""
        out: list[Path] = []
        for p in workdir.rglob("*"):
            if p.suffix not in self.extensions:
                continue
            if self.exclude_segments and any(seg in self.exclude_segments for seg in p.parts):
                continue
            if self.exclude_suffixes and any(p.name.endswith(s) for s in self.exclude_suffixes):
                continue
            out.append(p)
        return out


class Detector:
    """Collision-safe import (and optional annotation) matcher over a crosswalk's achievable patterns.

    ``matches`` is the shared prefix-safe rule; ``hyp`` is import-only (Go/Node) and ``hyp_signals``
    is the import+annotation variant (Java). ``coverage_report`` walks a corpus and produces the
    per-language coverage result. Instantiated with the language's :class:`CoverageAdapter`.
    """

    def __init__(self, adapter: CoverageAdapter):
        self.adapter = adapter

    def matches(self, import_path: str, sig: str) -> bool:
        """Exact package OR a sub-package (``sig + separator``) — prevents ``net`` eating ``net/http``."""
        return import_path == sig or import_path.startswith(sig + self.adapter.separator)

    def hyp(self, imports: Iterable[str], achievable: list[dict[str, Any]]) -> list[str]:
        """Import-only hypothesis: achievable pattern ids whose signatures match a file import."""
        hit: list[str] = []
        for pat in achievable:
            sigs = pat.get("import_signatures") or []
            if any(self.matches(imp, sig) for imp in imports for sig in sigs):
                hit.append(pat["id"])
        return hit

    def hyp_signals(self, imports: Iterable[str], annotations: set[str],
                    achievable: list[dict[str, Any]]) -> dict[str, str]:
        """Import+annotation hypothesis: ``{pattern_id: 'import' | 'annotation' | 'both'}`` (Java)."""
        imports = list(imports)
        hits: dict[str, str] = {}
        for pat in achievable:
            imp = any(self.matches(i, s) for i in imports for s in (pat.get("import_signatures") or []))
            ann = any(a in annotations for a in (pat.get("annotation_signatures") or []))
            if imp and ann:
                hits[pat["id"]] = "both"
            elif imp:
                hits[pat["id"]] = "import"
            elif ann:
                hits[pat["id"]] = "annotation"
        return hits


def _corpus_walk(adapter: CoverageAdapter, workdir: Path):
    """Yield ``(rel_path_str, imports, annotations)`` per readable corpus file; count parse errors.

    Wraps the shared file walk + read + extract. ``annotations`` is an empty set for import-only
    languages. Returns ``(files, results, parse_errors)``.
    """
    files = adapter.source_files(workdir)
    results = []
    parse_errors = 0
    for f in sorted(files):
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
            imports = list(adapter.extract_imports(src))
            if adapter.has_annotations and adapter.extract_annotations is not None:
                annotations = adapter.extract_annotations(src)
            else:
                annotations = set()
        except Exception:  # a corpus file we can't read is not a crosswalk failure
            parse_errors += 1
            continue
        results.append((str(f.relative_to(workdir)), imports, annotations))
    return files, results, parse_errors


def coverage_report(adapter: CoverageAdapter, index: dict[str, Any], workdir: Path, *,
                    label: tuple[str, str]) -> dict[str, Any]:
    """Walk *workdir*, compute per-pattern coverage, and build the analyzer result dict.

    ``label`` is the ``(key, value)`` describing the detector on the result — Go emits
    ``("tier", index["tier"])``; Java/Node emit ``("detector", "<detector string>")``. (This is the
    one field where the three legacy results genuinely disagreed; it is data, so the caller passes it.)

    Two output shapes, keyed on ``adapter.has_annotations``:

    * import-only (Go, Node) — flat ``per_pattern_file_counts`` + ``detected`` / ``not_evidenced``;
    * import+annotation (Java) — ``per_pattern_signal_counts`` (import/annotation/both) plus the
      ``annotation_axis`` marginal-value block.

    The two shapes are the real per-language product difference (the annotation axis earns a richer
    report), not accidental duplication — so they are two branches here, not one forced union.
    """
    label_key, label_val = label
    detector = Detector(adapter)
    crosswalk = index["communication_crosswalk"]
    achievable = [p for p in crosswalk if not p.get("floor")]
    floor_ids = [f["id"] for f in index["detectability_floor"]]

    files, walked, parse_errors = _corpus_walk(adapter, workdir)
    per_file: list[dict[str, Any]] = []
    n_ach = len(achievable)

    base = {
        "corpus": str(workdir),
        "generator_index": index["generator"],
        "files_analyzed": len(files),
        "parse_errors": parse_errors,
        # Achievable pattern -> §5 semconv_domain. Carried on the report so downstream
        # renderers (e.g. render_sarif) stay DATA-driven from the report alone, without
        # re-loading the crosswalk. Additive: existing consumers ignore unknown keys.
        "pattern_domains": {p["id"]: p.get("semconv_domain", "") for p in achievable},
    }

    if adapter.has_annotations:
        counts = {p["id"]: {"import": 0, "annotation": 0, "both": 0} for p in achievable}
        for rel, imports, annotations in walked:
            h = detector.hyp_signals(imports, annotations, achievable)
            for pid, sig in h.items():
                counts[pid][sig] += 1
            if h:
                per_file.append({"rel_path": rel, "hyp": h})

        def total(pid: str) -> int:
            return sum(counts[pid].values())

        detected = sorted(pid for pid in counts if total(pid) > 0)
        annotation_only = sorted(
            pid for pid in detected
            if counts[pid]["annotation"] > 0 and counts[pid]["import"] == 0 and counts[pid]["both"] == 0)
        not_evidenced = sorted(p["id"] for p in achievable if total(p["id"]) == 0)
        pct = round(100.0 * len(detected) / n_ach, 1) if n_ach else 0.0
        return {
            **base,
            label_key: label_val,
            "coverage": {
                "achievable_patterns": n_ach,
                "detected_patterns": len(detected),
                "achievable_coverage_percent": pct,
                "floor_patterns_excluded": floor_ids,
            },
            "annotation_axis": {
                "detected_via_annotation_only": annotation_only,
                "marginal_patterns": len(annotation_only),
                "note": "patterns that would be MISSED by imports alone — the annotation axis's "
                        "marginal contribution",
            },
            "detected": detected,
            "not_evidenced_achievable": not_evidenced,
            "per_pattern_signal_counts": counts,
            "per_file_hyp": per_file,
        }

    counts = {p["id"]: 0 for p in achievable}
    for rel, imports, _annotations in walked:
        h = detector.hyp(imports, achievable)
        for pid in h:
            counts[pid] += 1
        if h:
            per_file.append({"rel_path": rel, "hyp": h})
    detected = sorted(pid for pid, n in counts.items() if n > 0)
    not_evidenced = sorted(p["id"] for p in achievable if counts[p["id"]] == 0)
    pct = round(100.0 * len(detected) / n_ach, 1) if n_ach else 0.0
    return {
        **base,
        label_key: label_val,
        "coverage": {
            "achievable_patterns": n_ach,
            "detected_patterns": len(detected),
            "achievable_coverage_percent": pct,
            "floor_patterns_excluded": floor_ids,
        },
        "detected": detected,
        "not_evidenced_achievable": not_evidenced,
        "per_pattern_file_counts": counts,
        "per_file_hyp": per_file,
    }


def render_coverage_md(r: dict[str, Any], *, title: str, generator: str, meta_lines: list[str],
                       json_sibling: str | None = None) -> str:
    """Render the analyzer coverage ``.md``. Shape switches on the presence of signal counts (Java).

    ``meta_lines`` are the per-language summary lines between the banner and the table (they carry
    genuinely different English — the annotation-axis line, tier vs detector wording — so the caller
    passes them). ``json_sibling`` overrides the closing per-file-hyp pointer (Go names the JSON file).
    """
    L = [title, "", f"> Generated by `{generator}` — do not edit.", "",
         f"**Corpus:** `{r['corpus']}`  ",
         f"**Files analyzed:** {r['files_analyzed']} (parse errors: {r['parse_errors']})  "]
    L += meta_lines
    if "per_pattern_signal_counts" in r:
        L += ["", "## Per-pattern signal breakdown (import vs annotation vs both)", "",
              "| Pattern | import | annotation | both | total |",
              "| --- | ---: | ---: | ---: | ---: |"]
        for pid in sorted(r["per_pattern_signal_counts"],
                          key=lambda k: -sum(r["per_pattern_signal_counts"][k].values())):
            s = r["per_pattern_signal_counts"][pid]
            tot = sum(s.values())
            if tot == 0:
                continue
            L.append(f"| `{pid}` | {s['import']} | {s['annotation']} | {s['both']} | {tot} |")
        L += ["", "## Not evidenced (achievable but unseen)", ""]
        L += [f"- `{pid}`" for pid in r["not_evidenced_achievable"]] or ["- (none)"]
        L += ["", f"> Per-file hyp for {len(r['per_file_hyp'])} files is in the JSON sibling.", ""]
        return "\n".join(L) + "\n"

    L += ["", "## Per-pattern file counts (achievable)", "", "| Pattern | Files |", "| --- | ---: |"]
    for pid, n in sorted(r["per_pattern_file_counts"].items(), key=lambda kv: (-kv[1], kv[0])):
        L.append(f"| `{pid}` | {n} |")
    L += ["", "## Not evidenced in this corpus (achievable but unseen)", ""] if json_sibling else \
         ["", "## Not evidenced (achievable but unseen)", ""]
    L += [f"- `{pid}`" for pid in r["not_evidenced_achievable"]] or ["- (none)"]
    if json_sibling:
        L += ["", f"> Per-file hyp for the {len(r['per_file_hyp'])} files with a non-empty hypothesis "
              f"is in the JSON sibling (`{json_sibling}`), not inlined here.", ""]
    else:
        L += ["", f"> Per-file hyp for {len(r['per_file_hyp'])} files is in the JSON sibling.", ""]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# SARIF 2.1.0 renderer (GitHub code-scanning / IDE consumable)
# ---------------------------------------------------------------------------

#: The SARIF 2.1.0 JSON-schema URL (top-level ``$schema``; validators key on this + ``version``).
SARIF_SCHEMA_URI = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
)
_SARIF_INFO_URI = "https://opentelemetry.io/docs/specs/semconv/"


def render_sarif(report: dict[str, Any], *, tool_name: str, corpus: str) -> dict[str, Any]:
    """Render an analyzer coverage *report* as a SARIF 2.1.0 document.

    Behaviour-additive: reads only the report dict (never re-loads the crosswalk), so it works
    for every language's report shape uniformly. It uses:

    * ``report["pattern_domains"]`` — ``{achievable_pattern_id: semconv_domain}``; the driver's
      ``rules`` (one per achievable §5 pattern; ``ruleId`` = pattern id, ``shortDescription`` =
      the semconv_domain).
    * ``report["per_file_hyp"]`` — ``[{"rel_path": …, "hyp": …}]`` where ``hyp`` is either a list of
      detected pattern ids (import-only: Go/Node) or a ``{pattern_id: signal}`` map (Java). One
      SARIF ``result`` per file×detected-pattern, ``level`` "note", ``ruleId`` = the pattern id, a
      file-level ``physicalLocation`` (no line region — this is import-level detection).

    ``tool_name`` becomes ``tool.driver.name`` (e.g. ``otel-comm-coverage-go``); ``corpus`` is
    recorded as an invocation property. The doc validates against the 2.1.0 shape (top-level
    ``$schema`` + ``version`` + a ``runs`` array).
    """
    domains: dict[str, str] = report.get("pattern_domains") or {}

    rules: list[dict[str, Any]] = []
    for pattern_id in sorted(domains):
        domain = domains[pattern_id]
        rules.append({
            "id": pattern_id,
            "name": pattern_id,
            "shortDescription": {"text": domain},
            "helpUri": _SARIF_INFO_URI,
            "defaultConfiguration": {"level": "note"},
        })

    rule_ids = set(domains)
    results: list[dict[str, Any]] = []
    for entry in report.get("per_file_hyp") or []:
        rel_path = entry.get("rel_path", "")
        hyp = entry.get("hyp")
        # import-only reports carry a list of ids; Java carries a {id: signal} map. Both iterate to ids.
        detected_ids = list(hyp.keys()) if isinstance(hyp, dict) else list(hyp or [])
        for pattern_id in detected_ids:
            if pattern_id not in rule_ids:
                continue  # a floor/unknown id would be a rule-less result — skip (never emit invalid)
            domain = domains.get(pattern_id, "")
            results.append({
                "ruleId": pattern_id,
                "level": "note",
                "message": {"text": f"file touches OTel §5 domain {domain}"},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": rel_path},
                    },
                }],
            })

    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": tool_name,
                    "informationUri": _SARIF_INFO_URI,
                    "version": str(report.get("generator_index", "unknown")),
                    "rules": rules,
                },
            },
            "invocations": [{
                "executionSuccessful": True,
                "properties": {"corpus": corpus},
            }],
            "results": results,
        }],
    }
