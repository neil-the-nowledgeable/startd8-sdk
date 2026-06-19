"""Deterministic-file provider for Kafka event stubs."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from ..scaffold_codegen.manifest import parse_app_manifest
from .drift import events_file_in_sync, is_owned_events_file


class EventsFileProvider:
    """Recognizes owned ``app/events/*`` modules declared in ``events.yaml``."""

    name = "events"

    def owns(self, path: Path, content: str) -> bool:
        return is_owned_events_file(content)

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        events_text = self._read_events_manifest(context)
        schema_text = self._read_schema(context)
        if not events_text or not schema_text:
            return False
        rel = self._relative_path(path, context)
        if rel is None:
            return False
        backend, package = self._messaging_and_package(context)
        return events_file_in_sync(
            events_text,
            schema_text,
            rel,
            content,
            messaging_backend=backend,
            package=package,
        )

    @staticmethod
    def _read_events_manifest(context: ProviderContext) -> Optional[str]:
        root = Path(context.project_root)
        for anchor in context.source_anchors:
            if not str(anchor).endswith("events.yaml"):
                continue
            ap = Path(anchor) if Path(anchor).is_absolute() else root / anchor
            if ap.is_file():
                try:
                    return ap.read_text(encoding="utf-8")
                except OSError:
                    return None
        for conventional in (root / "events.yaml", root / "prisma" / "events.yaml"):
            if conventional.is_file():
                try:
                    return conventional.read_text(encoding="utf-8")
                except OSError:
                    return None
        return None

    @staticmethod
    def _read_schema(context: ProviderContext) -> Optional[str]:
        root = Path(context.project_root)
        for anchor in context.source_anchors:
            if not str(anchor).endswith("schema.prisma"):
                continue
            ap = Path(anchor) if Path(anchor).is_absolute() else root / anchor
            if ap.is_file():
                try:
                    return ap.read_text(encoding="utf-8")
                except OSError:
                    return None
        for conventional in (root / "prisma" / "schema.prisma", root / "schema.prisma"):
            if conventional.is_file():
                try:
                    return conventional.read_text(encoding="utf-8")
                except OSError:
                    return None
        return None

    @staticmethod
    def _messaging_and_package(context: ProviderContext) -> tuple[str, str]:
        root = Path(context.project_root)
        for conventional in (root / "app.yaml", root / "prisma" / "app.yaml"):
            if conventional.is_file():
                try:
                    manifest = parse_app_manifest(conventional.read_text(encoding="utf-8"))
                    return manifest.messaging_backend, manifest.package
                except (OSError, ValueError):
                    break
        return "aiokafka", "app"

    @staticmethod
    def _relative_path(path: Path, context: ProviderContext) -> Optional[str]:
        root = Path(context.project_root)
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.name
