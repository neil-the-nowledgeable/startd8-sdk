"""FR-SAP-1 — assumption extraction from the *structured* ForwardManifest.

Per requirements §0.9: assumptions are read from the typed manifest
(``ForwardFileSpec.imports`` / ``.elements`` / ``InterfaceContract``), **never** by
re-parsing rendered skeleton text. The rendered ``skeleton_sources`` are consumed only by
the pilot bore (``sapper.pilot_bore``).

The extractor enumerates the plan's *claims*; the bore / convention-route / per-element
validators turn (a subset of) them into verdicts. Extraction here intentionally does **not**
pre-classify ``module_source`` vs ``import_availability`` — that distinction is refined by the
bore from the actual typecheck diagnostic (module-missing vs name-missing).
"""

from __future__ import annotations

from typing import List

from startd8.utils.code_manifest import ElementKind

from .models import Assumption, AssumptionKind, ValidatorClass

_CALLABLE_KINDS = {
    ElementKind.FUNCTION,
    ElementKind.ASYNC_FUNCTION,
    ElementKind.METHOD,
    ElementKind.ASYNC_METHOD,
    ElementKind.PROPERTY,
}


def extract_assumptions(manifest) -> List[Assumption]:
    """Enumerate the assumptions a ForwardManifest makes about the existing codebase.

    Returns import-availability and interface-signature assumptions (the bore's domain),
    plus identity-collision candidates for the per-element rules. ``manifest`` is a
    ``startd8.forward_manifest.ForwardManifest``.
    """
    out: List[Assumption] = []
    for path, spec in sorted(manifest.file_specs.items()):
        # --- imports → existence assumptions (bore-checked) ---
        for imp in spec.imports:
            module = imp.module
            names = list(imp.names) if imp.names else []
            if names:
                for name in names:
                    out.append(
                        Assumption(
                            id=f"{path}::import::{module}.{name}",
                            kind=AssumptionKind.IMPORT_AVAILABILITY,
                            claim=f"`from {module} import {name}` resolves",
                            validator_class=ValidatorClass.PILOT_BORE,
                            source_ref=f"file_spec:{path}#import",
                            file=path,
                            symbol=f"{module}.{name}",
                        )
                    )
            else:
                out.append(
                    Assumption(
                        id=f"{path}::import::{module}",
                        kind=AssumptionKind.IMPORT_AVAILABILITY,
                        claim=f"`import {module}` resolves",
                        validator_class=ValidatorClass.PILOT_BORE,
                        source_ref=f"file_spec:{path}#import",
                        file=path,
                        symbol=module,
                    )
                )

        # --- callable elements → interface-signature assumptions ---
        for el in spec.elements:
            if el.kind in _CALLABLE_KINDS:
                out.append(
                    Assumption(
                        id=f"{path}::sig::{el.parent_class + '.' if el.parent_class else ''}{el.name}",
                        kind=AssumptionKind.INTERFACE_SIGNATURE,
                        claim=f"`{el.name}` has the declared signature",
                        validator_class=ValidatorClass.PILOT_BORE,
                        source_ref=f"file_spec:{path}#element",
                        file=path,
                        symbol=el.name,
                    )
                )
    return out


def shared_files(manifest) -> set:
    """Files imported by ≥2 feature files in the plan — used to escalate avoidable cost.

    A heuristic over ``ForwardImportSpec.module`` → candidate file path: any module that
    matches another file_spec's path (module-as-file) and is referenced by ≥2 files.
    """
    # module path (dotted) → set of importing files
    importers: dict[str, set] = {}
    file_modules = {p[:-3].replace("/", "."): p for p in manifest.file_specs if p.endswith(".py")}
    for path, spec in manifest.file_specs.items():
        for imp in spec.imports:
            if imp.module in file_modules:
                importers.setdefault(file_modules[imp.module], set()).add(path)
    return {f for f, imps in importers.items() if len(imps) >= 2}
