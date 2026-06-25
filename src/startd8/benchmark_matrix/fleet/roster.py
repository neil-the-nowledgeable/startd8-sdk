"""Round-3 finalist roster (M6 wiring) — resolve which finalists to score and where their fleets live.

A finalist is one model whose OWN 9-service fleet is scored end-to-end. Its services are built into a
per-model image namespace (``r3/<model>/<svc>:<lang>``) so distinct finalists don't collide; the
reference fleet uses the bare ``r3`` namespace. The roster is a small YAML the operator hand-picks
(advisory, FR-21 — no auto-orchestrator).

Roster YAML shape:
    finalists:
      - model: claude-opus-4-8
        image_namespace: r3/claude-opus-4-8      # optional; defaults to r3/<model>
      - model: reference
        image_namespace: r3                       # the SDK reference fleet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class FinalistSpec:
    """One finalist: a model id + the image namespace its 9-service fleet was built into."""
    model: str
    image_namespace: str

    @classmethod
    def of(cls, model: str, image_namespace: str | None = None) -> "FinalistSpec":
        # default each model to its own namespace; the literal "reference" maps to the bare r3 fleet.
        if image_namespace is None:
            image_namespace = "r3" if model == "reference" else f"r3/{model}"
        return cls(model=model, image_namespace=image_namespace)


def reference_roster() -> list[FinalistSpec]:
    """The single SDK-reference finalist (the bare r3 fleet) — used for the harness self-test."""
    return [FinalistSpec.of("reference")]


def load_roster(path: str | Path) -> list[FinalistSpec]:
    """Load a finalist roster from a YAML file. Raises on a malformed roster (never silently empty)."""
    doc = yaml.safe_load(Path(path).read_text()) or {}
    raw = doc.get("finalists")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"roster {path}: expected a non-empty 'finalists:' list")
    specs: list[FinalistSpec] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict) or "model" not in entry:
            raise ValueError(f"roster {path}: each finalist needs a 'model' (got {entry!r})")
        model = str(entry["model"])
        if model in seen:
            raise ValueError(f"roster {path}: duplicate finalist {model!r}")
        seen.add(model)
        specs.append(FinalistSpec.of(model, entry.get("image_namespace")))
    return specs
