"""Framework-specific import templates for code generation.

When a task targets a known framework domain, the corresponding import
block is injected into the spec as a mandatory preamble, reducing
post-generation import repair.  Framework detection uses three sources
(checked in priority order): runtime_dependencies, task description
keywords, and target file name patterns.
"""

from __future__ import annotations

from typing import Any


__all__ = [
    "FRAMEWORK_IMPORTS",
    "detect_frameworks",
    "get_import_preamble",
]


FRAMEWORK_IMPORTS: dict[str, dict[str, Any]] = {
    "grpc": {
        "detect": ["grpc", "grpcio", "proto", "protobuf", "gRPC"],
        "dep_names": {"grpcio", "grpcio-health-checking", "grpcio-tools"},
        "imports": [
            "import grpc",
            "from concurrent import futures",
        ],
        "conditional": {
            "opentelemetry": [
                "from opentelemetry import trace",
                "from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer",
            ],
        },
    },
    "locust": {
        "detect": ["locust", "load test", "load generator", "traffic simulation"],
        "dep_names": {"locust"},
        "imports": [
            "from locust import FastHttpUser, TaskSet, between",
        ],
        "conditional": {
            "faker": ["from faker import Faker"],
        },
    },
    "flask": {
        "detect": ["flask", "web server", "REST API", "HTTP endpoint"],
        "dep_names": {"flask"},
        "imports": [
            "from flask import Flask, request, jsonify",
        ],
        "conditional": {},
    },
    "opentelemetry": {
        "detect": ["opentelemetry", "OTel", "tracing", "instrumentation"],
        "dep_names": {
            "opentelemetry-api",
            "opentelemetry-sdk",
            "opentelemetry-distro",
            "opentelemetry-exporter-otlp-proto-grpc",
            "opentelemetry-instrumentation-grpc",
        },
        "imports": [
            "from opentelemetry import trace",
            "from opentelemetry.sdk.trace import TracerProvider",
            "from opentelemetry.sdk.trace.export import BatchSpanProcessor",
        ],
        "conditional": {},
    },
    "fastapi": {
        "detect": ["fastapi", "FastAPI"],
        "dep_names": {"fastapi"},
        "imports": [
            "from fastapi import FastAPI, HTTPException, Depends",
        ],
        "conditional": {
            "uvicorn": ["import uvicorn"],
        },
    },
}


def _strip_version(dep: str) -> str:
    """Strip version pins: ``grpcio==1.76.0`` → ``grpcio``."""
    for sep in ("==", ">=", "<=", "~=", "!=", "<", ">"):
        dep = dep.split(sep)[0]
    return dep.strip().lower()


def detect_frameworks(
    task_description: str = "",
    target_files: list[str] | None = None,
    dependencies: list[str] | None = None,
) -> list[str]:
    """Return framework keys detected from task metadata.

    Detection sources (checked in order):
    1. ``dependencies`` — if a dep name matches a framework's ``dep_names``
    2. ``task_description`` — case-insensitive keyword match against ``detect``
    3. ``target_files`` — filename patterns (currently informational only)

    Returns:
        Sorted list of framework keys (e.g. ``["flask", "grpc"]``).
    """
    detected: set[str] = set()
    dep_names_lower: set[str] = set()

    if dependencies:
        dep_names_lower = {_strip_version(d) for d in dependencies}

    desc_lower = task_description.lower() if task_description else ""

    for framework_key, config in FRAMEWORK_IMPORTS.items():
        # Source 1: dependency name match
        framework_dep_names = config.get("dep_names", set())
        if dep_names_lower & framework_dep_names:
            detected.add(framework_key)
            continue

        # Source 2: description keyword match
        detect_keywords = config.get("detect", [])
        for keyword in detect_keywords:
            if keyword.lower() in desc_lower:
                detected.add(framework_key)
                break

    return sorted(detected)


def get_import_preamble(
    frameworks: list[str],
    dependencies: list[str] | None = None,
) -> str:
    """Return formatted import block for detected frameworks.

    Includes conditional imports when their trigger package is present
    in *dependencies*.

    Args:
        frameworks: Framework keys from :func:`detect_frameworks`.
        dependencies: Full dependency list for conditional import resolution.

    Returns:
        Formatted import preamble string, or empty string if no frameworks.
    """
    if not frameworks:
        return ""

    dep_names_lower: set[str] = set()
    if dependencies:
        dep_names_lower = {_strip_version(d) for d in dependencies}

    lines: list[str] = []
    lines.append("## Framework Import Templates")
    lines.append("")
    lines.append(
        "The following import patterns are canonical for the detected frameworks. "
        "Use these exact import statements (adapt module names to your project):"
    )
    lines.append("")

    for fw_key in frameworks:
        config = FRAMEWORK_IMPORTS.get(fw_key)
        if not config:
            continue

        lines.append(f"### {fw_key}")
        lines.append("```python")
        for imp in config.get("imports", []):
            lines.append(imp)

        # Add conditional imports if trigger package is in deps
        # Match both exact name and prefix (e.g. "opentelemetry" matches "opentelemetry-api")
        for trigger_pkg, cond_imports in config.get("conditional", {}).items():
            trigger_lower = trigger_pkg.lower()
            matched = any(
                d == trigger_lower or d.startswith(trigger_lower + "-")
                for d in dep_names_lower
            )
            if matched:
                for imp in cond_imports:
                    lines.append(imp)

        lines.append("```")
        lines.append("")

    return "\n".join(lines)
