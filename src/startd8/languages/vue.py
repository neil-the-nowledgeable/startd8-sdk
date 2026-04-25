"""Vue 3 single-file component language profile (REQ-VUE-B-001).

Shares the JavaScript-on-Node host with :class:`~startd8.languages.nodejs.NodeLanguageProfile`
but uses dialect ``vue_sfc`` and extension ``.vue``. MicroPrime operates on the
extracted ``<script>`` block (see :mod:`startd8.languages.vue_sfc`).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from .js_metadata import JS_DIALECT_VUE_SFC, JS_HOST_JAVASCRIPT_NODE
from .nodejs import NodeLanguageProfile


class VueLanguageProfile(NodeLanguageProfile):
    """Language profile for Vue 3 SFCs (``.vue``).

    Phase C (REQ-VUE-P-001, P-006, P-007, P-014): extends the Node host with
    Vue-specific cleanup, framework hints, blast radius for colocated modules,
    and template XSS guidance — without duplicating Node ``grpc``/``otel`` entries.
    """

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
        """REQ-VUE-B-005: optional ``vue-tsc --noEmit`` on the ``.vue`` file.

        Checkpoint substitutes ``{file}`` and runs from ``project_root`` (see
        ``contractors/checkpoint.py``). If ``npx`` / ``vue-tsc`` is missing,
        the check is skipped with a warning.

        Set ``STARTD8_VUE_SYNTAX_CHECK=0`` to disable subprocess checks and rely
        on :meth:`validate_syntax` only (gap documented under REQ-VUE-P-005).
        """
        raw = os.environ.get("STARTD8_VUE_SYNTAX_CHECK", "1").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return None
        return ["npx", "--yes", "vue-tsc", "--noEmit", "--pretty", "false", "{file}"]

    @property
    def framework_imports(self) -> Dict[str, dict]:
        """Node host stacks plus Vue 3 ecosystem (REQ-VUE-P-006)."""
        merged = dict(super().framework_imports)
        merged.update({
            "vue_router": {
                "detect": ["vue-router", "router", "createRouter", "useRouter"],
                "dep_names": {"vue-router"},
                "imports": [
                    "import { createRouter, createWebHistory } from 'vue-router';",
                ],
                "conditional": {},
            },
            "pinia": {
                "detect": ["pinia", "createPinia", "defineStore", "useStore"],
                "dep_names": {"pinia"},
                "imports": [
                    "import { createPinia } from 'pinia';",
                ],
                "conditional": {},
            },
            "vitest": {
                "detect": ["vitest", "describe(", "it(", "expect("],
                "dep_names": {"vitest", "@vue/test-utils"},
                "imports": [
                    "import { describe, it, expect } from 'vitest';",
                    "import { mount } from '@vue/test-utils';",
                ],
                "conditional": {},
            },
        })
        return merged

    @property
    def cleanup_patterns(self) -> List[str]:
        """Host patterns plus Vite output dirs (REQ-VUE-P-007)."""
        base = list(super().cleanup_patterns)
        for p in ("dist/", ".vite/", "coverage/"):
            if p not in base:
                base.append(p)
        return base

    @property
    def lint_command(self) -> Optional[List[str]]:
        return None

    @property
    def blast_radius_extensions(self) -> List[str]:
        # Colocated modules beside SFCs (REQ-VUE-P-001): match Node ESM variants.
        return [".vue", ".ts", ".tsx", ".mts", ".js", ".jsx", ".mjs", ".cjs"]

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
            "\n"
            "VUE SECURITY (REQ-VUE-P-014):\n"
            "- Never use ``v-html`` with untrusted or user-controlled strings; prefer "
            "text interpolation or a vetted sanitizer.\n"
            "- Treat URL/query/body-derived values as untrusted when binding to DOM "
            "or attributes.\n"
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
