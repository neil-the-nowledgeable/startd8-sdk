"""Provenance headers for proto-owned skeleton files."""

from __future__ import annotations


def header_proto(source_file: str, proto_sha: str, kind: str, service: str) -> str:
    return (
        f"# GENERATED from {source_file} — do not edit by hand; "
        f"regenerate via `startd8 generate grpc`.\n"
        f"# startd8-artifact: {kind}\n"
        f"# Source of truth: the .proto service contract.\n"
        f"# proto-sha256: {proto_sha}\n"
        f"# service: {service}"
    )
