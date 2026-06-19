"""Resolve per-file communication hypotheses against the Python capability index.

Implements hyp(f) from PYTHON_AST_COMMUNICATION_CAPABILITY_INDEX.md §3:
  hyp(f) = { c ∈ C | detect_import/call/decor intersect φ(c) signatures }

Loads numbered catalogs from ``docs/design/python-capability-index/*.json``.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = REPO_ROOT / "docs" / "design" / "python-capability-index"

GENERATED_SUFFIXES = ("_pb2.py", "_pb2_grpc.py")


@dataclass
class FileSignals:
    """Static signatures extracted from one Python source file."""

    imports: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    decorators: set[str] = field(default_factory=set)
    ast_node_types: set[str] = field(default_factory=set)
    manifest_kinds: set[str] = field(default_factory=set)
    parse_error: Optional[str] = None


@dataclass
class PatternMatch:
    pattern_id: str
    otel_pattern: str
    matched_via: list[str]
    import_hits: list[str] = field(default_factory=list)
    call_hits: list[str] = field(default_factory=list)
    decorator_hits: list[str] = field(default_factory=list)


@dataclass
class FileHypothesisReport:
    path: str
    rel_path: str
    lines: int
    signals: FileSignals
    hyp: list[str]  # pattern ids
    pattern_matches: list[PatternMatch]
    skipped_generated: bool = False


@dataclass
class DimensionCoverage:
    dimension: str
    detected: list[str]
    total: int
    percent: float
    missing: list[str]


@dataclass
class CorpusCoverageReport:
    corpus: str
    workdir: str
    files_analyzed: int
    files_skipped_generated: int
    files_parse_error: int
    per_file: list[FileHypothesisReport]
    dimensions: list[DimensionCoverage]
    overall_index_percent: float
    pattern_union: list[str]
    pattern_missing: list[str]


def load_index(index_dir: Path = INDEX_DIR) -> dict[str, Any]:
    meta = json.loads((index_dir / "index-meta.json").read_text(encoding="utf-8"))
    return {
        "meta": meta,
        "ast_nodes": json.loads((index_dir / "ast-nodes.json").read_text())["nodes"],
        "manifest_kinds": json.loads((index_dir / "manifest-kinds.json").read_text())["kinds"],
        "composites": json.loads((index_dir / "language-composites.json").read_text())["composites"],
        "patterns": json.loads((index_dir / "communication-crosswalk.json").read_text())["patterns"],
    }


def _decorator_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node).lower()
    except Exception:
        if isinstance(node, ast.Name):
            return node.id.lower()
        if isinstance(node, ast.Attribute):
            return node.attr.lower()
        return ""


def _call_text(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        chain: list[str] = []
        cur: ast.AST = func
        while isinstance(cur, ast.Attribute):
            chain.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            chain.append(cur.id)
        chain.reverse()
        base = ".".join(chain)
        return f"{base}("
    if isinstance(func, ast.Name):
        return f"{func.id}("
    try:
        return ast.unparse(func) + "("
    except Exception:
        return "call("


def _collect_imports(node: ast.AST, out: set[str]) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            out.add(alias.name.lower())
            if alias.asname:
                out.add(alias.asname.lower())
    elif isinstance(node, ast.ImportFrom):
        mod = (node.module or "").lower()
        if mod:
            out.add(mod)
        for alias in node.names:
            if mod:
                out.add(f"{mod}.{alias.name}".lower())
            out.add(alias.name.lower())


def _collect_manifest_kinds(tree: ast.AST) -> set[str]:
    kinds: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.class_stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            kinds.add("class")
            self.class_stack.append(node.name)
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    kinds.add("method")
                    if any(
                        isinstance(d, ast.Name) and d.id == "property"
                        or isinstance(d, ast.Attribute) and d.attr == "property"
                        for d in item.decorator_list
                    ):
                        kinds.add("property")
                elif isinstance(item, ast.AsyncFunctionDef):
                    kinds.add("async_method")
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if self.class_stack:
                kinds.add("method")
            else:
                kinds.add("function")
            if any(
                isinstance(d, ast.Name) and d.id == "property"
                or isinstance(d, ast.Attribute) and d.attr == "property"
                for d in node.decorator_list
            ):
                kinds.add("property")
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            kinds.add("async_method" if self.class_stack else "async_function")
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if isinstance(node.target, ast.Name):
                name = node.target.id
                kinds.add("constant" if name.isupper() else "variable")
            kinds.add("type_alias")
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    kinds.add("constant" if tgt.id.isupper() else "variable")
            self.generic_visit(node)

        def visit_TypeAlias(self, node: ast.TypeAlias) -> None:
            kinds.add("type_alias")
            self.generic_visit(node)

    Visitor().visit(tree)
    return kinds


def extract_signals(source: str) -> FileSignals:
    sig = FileSignals()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        sig.parse_error = str(exc)
        return sig

    for node in ast.walk(tree):
        sig.ast_node_types.add(type(node).__name__)
        _collect_imports(node, sig.imports)
        if isinstance(node, ast.Call):
            sig.calls.add(_call_text(node).lower())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                text = _decorator_text(dec)
                if text:
                    sig.decorators.add(text)

    sig.manifest_kinds = _collect_manifest_kinds(tree)
    return sig


def _match_signature(haystack: Iterable[str], needles: list[str]) -> list[str]:
    hits: list[str] = []
    for needle in needles:
        n = needle.lower()
        for h in haystack:
            if n in h:
                hits.append(needle)
                break
    return hits


def match_patterns(signals: FileSignals, patterns: list[dict[str, Any]]) -> list[PatternMatch]:
    if signals.parse_error:
        return []
    matches: list[PatternMatch] = []
    import_pool = signals.imports
    call_pool = signals.calls
    decor_pool = signals.decorators

    for pat in patterns:
        imp_hits = _match_signature(import_pool, pat.get("import_signatures") or [])
        call_hits = _match_signature(call_pool, pat.get("call_signatures") or [])
        dec_hits = _match_signature(decor_pool, pat.get("decorator_signatures") or [])
        # HTTP: ignore call-only dict.get / env.get false positives (Wave 0.2).
        if pat.get("id") == "PY-OTEL-5.1-HTTP":
            generic_get_only = (
                bool(call_hits)
                and not imp_hits
                and not dec_hits
                and all(h == ".get(" for h in call_hits)
            )
            if generic_get_only:
                continue
        if imp_hits or call_hits or dec_hits:
            via: list[str] = []
            if imp_hits:
                via.append("import")
            if call_hits:
                via.append("call")
            if dec_hits:
                via.append("decorator")
            matches.append(
                PatternMatch(
                    pattern_id=pat["id"],
                    otel_pattern=pat.get("otel_pattern", pat["id"]),
                    matched_via=via,
                    import_hits=imp_hits,
                    call_hits=call_hits,
                    decorator_hits=dec_hits,
                )
            )
    return matches


def _composite_detected(comp: dict[str, Any], signals: FileSignals) -> bool:
    nodes = set(comp.get("ast_nodes") or [])
    if nodes & signals.ast_node_types:
        if comp["id"] == "PY-LC-005":
            return bool(signals.decorators)
        return True
    return False


def analyze_file(
    path: Path,
    *,
    workdir: Path,
    patterns: list[dict[str, Any]],
    skip_generated: bool = True,
) -> FileHypothesisReport:
    rel = str(path.relative_to(workdir))
    skipped = skip_generated and path.name.endswith(GENERATED_SUFFIXES)
    if skipped:
        return FileHypothesisReport(
            path=str(path),
            rel_path=rel,
            lines=0,
            signals=FileSignals(),
            hyp=[],
            pattern_matches=[],
            skipped_generated=True,
        )

    source = path.read_text(encoding="utf-8", errors="replace")
    signals = extract_signals(source)
    pmatches = match_patterns(signals, patterns)
    hyp = [m.pattern_id for m in pmatches]
    return FileHypothesisReport(
        path=str(path),
        rel_path=rel,
        lines=source.count("\n") + (1 if source else 0),
        signals=signals,
        hyp=hyp,
        pattern_matches=pmatches,
        skipped_generated=False,
    )


def discover_python_files(workdir: Path, glob: str = "**/*.py") -> list[Path]:
    return sorted(p for p in workdir.glob(glob) if p.is_file())


def analyze_corpus(
    workdir: Path,
    *,
    corpus: str = "otel-demo",
    index: Optional[dict[str, Any]] = None,
    skip_generated: bool = True,
    python_glob: str = "src/**/*.py",
) -> CorpusCoverageReport:
    index = index or load_index()
    patterns = index["patterns"]
    files = discover_python_files(workdir, python_glob)
    reports = [
        analyze_file(p, workdir=workdir, patterns=patterns, skip_generated=skip_generated)
        for p in files
    ]

    active = [r for r in reports if not r.skipped_generated and not r.signals.parse_error]
    parse_errors = [r for r in reports if r.signals.parse_error and not r.skipped_generated]
    skipped = [r for r in reports if r.skipped_generated]

    all_ast: set[str] = set()
    all_manifest: set[str] = set()
    all_composites: set[str] = set()
    pattern_union: set[str] = set()

    for r in active:
        all_ast |= r.signals.ast_node_types
        all_manifest |= r.signals.manifest_kinds
        pattern_union |= set(r.hyp)
        for comp in index["composites"]:
            if _composite_detected(comp, r.signals):
                all_composites.add(comp["id"])

    ast_catalog = {n["name"] for n in index["ast_nodes"]}
    # Only count AST types that appear in the catalog (ignore ast.AST base noise)
    ast_used = sorted(all_ast & ast_catalog)

    manifest_catalog = {k["kind"] for k in index["manifest_kinds"]}
    kind_to_id = {k["kind"]: k["id"] for k in index["manifest_kinds"]}

    pattern_catalog = [p["id"] for p in patterns]
    composite_catalog = [c["id"] for c in index["composites"]]

    def _dim(name: str, detected_ids: list[str], catalog: list[str]) -> DimensionCoverage:
        missing = [x for x in catalog if x not in detected_ids]
        total = len(catalog)
        pct = (len(detected_ids) / total * 100.0) if total else 0.0
        return DimensionCoverage(
            dimension=name,
            detected=sorted(detected_ids),
            total=total,
            percent=round(pct, 1),
            missing=missing,
        )

    dims = [
        _dim("communication_patterns", sorted(pattern_union), pattern_catalog),
        _dim("ast_nodes", ast_used, sorted(ast_catalog)),
        _dim("language_composites", sorted(all_composites), composite_catalog),
        _dim(
            "manifest_kinds",
            sorted(kind_to_id[k] for k in all_manifest if k in kind_to_id),
            [k["id"] for k in index["manifest_kinds"]],
        ),
    ]
    overall = round(sum(d.percent for d in dims) / len(dims), 1) if dims else 0.0

    return CorpusCoverageReport(
        corpus=corpus,
        workdir=str(workdir),
        files_analyzed=len(active),
        files_skipped_generated=len(skipped),
        files_parse_error=len(parse_errors),
        per_file=reports,
        dimensions=dims,
        overall_index_percent=overall,
        pattern_union=sorted(pattern_union),
        pattern_missing=[p for p in pattern_catalog if p not in pattern_union],
    )


def merge_corpus_reports(
    primary: CorpusCoverageReport,
    extra: CorpusCoverageReport,
    *,
    corpus: str | None = None,
) -> CorpusCoverageReport:
    """Merge two reports (e.g. upstream demo + SDK fixtures) into one coverage view."""
    index = load_index()
    pattern_catalog = [p["id"] for p in index["patterns"]]
    ast_catalog = {n["name"] for n in index["ast_nodes"]}
    composite_catalog = [c["id"] for c in index["composites"]]
    kind_to_id = {k["kind"]: k["id"] for k in index["manifest_kinds"]}

    pattern_union: set[str] = set(primary.pattern_union) | set(extra.pattern_union)
    all_ast: set[str] = set()
    all_manifest: set[str] = set()
    all_composites: set[str] = set()

    for r in primary.per_file + extra.per_file:
        if r.skipped_generated or r.signals.parse_error:
            continue
        all_ast |= r.signals.ast_node_types
        all_manifest |= r.signals.manifest_kinds
        for comp in index["composites"]:
            if _composite_detected(comp, r.signals):
                all_composites.add(comp["id"])

    ast_used = sorted(all_ast & ast_catalog)

    def _dim(name: str, detected_ids: list[str], catalog: list[str]) -> DimensionCoverage:
        missing = [x for x in catalog if x not in detected_ids]
        total = len(catalog)
        pct = (len(detected_ids) / total * 100.0) if total else 0.0
        return DimensionCoverage(
            dimension=name,
            detected=sorted(detected_ids),
            total=total,
            percent=round(pct, 1),
            missing=missing,
        )

    dims = [
        _dim("communication_patterns", sorted(pattern_union), pattern_catalog),
        _dim("ast_nodes", ast_used, sorted(ast_catalog)),
        _dim("language_composites", sorted(all_composites), composite_catalog),
        _dim(
            "manifest_kinds",
            sorted(kind_to_id[k] for k in all_manifest if k in kind_to_id),
            [k["id"] for k in index["manifest_kinds"]],
        ),
    ]
    overall = round(sum(d.percent for d in dims) / len(dims), 1) if dims else 0.0

    return CorpusCoverageReport(
        corpus=corpus or f"{primary.corpus}+{extra.corpus}",
        workdir=f"{primary.workdir}+{extra.workdir}",
        files_analyzed=primary.files_analyzed + extra.files_analyzed,
        files_skipped_generated=primary.files_skipped_generated + extra.files_skipped_generated,
        files_parse_error=primary.files_parse_error + extra.files_parse_error,
        per_file=primary.per_file + extra.per_file,
        dimensions=dims,
        overall_index_percent=overall,
        pattern_union=sorted(pattern_union),
        pattern_missing=[p for p in pattern_catalog if p not in pattern_union],
    )


def report_to_dict(report: CorpusCoverageReport) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "corpus": report.corpus,
        "workdir": report.workdir,
        "summary": {
            "files_analyzed": report.files_analyzed,
            "files_skipped_generated": report.files_skipped_generated,
            "files_parse_error": report.files_parse_error,
            "overall_index_percent": report.overall_index_percent,
            "pattern_union": report.pattern_union,
            "pattern_missing": report.pattern_missing,
        },
        "dimensions": [
            {
                "dimension": d.dimension,
                "detected_count": len(d.detected),
                "total": d.total,
                "percent": d.percent,
                "detected": d.detected,
                "missing": d.missing,
            }
            for d in report.dimensions
        ],
        "files": [
            {
                "rel_path": f.rel_path,
                "lines": f.lines,
                "skipped_generated": f.skipped_generated,
                "parse_error": f.signals.parse_error,
                "hyp": f.hyp,
                "manifest_kinds": sorted(f.signals.manifest_kinds),
                "ast_node_count": len(f.signals.ast_node_types),
                "imports_sample": sorted(f.signals.imports)[:30],
                "pattern_matches": [
                    {
                        "pattern_id": m.pattern_id,
                        "otel_pattern": m.otel_pattern,
                        "matched_via": m.matched_via,
                        "import_hits": m.import_hits,
                        "call_hits": m.call_hits,
                        "decorator_hits": m.decorator_hits,
                    }
                    for m in f.pattern_matches
                ],
            }
            for f in report.per_file
        ],
    }
