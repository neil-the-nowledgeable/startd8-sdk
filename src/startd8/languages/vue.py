"""Vue 3 single-file component language profile (REQ-VUE-B-001).

Shares the JavaScript-on-Node host with :class:`~startd8.languages.nodejs.NodeLanguageProfile`
but uses dialect ``vue_sfc`` and extension ``.vue``. MicroPrime operates on the
extracted ``<script>`` block (see :mod:`startd8.languages.vue_sfc`).
"""

from __future__ import annotations

from typing import List, Optional

from .js_metadata import JS_DIALECT_VUE_SFC, JS_HOST_JAVASCRIPT_NODE
from .nodejs import NodeLanguageProfile


class VueLanguageProfile(NodeLanguageProfile):
    """Language profile for Vue 3 SFCs (``.vue``)."""

    @property
    def language_id(self) -> str:
        return "vue"

    @property
    def display_name(self) -> str:
        return "Vue 3 (SFC)"

    @property
    def js_host_id(self) -> str:
        return JS_HOST_JAVASCRIPT_NODE

    @property
    def js_dialect_id(self) -> str:
        return JS_DIALECT_VUE_SFC

    @property
    def source_extensions(self) -> List[str]:
        return [".vue"]

    @property
    def build_file_patterns(self) -> List[str]:
        base = list(super().build_file_patterns)
        extra = [
            "vite.config.ts",
            "vite.config.js",
            "vite.config.mts",
            "pnpm-lock.yaml",
            "pnpm-workspace.yaml",
        ]
        for p in extra:
            if p not in base:
                base.append(p)
        return base

    @property
    def syntax_check_command(self) -> Optional[List[str]]:
        """Optional ``vue-tsc`` / ESLint wiring is REQ-VUE-B-005 (deferred for MVP)."""
        return None

    @property
    def lint_command(self) -> Optional[List[str]]:
        return None

    @property
    def blast_radius_extensions(self) -> List[str]:
        return [".vue", ".ts", ".tsx", ".js", ".jsx"]

    @property
    def system_prompt_role(self) -> str:
        return "an expert Vue 3 engineer"

    @property
    def coding_standards(self) -> str:
        node_std = super().coding_standards
        sfc = (
            "\n\nVUE SFC (basic tier):\n"
            "- Edit the ``<script setup>`` or first ``<script>`` block only unless "
            "the task explicitly covers template or style.\n"
            "- Preserve ``<template>`` and ``<style>`` blocks verbatim when generating "
            "or patching script.\n"
            "- Prefer Composition API with ``<script setup>`` and TypeScript when "
            "``lang=\"ts\"`` is set.\n"
            "- Do not add Nuxt-specific or Vue 2 Options API patterns unless the "
            "existing file already uses them.\n"
        )
        return node_std + sfc

    def supports_extension(self, ext: str) -> bool:
        return ext.lower() == ".vue"

    def validate_syntax(
        self, code: str, *, filename_hint: str = "",
    ) -> tuple[bool, str]:
        """Validate the extracted script when the buffer is an SFC; else delegate."""
        from .vue_sfc import extract_vue_script

        ext = extract_vue_script(code)
        if ext is None or not ext.script.strip():
            return True, ""
        hint = ".ts" if ext.lang == "ts" else ".js"
        return super().validate_syntax(ext.script, filename_hint=hint)
