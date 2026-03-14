"""Bidirectional mapping between PyPI package names and Python import names.

Single source of truth used by:
- Dependency scoping (L3): PyPI → import direction
- Import audit pass (L1): import → PyPI direction
- Framework detection (L5): both directions
"""

from __future__ import annotations

# Maps PyPI distribution names to their importable top-level module names.
# When a package installs a module with a different name than the package
# (e.g. ``pip install grpcio`` but ``import grpc``), it needs an entry here.
_PYPI_TO_IMPORT: dict[str, str] = {
    "grpcio": "grpc",
    "grpcio-health-checking": "grpc_health",
    "grpcio-tools": "grpc_tools",
    "pillow": "PIL",
    "python-json-logger": "pythonjsonlogger",
    "google-api-core": "google.api_core",
    "google-auth": "google.auth",
    "google-cloud-secret-manager": "google.cloud.secretmanager",
    "google-cloud-aiplatform": "google.cloud.aiplatform",
    "langchain-core": "langchain_core",
    "langchain-community": "langchain_community",
    "langchain-google-genai": "langchain_google_genai",
    "opentelemetry-distro": "opentelemetry",
    "opentelemetry-api": "opentelemetry",
    "opentelemetry-sdk": "opentelemetry",
    "opentelemetry-exporter-otlp-proto-grpc": "opentelemetry.exporter.otlp",
    "opentelemetry-instrumentation-grpc": "opentelemetry.instrumentation.grpc",
    "python-dateutil": "dateutil",
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "scikit-learn": "sklearn",
}

# Reverse map: importable module → PyPI package name.
# For modules that map to the same import prefix (e.g. multiple opentelemetry-*
# packages all import as ``opentelemetry``), the reverse map keeps the first
# (shortest) PyPI name encountered.
_IMPORT_TO_PYPI: dict[str, str] = {}
for _pypi, _mod in sorted(_PYPI_TO_IMPORT.items(), key=lambda x: len(x[0])):
    _IMPORT_TO_PYPI.setdefault(_mod, _pypi)


def pypi_to_import(package_name: str) -> str:
    """Map a PyPI package name to its Python import name.

    Returns *package_name* unchanged if no mapping exists (the common case
    where the PyPI name matches the import name, e.g. ``flask``).
    """
    return _PYPI_TO_IMPORT.get(package_name.lower(), package_name)


def import_to_pypi(import_name: str) -> str:
    """Map a Python import name to its PyPI package name.

    Tries exact match first, then prefix match for nested imports
    (e.g. ``google.api_core.retry`` → ``google-api-core``).

    Returns *import_name* unchanged if no mapping exists.
    """
    if import_name in _IMPORT_TO_PYPI:
        return _IMPORT_TO_PYPI[import_name]
    for imp, pypi in _IMPORT_TO_PYPI.items():
        if import_name.startswith(imp + "."):
            return pypi
    return import_name


__all__ = [
    "_PYPI_TO_IMPORT",
    "_IMPORT_TO_PYPI",
    "pypi_to_import",
    "import_to_pypi",
]
