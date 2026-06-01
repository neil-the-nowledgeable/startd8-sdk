"""PrismaLanguageProfile — first-class `.prisma` recognition (RUN-008 FR-6).

Prisma schema is a **schema DSL**, not a general-purpose language and not
JS-on-Node, so this profile does NOT subclass :class:`NodeLanguageProfile`
(the way :class:`VueLanguageProfile` does). It exists to:

1. Stop ``.prisma`` files resolving to the Python profile by default
   (``resolution.py`` fell through to ``python`` — RUN-008 gap G3).
2. Provide an in-process structural ``validate_syntax`` (brace balance) and a
   ``prisma validate`` checkpoint command.
3. Carry the :mod:`startd8.languages.prisma_parser` entity model that FR-5
   (unique-key validity) and FR-7 (Prisma↔Zod symmetry) consume.

Most protocol members are intentionally inert (no imports, no tests, no
MicroPrime stubs) — a schema has no functions to fill or import graph to align.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .prisma_parser import PrismaSchema, parse_prisma_schema


class PrismaLanguageProfile:
    """Language profile for Prisma schema files (``.prisma``)."""

    @property
    def language_id(self) -> str:
        return "prisma"

    @property
    def display_name(self) -> str:
        return "Prisma Schema"

    @property
    def source_extensions(self) -> List[str]:
        return [".prisma"]

    @property
    def build_file_patterns(self) -> List[str]:
        return ["schema.prisma"]

    @property
    def syntax_check_command(self) -> Optional[List[str]]:
        """``prisma validate`` on the schema file (checkpoint substitutes ``{file}``).

        Gated by ``STARTD8_PRISMA_SYNTAX_CHECK`` (default on); set to a falsey
        value to rely on the in-process :meth:`validate_syntax` only when
        ``npx``/``prisma`` is unavailable.
        """
        raw = os.environ.get("STARTD8_PRISMA_SYNTAX_CHECK", "1").strip().lower()
        if raw in ("0", "false", "no", "off"):
            return None
        return ["npx", "--yes", "prisma", "validate", "--schema", "{file}"]

    @property
    def lint_command(self) -> Optional[List[str]]:
        return None

    @property
    def test_command(self) -> Optional[List[str]]:
        return None

    @property
    def framework_imports(self) -> Dict[str, dict]:
        return {}

    @property
    def package_alias_map(self) -> Dict[str, str]:
        return {}

    @property
    def cleanup_patterns(self) -> List[str]:
        return []

    @property
    def blast_radius_extensions(self) -> List[str]:
        return [".prisma"]

    @property
    def import_pattern_template(self) -> str:
        # Prisma has no import statements; relations reference model names directly.
        return "{module}"

    @property
    def system_prompt_role(self) -> str:
        return "an expert Prisma schema engineer"

    @property
    def coding_standards(self) -> str:
        return (
            "Prisma schema standards:\n"
            "- Model names PascalCase; field names camelCase.\n"
            "- Every model has an `@id` field. Use `@unique` (or `@@unique([...])`) "
            "for any field a query reads via `findUnique`/`upsert` `where`.\n"
            "- Field names and types MUST match the corresponding Zod schema exactly "
            "(no synonyms: `summary` not `bio`, `yearsExp` not `yearsOfExperience`).\n"
            "- Model child entities reference parents via an explicit relation + scalar "
            "FK column (`parentId String` + `parent Parent @relation(...)`), not an "
            "implicit field — do not invent an FK the relation graph doesn't declare.\n"
        )

    @property
    def merge_strategy_preference(self) -> str:
        return "simple"

    @property
    def repair_enabled(self) -> bool:
        # No Prisma repair steps exist; routing into the code-repair pipeline is a no-op.
        return False

    @property
    def docker_base_image(self) -> str:
        return "node:20-slim"

    @property
    def docker_runtime_image(self) -> str:
        return "node:20-slim"

    @property
    def stub_patterns(self) -> List[str]:
        return []

    @property
    def function_start_pattern(self) -> Optional[str]:
        return None

    @property
    def stub_marker_text(self) -> str:
        return "`// TODO`"

    def supports_extension(self, ext: str) -> bool:
        return ext.lower() == ".prisma"

    def get_import_patterns(self, module_stem: str) -> List[str]:
        return [module_stem]

    def get_stdlib_prefixes(self) -> Sequence[str]:
        return ()

    def post_generation_cleanup(self, files: List[Path], project_root: Path) -> List[str]:
        return []

    def validate_syntax(self, code: str, *, filename_hint: str = "") -> tuple[bool, str]:
        """In-process structural check: balanced braces + at least one block.

        Authoritative validation is ``prisma validate`` (:meth:`syntax_check_command`);
        this is the cheap gate MicroPrime/disk checks use when no toolchain is present.
        """
        text = code or ""
        depth = 0
        for ch in text:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    return False, "unbalanced '}' in Prisma schema"
        if depth != 0:
            return False, "unbalanced '{' in Prisma schema"
        # A non-trivial schema that declares blocks must parse into at least one.
        stripped = text.strip()
        if stripped and any(
            kw in stripped for kw in ("model ", "enum ", "datasource ", "generator ", "type ")
        ):
            schema = parse_prisma_schema(text)
            if not (schema.models or schema.enums or schema.datasource_provider
                    or schema.generator_provider):
                return False, "no parseable Prisma blocks found"
        return True, ""

    def parse_schema(self, code: str) -> PrismaSchema:
        """Convenience accessor: parse schema *code* into a :class:`PrismaSchema`."""
        return parse_prisma_schema(code)

    def generate_dependency_file(
        self,
        project_root: Path,
        service_name: str,
        module_path: str,
        dependencies: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        return None

    def derive_service_metadata(
        self,
        features: Sequence[Any],
        *,
        onboarding: Optional[Dict[str, Any]] = None,
        api_signatures: Optional[List[str]] = None,
        runtime_dependencies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {}

    def build_project_context_section(self, context: Dict[str, Any]) -> str:
        return ""

    def strip_dependency_version(self, dep: str) -> str:
        return dep.strip()

    def get_import_syntax_guidance(self) -> str:
        return ""

    def extract_import_lines(self, source: str) -> List[str]:
        return []

    def sanitize_code_examples(self, text: str) -> str:
        return text
