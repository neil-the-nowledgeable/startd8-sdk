"""Evaluation scoring rubric for Micro Prime output quality.

5-dimension quality scoring:
  - syntax:   0/1  — AST parses successfully
  - imports:  0/1  — no missing/hallucinated imports
  - lint:     0/1  — no ruff errors (E/F codes)
  - semantic: 0-3  — structural match to reference implementation
  - fill_rate: 0.0-1.0 — fraction of stubs filled (file-whole only)
"""

from __future__ import annotations

import ast
import subprocess
import textwrap
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ElementScore:
    """Quality score for a single generated element."""

    element_name: str
    file_path: str
    tier: str

    # Individual dimensions
    syntax: int = 0  # 0 or 1
    imports: int = 0  # 0 or 1
    lint: int = 0  # 0 or 1
    semantic: int = 0  # 0-3
    fill_rate: float = 1.0  # 0.0-1.0 (1.0 for element-level, computed for file-whole)

    # Metadata
    repair_steps_applied: list[str] = field(default_factory=list)
    repair_recovered: bool = False
    generation_time_ms: float = 0.0
    error: Optional[str] = None

    @property
    def composite_score(self) -> float:
        """Weighted composite: syntax(20) + imports(15) + lint(15) + semantic(50)."""
        return (
            self.syntax * 0.20
            + self.imports * 0.15
            + self.lint * 0.15
            + (self.semantic / 3.0) * 0.50
        )

    @property
    def pass_threshold(self) -> bool:
        """Element passes if syntax=1 AND semantic >= 2."""
        return self.syntax == 1 and self.semantic >= 2


@dataclass
class FileScore:
    """Quality score for a file-whole generation."""

    file_path: str
    element_scores: list[ElementScore] = field(default_factory=list)
    fill_rate: float = 0.0
    total_elements: int = 0
    filled_elements: int = 0

    @property
    def composite_score(self) -> float:
        if not self.element_scores:
            return 0.0
        return sum(s.composite_score for s in self.element_scores) / len(
            self.element_scores
        )


@dataclass
class CorpusReport:
    """Aggregated report over an entire golden corpus run."""

    run_id: str
    model: str
    element_scores: list[ElementScore] = field(default_factory=list)
    file_scores: list[FileScore] = field(default_factory=list)

    @property
    def total_elements(self) -> int:
        return len(self.element_scores)

    @property
    def syntax_rate(self) -> float:
        if not self.element_scores:
            return 0.0
        return sum(s.syntax for s in self.element_scores) / len(self.element_scores)

    @property
    def import_rate(self) -> float:
        if not self.element_scores:
            return 0.0
        return sum(s.imports for s in self.element_scores) / len(self.element_scores)

    @property
    def lint_rate(self) -> float:
        if not self.element_scores:
            return 0.0
        return sum(s.lint for s in self.element_scores) / len(self.element_scores)

    @property
    def mean_semantic(self) -> float:
        if not self.element_scores:
            return 0.0
        return sum(s.semantic for s in self.element_scores) / len(self.element_scores)

    @property
    def mean_composite(self) -> float:
        if not self.element_scores:
            return 0.0
        return sum(s.composite_score for s in self.element_scores) / len(
            self.element_scores
        )

    @property
    def pass_rate(self) -> float:
        if not self.element_scores:
            return 0.0
        return sum(1 for s in self.element_scores if s.pass_threshold) / len(
            self.element_scores
        )

    @property
    def repair_rate(self) -> float:
        if not self.element_scores:
            return 0.0
        return sum(
            1 for s in self.element_scores if len(s.repair_steps_applied) > 0
        ) / len(self.element_scores)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "model": self.model,
            "total_elements": self.total_elements,
            "syntax_rate": round(self.syntax_rate, 4),
            "import_rate": round(self.import_rate, 4),
            "lint_rate": round(self.lint_rate, 4),
            "mean_semantic": round(self.mean_semantic, 2),
            "mean_composite": round(self.mean_composite, 4),
            "pass_rate": round(self.pass_rate, 4),
            "repair_rate": round(self.repair_rate, 4),
            "elements": [
                {
                    "name": s.element_name,
                    "file": s.file_path,
                    "tier": s.tier,
                    "syntax": s.syntax,
                    "imports": s.imports,
                    "lint": s.lint,
                    "semantic": s.semantic,
                    "composite": round(s.composite_score, 4),
                    "repair_steps": s.repair_steps_applied,
                    "repair_recovered": s.repair_recovered,
                    "generation_time_ms": round(s.generation_time_ms, 1),
                    "error": s.error,
                }
                for s in self.element_scores
            ],
        }


