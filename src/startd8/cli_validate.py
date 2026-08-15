"""`startd8 validate` — run the cross-language semantic validators; emit text / JSON / SARIF.

Walks a file or directory, routes each source file to its language's deterministic semantic
checker (`validators/*_semantic_checks.py` — Python/Go/Node/Java/C#), and reports the findings.
With ``--format sarif`` the findings render as a SARIF 2.1.0 document (via
``coverage_map.render_sarif_from_findings``) — the same GitHub-code-scanning / IDE format the
coverage analyzer emits, so requirement-doc, coverage, and code-quality findings all speak SARIF.

No LLM: these are pure deterministic AST/text checks. Exit 0 = no error-severity findings, 1 =
at least one error-severity finding, 2 = usage/path error. (Warnings/advisories never fail the exit.)
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Callable, Iterable, Optional

import typer
from rich.console import Console

from .coverage_map import render_sarif_from_findings
from .validators.csharp_semantic_checks import run_csharp_semantic_checks
from .validators.go_semantic_checks import run_go_semantic_checks
from .validators.java_semantic_checks import run_java_semantic_checks
from .validators.nodejs_semantic_checks import run_nodejs_semantic_checks
from .validators.semantic_checks import SemanticIssue, run_semantic_checks

console = Console()

_EXIT_OK = 0
_EXIT_FINDINGS = 1
_EXIT_ERROR = 2

#: source extension → its semantic checker (str source, file_path) -> list[SemanticIssue].
_CHECKERS: dict[str, Callable[..., list[SemanticIssue]]] = {
    ".py": run_semantic_checks,
    ".go": run_go_semantic_checks,
    ".java": run_java_semantic_checks,
    ".js": run_nodejs_semantic_checks,
    ".mjs": run_nodejs_semantic_checks,
    ".cjs": run_nodejs_semantic_checks,
    ".cs": run_csharp_semantic_checks,
}

#: path segments that exclude a file from the walk (dependency / build output / VCS).
_EXCLUDE_SEG = frozenset({
    "node_modules", "vendor", "dist", "build", "target", ".git", ".venv",
    "__pycache__", "obj", "bin",
})

_VALID_FORMATS = ("text", "json", "sarif")


def _iter_source_files(root: Path) -> Iterable[Path]:
    """Yield checkable source files under *root* (a file yields itself), applying exclusions."""
    if root.is_file():
        if root.suffix in _CHECKERS:
            yield root
        return
    for p in sorted(root.rglob("*")):
        if p.suffix not in _CHECKERS or not p.is_file():
            continue
        if any(seg in _EXCLUDE_SEG for seg in p.parts):
            continue
        yield p


def _collect(root: Path) -> list[SemanticIssue]:
    """Run the matching checker on every source file under *root*; return all findings.

    A file we cannot read or that a checker chokes on is skipped (a corpus we can't parse is not a
    validation failure) — the checkers themselves already return ``[]`` on unparseable input.
    """
    issues: list[SemanticIssue] = []
    for f in _iter_source_files(root):
        checker = _CHECKERS[f.suffix]
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            found = checker(src, file_path=str(f))
        except Exception:  # a checker bug must not abort the whole scan
            continue
        issues.extend(found)
    return issues


def _emit_text(issues: list[SemanticIssue], root: Path) -> None:
    if not issues:
        console.print(f"[green]✓[/green] no semantic findings under [bold]{root}[/bold]")
        return
    errors = sum(1 for i in issues if i.severity == "error")
    for i in sorted(issues, key=lambda x: (x.file_path or "", x.line or 0, x.check)):
        loc = f"{i.file_path}:{i.line}" if i.line else (i.file_path or "?")
        colour = "red" if i.severity == "error" else "yellow"
        console.print(f"{loc}  [{colour}]{i.severity}[/{colour}]  [bold]{i.check}[/bold]  {i.message}")
    console.print(
        f"\n[bold]{len(issues)}[/bold] finding(s): "
        f"[red]{errors} error[/red], {len(issues) - errors} warning"
    )


def validate_command(
    path: Path = typer.Argument(..., exists=True, help="a source file or directory to validate"),
    fmt: str = typer.Option("text", "--format", "-f", help="output format: text | json | sarif"),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="write output to a file (default stdout)"),
    tool_name: str = typer.Option("startd8-semantic", "--tool-name", help="SARIF tool.driver.name"),
) -> None:
    """Run cross-language semantic validators over PATH; emit findings as text, JSON, or SARIF.

    Routes each source file to its language checker (Python/Go/Node/Java/C#). Exit 1 if any
    error-severity finding is present, else 0.
    """
    if fmt not in _VALID_FORMATS:
        console.print(f"[red]error[/red]: --format must be one of {', '.join(_VALID_FORMATS)}")
        raise typer.Exit(_EXIT_ERROR)

    issues = _collect(path)

    if fmt == "sarif":
        payload = json.dumps(
            render_sarif_from_findings(issues, tool_name=tool_name, corpus=str(path)),
            indent=2, ensure_ascii=False,
        ) + "\n"
    elif fmt == "json":
        payload = json.dumps(
            [dataclasses.asdict(i) for i in issues], indent=2, ensure_ascii=False, sort_keys=True,
        ) + "\n"
    else:  # text
        payload = None

    if payload is not None:
        if out is not None:
            out.write_text(payload, encoding="utf-8")
            console.print(f"wrote {fmt} findings → [bold]{out}[/bold] ({len(issues)} finding(s))")
        else:
            # raw payload to stdout (machine-consumable) — no Rich markup
            typer.echo(payload, nl=False)
    else:
        _emit_text(issues, path)
        if out is not None:
            console.print("[yellow]note[/yellow]: --out is ignored for --format text")

    raise typer.Exit(_EXIT_FINDINGS if any(i.severity == "error" for i in issues) else _EXIT_OK)
