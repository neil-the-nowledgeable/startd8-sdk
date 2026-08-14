"""Element-level evidence checks for a persisted :class:`ForwardManifest`.

The normal Forward Manifest path validates a draft before it is merged.  This
module provides the narrower, read-only primitive needed by evidence consumers:
given source bytes from an immutable ``git:<sha>:<path>`` locator, check only the
elements prescribed for that file.

The result is verification evidence, not delivery health.  Callers must keep the
commit/digest check as the lower rung and decide how to present a violation or an
unavailable parser in their own health vocabulary.
"""

from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from startd8.forward_manifest import ForwardFileSpec, ForwardManifest
from startd8.forward_manifest_validator import (
    severity_for_parser_tier,
    validate_forward_manifest,
)
from startd8.languages.manifest_adapter import build_multilang_file_manifest
from startd8.utils.manifest_registry import ManifestRegistry


_COARSE_KIND_COMPATIBILITY = {
    # Design tables often omit modifiers that the source parser can identify exactly.
    # Direction matters: an explicit async/property/struct promise remains exact.
    "function": {"function", "async_function"},
    "method": {"method", "async_method", "property"},
    "class": {"class", "interface", "record", "struct"},
    # Data-member classification is scope/name-heuristic in several parsers.
    "constant": {"constant", "field", "variable"},
    "field": {"constant", "field", "variable"},
    "variable": {"constant", "field", "variable"},
    # The advisory Go adapter currently projects a native struct as `class`.
    "struct": {"class", "struct"},
}


class ElementVerificationStatus(str, Enum):
    """Outcome of checking one immutable source blob against its file spec."""

    VERIFIED = "verified"
    VIOLATED = "violated"
    NOT_APPLICABLE = "not-applicable"
    VERIFICATION_UNAVAILABLE = "verification-unavailable"


class ElementExpectation(BaseModel):
    """One element shape promised by the forward file specification."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: str
    parent_class: Optional[str] = None


class ElementVerificationIssue(BaseModel):
    """Serializable projection of a Forward Manifest contract violation."""

    model_config = ConfigDict(frozen=True)

    contract_id: str
    violation_type: str
    expected: str
    actual: Optional[str] = None
    file_path: Optional[str] = None
    severity: str
    tier: Optional[str] = None


class ElementVerificationResult(BaseModel):
    """Structured, health-neutral result for one evidence blob."""

    model_config = ConfigDict(frozen=True)

    status: ElementVerificationStatus
    scope: Literal["file"] = "file"
    file_path: str
    manifest_schema_version: Optional[str] = None
    manifest_file_path: Optional[str] = None
    parser_tier: Optional[str] = None
    finding_severity: Optional[Literal["error", "warning"]] = None
    expected_elements: list[ElementExpectation] = Field(default_factory=list)
    issues: list[ElementVerificationIssue] = Field(default_factory=list)
    reason: Optional[str] = None


def _normalise_path(value: str) -> str:
    """Normalize separators and a leading ``./`` without making a path absolute."""

    raw = str(value or "").strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return PurePosixPath(raw).as_posix()


def _is_safe_repo_path(value: str) -> bool:
    """Whether a normalized path is non-empty and cannot escape a repo root."""

    path = PurePosixPath(value)
    return (
        value not in {"", "."}
        and not path.is_absolute()
        and ".." not in path.parts
        and not (len(value) >= 3 and value[1:3] == ":/")
    )


def _path_matches(requested: str, candidate: str) -> bool:
    """Whether two repo-relative paths are exact or unambiguously suffix-related."""

    return (
        requested == candidate
        or candidate.endswith("/" + requested)
    )


def _matching_file_specs(
    manifest: ForwardManifest,
    file_path: str,
) -> list[tuple[str, ForwardFileSpec]]:
    requested = _normalise_path(file_path)
    exact: list[tuple[str, ForwardFileSpec]] = []
    suffix: list[tuple[str, ForwardFileSpec]] = []

    for key, spec in manifest.file_specs.items():
        aliases = {
            alias
            for alias in (_normalise_path(key), _normalise_path(spec.file))
            if _is_safe_repo_path(alias)
        }
        if requested in aliases:
            exact.append((key, spec))
        elif any(_path_matches(requested, alias) for alias in aliases):
            suffix.append((key, spec))

    return exact or suffix


def _unsafe_matching_paths(manifest: ForwardManifest, requested: str) -> list[str]:
    """Return unsafe manifest aliases that otherwise look like the requested file."""

    unsafe: set[str] = set()
    for key, spec in manifest.file_specs.items():
        for raw in (key, spec.file):
            candidate = _normalise_path(raw)
            if not _is_safe_repo_path(candidate) and (
                candidate == requested or candidate.endswith("/" + requested)
            ):
                unsafe.add(str(raw))
    return sorted(unsafe)


def _flatten_actual_elements(elements):
    """Yield parsed elements, including nested members and class variables."""

    for element in elements:
        yield element
        yield from _flatten_actual_elements(getattr(element, "children", ()) or ())
        yield from _flatten_actual_elements(
            getattr(element, "class_variables", ()) or ()
        )


def _kind_matches(expected_kind, actual_kind) -> bool:
    """Match a coarse design kind to a parser's more precise source kind."""

    expected = expected_kind.value
    actual = actual_kind.value
    return actual in _COARSE_KIND_COMPATIBILITY.get(expected, {expected})