# ── Scoring Functions ──────────────────────────────────────────────────


def score_syntax(code: str) -> int:
    """Score 1 if code parses as valid Python AST, 0 otherwise."""
    try:
        ast.parse(code)
        return 1
    except SyntaxError:
        return 0


def score_imports(code: str, expected_imports: list[str]) -> int:
    """Score 1 if no import errors detected, 0 otherwise.

    Checks:
    - No hallucinated imports (imports not in expected list)
    - Uses AST to extract actual import statements from generated code
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return 0

    actual_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                actual_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                actual_modules.add(node.module.split(".")[0])

    expected_set = {m.split(".")[0] for m in expected_imports}

    # Allow stdlib imports unconditionally
    stdlib_modules = {
        "os", "sys", "json", "logging", "typing", "pathlib", "abc",
        "dataclasses", "enum", "functools", "collections", "re",
        "datetime", "time", "copy", "io", "math", "hashlib",
        "itertools", "contextlib", "textwrap", "inspect", "ast",
        "unittest", "pytest", "warnings", "subprocess", "tempfile",
        "shutil", "uuid", "socket", "http", "urllib", "threading",
        "asyncio", "concurrent", "signal", "traceback", "importlib",
        "__future__",
    }

    hallucinated = actual_modules - expected_set - stdlib_modules
    return 0 if hallucinated else 1


def score_lint(code: str) -> int:
    """Score 1 if ruff reports no E/F errors, 0 otherwise.

    Falls back to 1 if ruff is not installed (avoid hard dependency).
    """
    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "E,F", "--quiet", "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return 1 if result.returncode == 0 else 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 1


def score_semantic(generated: str, reference: str) -> int:
    """Score 0-3 based on structural similarity to reference implementation.

    0 = No meaningful code (empty, only pass/raise, or syntax error)
    1 = Has code but wrong structure (missing key constructs)
    2 = Correct structure, minor differences (variable names, style)
    3 = Functionally equivalent to reference
    """
    if not generated or not generated.strip():
        return 0

    try:
        gen_tree = ast.parse(generated)
    except SyntaxError:
        return 0

    try:
        ref_tree = ast.parse(reference)
    except SyntaxError:
        # Can't compare if reference doesn't parse
        return 0

    gen_body = _extract_meaningful_nodes(gen_tree)
    ref_body = _extract_meaningful_nodes(ref_tree)

    # Special case: constant/variable-only files — compare normalized source
    if not gen_body and not ref_body:
        # Both have no meaningful nodes — likely constant assignments
        # Compare normalized text (strip whitespace, comments)
        gen_norm = _normalize_source(generated)
        ref_norm = _normalize_source(reference)
        if gen_norm == ref_norm:
            return 3
        # Check if same variable names are assigned
        gen_names = _extract_assign_names(gen_tree)
        ref_names = _extract_assign_names(ref_tree)
        if gen_names and gen_names == ref_names:
            return 2
        return 1 if gen_names else 0

    # Score 0: no meaningful code
    if not gen_body:
        return 0

    # Extract structural features
    gen_features = _extract_features(gen_tree)
    ref_features = _extract_features(ref_tree)

    # Score 3: high structural match
    match_ratio = _feature_overlap(gen_features, ref_features)
    if match_ratio >= 0.80:
        return 3

    # Score 2: moderate structural match
    if match_ratio >= 0.50:
        return 2

    # Score 1: has code but low match
    return 1


def score_fill_rate(
    generated_code: str,
    total_stubs: int,
) -> float:
    """Compute fill rate for file-whole generation.

    Returns fraction of stubs that were replaced with real implementations.
    """
    if total_stubs == 0:
        return 1.0

    remaining_stubs = generated_code.count("raise NotImplementedError")
    filled = total_stubs - remaining_stubs
    return max(0.0, min(1.0, filled / total_stubs))


def score_element(
    generated_code: str,
    reference_code: str,
    element_name: str,
    file_path: str,
    tier: str,
    expected_imports: list[str],
    repair_steps: list[str] | None = None,
    repair_recovered: bool = False,
    generation_time_ms: float = 0.0,
) -> ElementScore:
    """Score a single generated element against its reference."""
    if not generated_code or not generated_code.strip():
        return ElementScore(
            element_name=element_name,
            file_path=file_path,
            tier=tier,
            error="empty_output",
        )

    return ElementScore(
        element_name=element_name,
        file_path=file_path,
        tier=tier,
        syntax=score_syntax(generated_code),
        imports=score_imports(generated_code, expected_imports),
        lint=score_lint(generated_code),
        semantic=score_semantic(generated_code, reference_code),
        repair_steps_applied=repair_steps or [],
        repair_recovered=repair_recovered,
        generation_time_ms=generation_time_ms,
    )


# ── Internal Helpers ───────────────────────────────────────────────────


def _extract_meaningful_nodes(tree: ast.AST) -> list[ast.AST]:
    """Extract non-trivial nodes (skip pass, raise NotImplementedError, docstrings)."""
    meaningful = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            meaningful.append(node)
        elif isinstance(node, ast.Assign):
            meaningful.append(node)
        elif isinstance(node, ast.Return):
            # Skip bare returns
            if node.value is not None:
                meaningful.append(node)
    return meaningful


def _extract_features(tree: ast.AST) -> set[str]:
    """Extract a set of structural feature strings for comparison."""
    features: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            features.add(f"def:{node.name}")
            features.add(f"params:{len(node.args.args)}")
            if node.returns:
                features.add(f"returns:{ast.dump(node.returns)}")
        elif isinstance(node, ast.AsyncFunctionDef):
            features.add(f"async_def:{node.name}")
            features.add(f"params:{len(node.args.args)}")
        elif isinstance(node, ast.ClassDef):
            features.add(f"class:{node.name}")
            for base in node.bases:
                features.add(f"base:{ast.dump(base)}")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    features.add(f"assign:{target.id}")
                elif isinstance(target, ast.Attribute):
                    features.add(f"attr:{node_attr_chain(target)}")
        elif isinstance(node, ast.Return) and node.value is not None:
            features.add(f"return:{type(node.value).__name__}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                features.add(f"call:{node.func.id}")
            elif isinstance(node.func, ast.Attribute):
                features.add(f"call:{node.func.attr}")
        elif isinstance(node, ast.If):
            features.add("if_branch")
        elif isinstance(node, ast.For):
            features.add("for_loop")
        elif isinstance(node, ast.While):
            features.add("while_loop")
        elif isinstance(node, ast.With):
            features.add("with_block")
        elif isinstance(node, ast.Try):
            features.add("try_block")
    return features


def node_attr_chain(node: ast.Attribute) -> str:
    """Build dotted attribute chain like 'self.x'."""
    parts = [node.attr]
    current = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _feature_overlap(gen: set[str], ref: set[str]) -> float:
    """Compute Jaccard-like overlap between feature sets."""
    if not ref:
        return 1.0 if not gen else 0.0
    intersection = gen & ref
    union = gen | ref
    if not union:
        return 1.0
    return len(intersection) / len(union)


def _normalize_source(code: str) -> str:
    """Normalize source for constant comparison (strip comments, whitespace)."""
    lines = []
    for line in code.splitlines():
        stripped = line.split("#")[0].strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def _extract_assign_names(tree: ast.AST) -> set[str]:
    """Extract top-level assignment target names."""
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names
