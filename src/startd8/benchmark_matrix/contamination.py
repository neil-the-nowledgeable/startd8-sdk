"""Contamination / memorization probe via CodeBLEU (FR-47).

Online Boutique is a *public* corpus, so frontier models may reproduce the canonical
implementation from pretraining rather than solving the task. This module measures
**similarity of each generated service to the canonical upstream Online Boutique source**
using CodeBLEU (n-gram + weighted n-gram + AST + dataflow match). High CodeBLEU ⇒ likely
memorization/contamination — a *credibility control* for the leaderboard, NOT a quality term.

This is a port of the edge-brains CodeBLEU work (`scripts/codebleu_score.py`,
`build_codebleu_references.py`), repointed from a fine-tuning corpus to the public upstream
reference. It is **static and $0** — re-scoreable on an existing run's artifacts, no execution.

Caveat the caller must honor: if the run was produced with the SDK's *repair* capability
active, the scored artifacts are repair-polished, which perturbs verbatim regurgitation and
muddies the memorization signal. The clean signal comes from a repair-OFF run.

Dependencies (`codebleu` + per-language tree-sitter parsers) are optional; absence degrades
honestly (FR-32) rather than raising.

Environment caveat (verified 2026-06-14): `codebleu==0.7.0` pins `tree-sitter<0.23`, but on
**Python 3.14** the only installable `tree-sitter-c-sharp` wheels are 0.23.x+ (grammar ABI 15),
which a <0.23 core rejects — so **C# degrades on 3.14** while python/go/java/javascript score
(8/9 OB services). The clean 5/5 stack (codebleu 0.7.0 + tree-sitter 0.22 + tree-sitter-* 0.21)
only resolves on **Python ≤3.11** (edge-brains ran 3.11). Options to lift C#: a dedicated ≤3.11
scorer subprocess, or a newer codebleu that accepts tree-sitter 0.25. Until then C# is degraded,
not failed (FR-32).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# SDK language_id (or file extension) -> CodeBLEU language id.
_CODEBLEU_LANG = {
    "python": "python", ".py": "python",
    "go": "go", ".go": "go",
    "java": "java", ".java": "java",
    "nodejs": "javascript", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    "csharp": "c_sharp", ".cs": "c_sharp",
}

# Directory *segments* that hold non-source artifacts (matched against path parts, NOT raw
# substrings — substring matching mis-fires, e.g. the clone dir "…-latest" contains "test").
_EXCLUDE_DIR_PARTS = frozenset({
    "node_modules", "build", "obj", "bin", "gen", "generated", "__pycache__", ".gradle",
    "loadgenerator", "proto",
})
# Filename markers for non-implementation files (tests, clients, generated stubs, backups).
_EXCLUDE_NAME_MARKERS = ("test", "client", "_pb", ".pb.", "grpc", "mock")


def _is_impl_file(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if parts & _EXCLUDE_DIR_PARTS:
        return False
    name = path.name.lower()
    if name.endswith(".backup") or name == "demo.proto":
        return False
    return not any(m in name for m in _EXCLUDE_NAME_MARKERS)


def codebleu_lang(key: str) -> Optional[str]:
    """Map an SDK language_id or a file extension to a CodeBLEU language id."""
    return _CODEBLEU_LANG.get(key) or _CODEBLEU_LANG.get(Path(key).suffix.lower())


def codebleu_available() -> bool:
    """True if codebleu + the needed tree-sitter parsers import cleanly."""
    try:
        import codebleu  # noqa: F401
        return True
    except Exception:
        return False


def resolve_main_source(root, ext: str) -> Optional[Path]:
    """The service's main implementation file under ``root``: the largest source file with
    extension ``ext``, excluding tests / generated stubs / clients / build output."""
    root = Path(root)
    if not root.exists():
        return None
    cands = [p for p in root.rglob(f"*{ext}") if p.is_file() and _is_impl_file(p)]
    return max(cands, key=lambda p: p.stat().st_size) if cands else None


@dataclass
class ContaminationScore:
    service: str
    model: str
    language: str                 # SDK language_id
    codebleu: Optional[float]     # None when unavailable/degraded
    available: bool
    detail: str = ""
    components: Dict[str, float] = field(default_factory=dict)
    generated_file: str = ""
    reference_file: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


def score_pair(generated_file, reference_file, sdk_language: str) -> ContaminationScore:
    """CodeBLEU of one generated file against its canonical reference. Degrades (available=False)
    on missing files, unsupported language, or absent codebleu/parsers — never raises."""
    lang = codebleu_lang(sdk_language)
    base = dict(service="", model="", language=sdk_language,
                generated_file=str(generated_file or ""), reference_file=str(reference_file or ""))
    if lang is None:
        return ContaminationScore(codebleu=None, available=False,
                                  detail=f"no CodeBLEU language for {sdk_language!r}", **base)
    gp, rp = Path(generated_file) if generated_file else None, Path(reference_file) if reference_file else None
    if not gp or not gp.exists():
        return ContaminationScore(codebleu=None, available=False, detail="generated file missing", **base)
    if not rp or not rp.exists():
        return ContaminationScore(codebleu=None, available=False, detail="reference file missing", **base)
    try:
        from codebleu import calc_codebleu
    except Exception as exc:  # noqa: BLE001
        return ContaminationScore(codebleu=None, available=False,
                                  detail=f"codebleu unavailable: {type(exc).__name__}", **base)
    try:
        res = calc_codebleu([rp.read_text(errors="ignore")], [gp.read_text(errors="ignore")], lang=lang)
    except Exception as exc:  # noqa: BLE001 — parser/tree-sitter gaps degrade, never crash a run
        return ContaminationScore(codebleu=None, available=False,
                                  detail=f"codebleu error: {type(exc).__name__}: {exc}"[:160], **base)
    comps = {k: round(float(v), 4) for k, v in res.items() if k != "codebleu"}
    return ContaminationScore(codebleu=round(float(res["codebleu"]), 4), available=True,
                              components=comps, **base)


# Online Boutique: SDK service -> (language_id, source extension). Matches the upstream
# language assignments the benchmark mirrors.
OB_SERVICE_LANG = {
    "adservice": ("java", ".java"), "cartservice": ("csharp", ".cs"),
    "checkoutservice": ("go", ".go"), "productcatalogservice": ("go", ".go"),
    "shippingservice": ("go", ".go"), "currencyservice": ("nodejs", ".js"),
    "paymentservice": ("nodejs", ".js"), "emailservice": ("python", ".py"),
    "recommendationservice": ("python", ".py"),
}


def score_run(run_dir, reference_root, *, services: Optional[Dict] = None) -> Dict:
    """Score every generated cell in a benchmark run's ``sandboxes/`` against the canonical
    Online Boutique source under ``reference_root``. Returns per-cell scores + per-model means.
    Pure read, $0, no execution."""
    run_dir, reference_root = Path(run_dir), Path(reference_root)
    services = services or OB_SERVICE_LANG
    sandboxes = run_dir / "sandboxes"
    cells: List[ContaminationScore] = []

    # Discover (service, model, rep) from sandbox dir names: "<service>-<model _>-r<rep>".
    for sb in sorted(p for p in sandboxes.glob("*-r*") if p.is_dir()) if sandboxes.exists() else []:
        name = sb.name
        svc = next((s for s in services if name.startswith(s + "-")), None)
        if svc is None:
            continue
        rest = name[len(svc) + 1:]
        if "-r" not in rest:
            continue
        model = rest.rsplit("-r", 1)[0].replace("_", ":", 1)
        lang, ext = services[svc]
        ref = resolve_main_source(reference_root / svc, ext)
        gen = resolve_main_source(sb, ext)
        sc = score_pair(gen, ref, lang)
        sc.service, sc.model = svc, model
        cells.append(sc)

    by_model: Dict[str, List[float]] = {}
    for c in cells:
        if c.available and c.codebleu is not None:
            by_model.setdefault(c.model, []).append(c.codebleu)
    model_mean = {m: round(sum(v) / len(v), 4) for m, v in by_model.items() if v}

    return {
        "reference_root": str(reference_root),
        "n_cells": len(cells),
        "n_scored": sum(1 for c in cells if c.available),
        "model_mean_codebleu": dict(sorted(model_mean.items(), key=lambda kv: -kv[1])),
        "cells": [c.to_dict() for c in cells],
    }