def verify_forward_manifest_elements(
    manifest: ForwardManifest,
    file_path: str,
    source: Union[str, bytes],
) -> ElementVerificationResult:
    """Check expected elements for one immutable source blob.

    Matching is exact first, then path-suffix based to accommodate manifests
    persisted with a project-directory prefix.  Ambiguous matches and parser
    degradation are explicit ``verification-unavailable`` outcomes; they never
    become an empty-list success.

    Imports, dependencies, and project-wide ``InterfaceContract`` entries are
    intentionally excluded.  A git evidence locator proves one file blob, so
    only that file's element inventory is attributable at this boundary.
    Accordingly, the result is stamped ``scope="file"``; callers loading a full
    persisted manifest must not relabel a path match as requirement-specific.

    Args:
        manifest: The persisted design-time Forward Manifest.
        file_path: Repo-relative path from the immutable evidence locator.
        source: Source text or raw git-blob bytes.

    Returns:
        A structured result that callers can serialize with
        ``model_dump(mode="json")``.
    """

    requested = _normalise_path(file_path)
    schema_version = str(manifest.schema_version or "")
    result_base = {
        "file_path": requested,
        "manifest_schema_version": schema_version,
    }
    if schema_version.split(".", 1)[0] != "1":
        return ElementVerificationResult(
            status=ElementVerificationStatus.VERIFICATION_UNAVAILABLE,
            reason=f"unsupported_manifest_schema: {schema_version or '<empty>'}",
            **result_base,
        )
    if not _is_safe_repo_path(requested):
        return ElementVerificationResult(
            status=ElementVerificationStatus.VERIFICATION_UNAVAILABLE,
            reason="invalid_file_path",
            **result_base,
        )
    matches = _matching_file_specs(manifest, requested)
    if not matches:
        unsafe_matches = _unsafe_matching_paths(manifest, requested)
        if unsafe_matches:
            return ElementVerificationResult(
                status=ElementVerificationStatus.VERIFICATION_UNAVAILABLE,
                reason="invalid_manifest_file_path: " + ", ".join(unsafe_matches),
                **result_base,
            )
        return ElementVerificationResult(
            status=ElementVerificationStatus.NOT_APPLICABLE,
            reason="file_spec_not_found",
            **result_base,
        )
    if len(matches) > 1:
        candidates = ", ".join(sorted(key for key, _ in matches))
        return ElementVerificationResult(
            status=ElementVerificationStatus.VERIFICATION_UNAVAILABLE,
            reason=f"ambiguous_file_spec: {candidates}",
            **result_base,
        )

    manifest_path, spec = matches[0]
    expected = [
        ElementExpectation(
            name=element.name,
            kind=element.kind.value,
            parent_class=element.parent_class,
        )
        for element in spec.elements
    ]
    if not expected:
        return ElementVerificationResult(
            status=ElementVerificationStatus.NOT_APPLICABLE,
            manifest_file_path=manifest_path,
            reason="no_elements_declared",
            **result_base,
        )

    if isinstance(source, bytes):
        try:
            source_text = source.decode("utf-8")
        except UnicodeDecodeError:
            return ElementVerificationResult(
                status=ElementVerificationStatus.VERIFICATION_UNAVAILABLE,
                manifest_file_path=manifest_path,
                expected_elements=expected,
                reason="source_not_utf8",
                    **result_base,
            )
    else:
        source_text = source

    try:
        actual = build_multilang_file_manifest(requested, source_text)
    except Exception as exc:  # defensive boundary: evidence is an optional rung
        return ElementVerificationResult(
            status=ElementVerificationStatus.VERIFICATION_UNAVAILABLE,
            manifest_file_path=manifest_path,
            expected_elements=expected,
            reason=f"parser_error: {exc.__class__.__name__}",
            **result_base,
        )
    parser_tier = getattr(actual, "parser_tier", None)
    if parser_tier is None:
        return ElementVerificationResult(
            status=ElementVerificationStatus.VERIFICATION_UNAVAILABLE,
            manifest_file_path=manifest_path,
            expected_elements=expected,
            reason="parser_unavailable_or_unsupported",
            **result_base,
        )
    if getattr(actual, "errors", None):
        return ElementVerificationResult(
            status=ElementVerificationStatus.VERIFICATION_UNAVAILABLE,
            manifest_file_path=manifest_path,
            parser_tier=parser_tier,
            expected_elements=expected,
            reason="source_parse_error",
            **result_base,
        )

    # The immutable evidence path is the registry authority. Keep the raw manifest
    # key only as report provenance; benign aliases such as "./x" and "x\\y" must
    # not become a synthetic missing_file violation.
    registry_key = requested
    element_only_spec = spec.model_copy(
        update={"file": registry_key, "imports": [], "dependencies": None}
    )
    scoped_manifest = ForwardManifest(
        file_specs={registry_key: element_only_spec},
        contracts=[],
    )
    registry = ManifestRegistry(
        manifests={registry_key: actual.model_copy(update={"file": registry_key})}
    )
    try:
        violations = validate_forward_manifest(scoped_manifest, registry)
    except Exception as exc:  # do not let the optional rung destroy base evidence checks
        return ElementVerificationResult(
            status=ElementVerificationStatus.VERIFICATION_UNAVAILABLE,
            manifest_file_path=manifest_path,
            parser_tier=parser_tier,
            expected_elements=expected,
            reason=f"validator_error: {exc.__class__.__name__}",
            **result_base,
        )
    issues = [
        ElementVerificationIssue(
            contract_id=violation.contract_id,
            violation_type=violation.violation_type,
            expected=violation.expected,
            actual=violation.actual,
            file_path=violation.file_path,
            severity=violation.severity,
            tier=violation.tier,
        )
        for violation in violations
    ]

    # The legacy file-spec validator is name-only for most kinds. Evidence consumers
    # need the promised shape, so tighten kind and parent ownership at this new boundary.
    actual_elements = list(_flatten_actual_elements(actual.elements))
    existing_contract_ids = {issue.contract_id for issue in issues}
    strict_severity = severity_for_parser_tier(parser_tier)
    for expected_spec in spec.elements:
        base_contract_id = f"file_element:{registry_key}:{expected_spec.name}"
        if base_contract_id in existing_contract_ids:
            continue
        candidates = [
            element
            for element in actual_elements
            if element.name == expected_spec.name
        ]
        if not candidates:
            continue
        kind_matches = [
            element
            for element in candidates
            if _kind_matches(expected_spec.kind, element.kind)
        ]
        if not kind_matches:
            issues.append(
                ElementVerificationIssue(
                    contract_id=f"file_element_kind:{registry_key}:{expected_spec.name}",
                    violation_type="wrong_element_kind",
                    expected=(
                        f"Element `{expected_spec.name}` of kind "
                        f"`{expected_spec.kind.value}`"
                    ),
                    actual="Kinds: "
                    + ", ".join(sorted({element.kind.value for element in candidates})),
                    file_path=registry_key,
                    severity=strict_severity,
                    tier=parser_tier,
                )
            )
            continue
        if expected_spec.parent_class:
            expected_fqn = f"{expected_spec.parent_class}.{expected_spec.name}"
            if not any(
                element.fqn.split("@", 1)[0] == expected_fqn
                or element.fqn.split("@", 1)[0].endswith("." + expected_fqn)
                for element in kind_matches
            ):
                issues.append(
                    ElementVerificationIssue(
                        contract_id=(
                            f"file_element_parent:{registry_key}:{expected_spec.name}"
                        ),
                        violation_type="wrong_parent_class",
                        expected=f"Element `{expected_fqn}`",
                        actual="Owners: "
                        + ", ".join(sorted({element.fqn for element in kind_matches})),
                        file_path=registry_key,
                        severity=strict_severity,
                        tier=parser_tier,
                    )
                )

    finding_severity: Optional[Literal["error", "warning"]] = None
    if issues:
        finding_severity = (
            "error" if any(issue.severity == "error" for issue in issues) else "warning"
        )
    return ElementVerificationResult(
        status=(
            ElementVerificationStatus.VIOLATED
            if issues
            else ElementVerificationStatus.VERIFIED
        ),
        manifest_file_path=manifest_path,
        parser_tier=parser_tier,
        finding_severity=finding_severity,
        expected_elements=expected,
        issues=issues,
        **result_base,
    )


__all__ = [
    "ElementExpectation",
    "ElementVerificationIssue",
    "ElementVerificationResult",
    "ElementVerificationStatus",
    "verify_forward_manifest_elements",
]
