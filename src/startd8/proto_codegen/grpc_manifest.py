"""Parse ``grpc.yaml`` — opt-in manifest for proto skeleton generation."""

from __future__ import annotations

from typing import List, Tuple

import yaml

from .models import GrpcServiceSpec

_VALID_LANGS = frozenset({"python", "go"})


def parse_grpc_manifest(text: str) -> Tuple[GrpcServiceSpec, ...]:
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict):
        raise ValueError("grpc.yaml must be a mapping")
    unknown = set(data) - {"services"}
    if unknown:
        raise ValueError(f"grpc.yaml has unknown top-level keys {sorted(unknown)}")
    raw = data.get("services") or []
    if not isinstance(raw, list) or not raw:
        raise ValueError("grpc.yaml must declare at least one entry under `services`")
    specs: List[GrpcServiceSpec] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"grpc.yaml services[{idx}] must be a mapping")
        unknown_item = set(item) - {"proto", "service", "language", "out", "stub_module"}
        if unknown_item:
            raise ValueError(f"grpc.yaml services[{idx}] unknown keys {sorted(unknown_item)}")
        proto = item.get("proto")
        service = item.get("service")
        language = item.get("language")
        out = item.get("out")
        for key, val in (("proto", proto), ("service", service), ("language", language), ("out", out)):
            if not isinstance(val, str) or not val.strip():
                raise ValueError(f"grpc.yaml services[{idx}].{key} is required")
        language = language.lower()
        if language not in _VALID_LANGS:
            raise ValueError(
                f"grpc.yaml services[{idx}].language must be one of {sorted(_VALID_LANGS)}, got {language!r}"
            )
        stub = item.get("stub_module")
        if stub is not None and (not isinstance(stub, str) or not stub):
            raise ValueError(f"grpc.yaml services[{idx}].stub_module must be a non-empty string")
        specs.append(
            GrpcServiceSpec(
                proto=proto.strip(),
                service=service.strip(),
                language=language,
                out=out.strip(),
                stub_module=stub.strip() if isinstance(stub, str) else None,
            )
        )
    return tuple(specs)
