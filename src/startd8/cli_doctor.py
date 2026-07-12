"""FR-E10 — ``startd8 doctor``: a fast environment self-check.

Motivated by the recurring **venv-vs-global staleness** trap: a globally-installed ``startd8`` on
``PATH`` can be stale while an editable venv install tracks the live source, so a new flag/command
"doesn't exist." Doctor surfaces which ``startd8`` you're actually running (editable vs installed),
whether a nearby editable venv would be newer, plus the basics (Python, provider keys, doppler).
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path


def run_doctor(console) -> int:
    """Print a diagnostic report. Returns an exit code (0 = no blocking problems; 1 = a warning worth
    acting on, e.g. a likely-stale install or no provider key)."""
    import startd8

    warnings: list[str] = []
    console.print("[bold]startd8 doctor[/bold]")

    # --- which startd8 am I running, and is it editable (live source) or installed (maybe stale)? ---
    version = getattr(startd8, "__version__", "?")
    pkg = Path(startd8.__file__).resolve()
    installed = "site-packages" in pkg.parts
    kind = "installed" if installed else "editable (live source)"
    root = pkg.parent.parent if not installed else pkg.parent
    console.print(f"  startd8 [cyan]{version}[/cyan] — {kind} @ {root}")

    which = shutil.which("startd8")
    console.print(f"  `startd8` on PATH: {which or '[yellow](not found)[/yellow]'}")

    # The trap: running an INSTALLED startd8 while an editable venv exists nearby → likely stale.
    if installed:
        for cand in (Path.cwd() / ".venv" / "bin" / "startd8",
                     Path(sys.prefix) / "bin" / "startd8"):
            if cand.exists() and str(cand) != (which or ""):
                warnings.append(
                    f"you're running an INSTALLED startd8, but an editable venv exists at {cand} — "
                    "if a new flag/command seems missing, run that one (it tracks the live source)."
                )
                break

    # --- Python + interpreter ---
    console.print(f"  python [cyan]{platform.python_version()}[/cyan] @ {sys.executable}")

    # --- provider keys (names only — never values) ---
    key_names = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
                 "GEMINI_API_KEY", "MISTRAL_API_KEY")
    present = [k for k in key_names if os.environ.get(k)]
    if present:
        console.print(f"  provider keys set: [green]{', '.join(present)}[/green]")
    else:
        console.print("  provider keys set: [yellow]none[/yellow]")
        warnings.append("no provider API key in env — the agentic chat/concierge needs one "
                        "(set ANTHROPIC_API_KEY, or use `doppler run -- …`).")

    # --- doppler (the repo's secrets injector) ---
    console.print(f"  doppler CLI: {'[green]available[/green]' if shutil.which('doppler') else '[dim]not found[/dim]'}")

    # --- summary ---
    if warnings:
        console.print("")
        for w in warnings:
            console.print(f"  [yellow]⚠[/yellow] {w}")
        return 1
    console.print("  [green]✓ no problems detected[/green]")
    return 0
