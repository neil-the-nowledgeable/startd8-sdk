"""CSharpLanguageProfile -- C# / .NET language support for Prime Contractor.

Follows the Java profile as the closest structural analog: brace-delimited,
namespace-scoped, NuGet dependency management.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ._validation_utils import check_balanced_braces


_CSHARP_STDLIB_PREFIXES: tuple[str, ...] = (
    "System",
    "Microsoft",
    "Windows",
)

# Python fingerprints -- if these appear in a .cs file, it's cross-language contamination.
_PYTHON_FINGERPRINTS = (
    "def ", "import os", "from __future__", "print(", "self.",
    "#!/usr/bin/env python", "#!/usr/bin/python",
)

# C# type declaration patterns
_CSHARP_TYPE_DECL_RE = re.compile(
    r"\b(?:class|interface|struct|record|enum)\s+\w+",
)


class CSharpLanguageProfile:
    """Language profile for C# code generation."""

    @property
    def language_id(self) -> str:
        return "csharp"

    @property
    def display_name(self) -> str:
        return "C#"

    @property
    def source_extensions(self) -> List[str]:
        return [".cs"]

    @property
    def build_file_patterns(self) -> List[str]:
        return ["*.csproj", "*.sln", "Directory.Build.props"]

    @property
    def syntax_check_command(self) -> Optional[List[str]]:
        # dotnet build requires full project context; no single-file check.
        return None

    @property
    def lint_command(self) -> Optional[List[str]]:
        # Roslyn analyzers are configured in .csproj, not invoked standalone.
        return None

    @property
    def test_command(self) -> Optional[List[str]]:
        return ["dotnet", "test", "--no-build"]

    @property
    def framework_imports(self) -> Dict[str, dict]:
        return {
            "aspnet_core": {
                "detect": [
                    "asp.net", "aspnetcore", "webapplication",
                    "mapget", "mappost", "microsoft.aspnetcore",
                ],
                "dep_names": {"Microsoft.AspNetCore.App"},
                "imports": [
                    "using Microsoft.AspNetCore.Builder;",
                    "using Microsoft.AspNetCore.Hosting;",
                    "using Microsoft.Extensions.DependencyInjection;",
                ],
                "conditional": {},
            },
            "ef_core": {
                "detect": [
                    "dbcontext", "entity framework",
                    "entityframeworkcore", "efcore",
                ],
                "dep_names": {
                    "Microsoft.EntityFrameworkCore",
                    "Microsoft.EntityFrameworkCore.SqlServer",
                },
                "imports": [
                    "using Microsoft.EntityFrameworkCore;",
                ],
                "conditional": {},
            },
            "grpc": {
                "detect": ["grpc", "protobuf", "proto"],
                "dep_names": {"Grpc.AspNetCore", "Google.Protobuf"},
                "imports": [
                    "using Grpc.Core;",
                    "using Google.Protobuf;",
                ],
                "conditional": {},
            },
            "serilog": {
                "detect": ["serilog", "log.information", "log.error"],
                "dep_names": {"Serilog", "Serilog.AspNetCore"},
                "imports": [
                    "using Serilog;",
                ],
                "conditional": {},
            },
            "redis": {
                "detect": ["redis", "cache", "distributed cache"],
                "dep_names": {"Microsoft.Extensions.Caching.StackExchangeRedis"},
                "imports": [
                    "using Microsoft.Extensions.Caching.Distributed;",
                ],
                "conditional": {},
            },
            "xunit": {
                "detect": ["xunit", "unit test", "fact", "theory"],
                "dep_names": {"xunit", "xunit.runner.visualstudio"},
                "imports": [
                    "using Xunit;",
                ],
                "conditional": {},
            },
            "spanner": {
                "detect": ["spanner", "cloud spanner"],
                "dep_names": {"Google.Cloud.Spanner.Data"},
                "imports": [
                    "using Google.Cloud.Spanner.Data;",
                ],
                "conditional": {},
            },
            "secretmanager": {
                "detect": ["secret manager", "secrets"],
                "dep_names": {"Google.Cloud.SecretManager.V1"},
                "imports": [
                    "using Google.Cloud.SecretManager.V1;",
                ],
                "conditional": {},
            },
            "npgsql": {
                "detect": ["npgsql", "postgresql", "alloydb"],
                "dep_names": {"Npgsql"},
                "imports": [
                    "using Npgsql;",
                ],
                "conditional": {},
            },
            "grpc_health": {
                "detect": ["health check", "healthcheck"],
                "dep_names": {"Grpc.HealthCheck"},
                "imports": [
                    "using Grpc.Health.V1;",
                ],
                "conditional": {},
            },
        }

    @property
    def package_alias_map(self) -> Dict[str, str]:
        return {}

    @property
    def cleanup_patterns(self) -> List[str]:
        return ["bin/", "obj/", ".vs/"]

    @property
    def blast_radius_extensions(self) -> List[str]:
        return [".cs"]

    @property
    def import_pattern_template(self) -> str:
        return "using.*{module}"

    @property
    def system_prompt_role(self) -> str:
        return "an expert C# / .NET engineer"

    @property
    def coding_standards(self) -> str:
        return (
            "PascalCase for public members, camelCase for private fields/locals. "
            "Use nullable reference types. Prefer async/await. "
            "Use 'using' declarations for IDisposable. "
            "Expression-bodied members for simple accessors."
        )

    @property
    def merge_strategy_preference(self) -> str:
        return "simple"

    @property
    def repair_enabled(self) -> bool:
        return False

    @property
    def docker_base_image(self) -> str:
        return "mcr.microsoft.com/dotnet/sdk:10.0"

    @property
    def docker_runtime_image(self) -> str:
        return "mcr.microsoft.com/dotnet/runtime-deps:10.0-chiseled"

    @property
    def stub_patterns(self) -> List[str]:
        return [
            r'throw\s+new\s+NotImplementedException\s*\(',
            r'throw\s+new\s+NotSupportedException\s*\(',
            r'^\s*//\s*TODO\b',
        ]

    @property
    def function_start_pattern(self) -> Optional[str]:
        return (
            r'^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?'
            r'(?:async\s+)?(?:override\s+)?[\w<>\[\],\s]+\s+'
            r'(?P<name>[A-Za-z_]\w*)\s*[\(<]'
        )

    def supports_extension(self, ext: str) -> bool:
        return ext.lower() == ".cs"

    def get_import_patterns(self, module_stem: str) -> List[str]:
        return [
            f"using {module_stem}",
            f"using static {module_stem}",
        ]

    def get_stdlib_prefixes(self) -> Sequence[str]:
        return _CSHARP_STDLIB_PREFIXES

    def post_generation_cleanup(
        self, files: List[Path], project_root: Path,
    ) -> List[str]:
        # C# has no standalone import fixer callable from CLI.
        # dotnet format requires a project context.
        return []

    def validate_syntax(self, code: str) -> tuple[bool, str]:
        """C# syntax validation via tree-sitter (with text-based fallback).

        Uses tree-sitter-c-sharp for per-file syntax checking when available
        (~5ms, in-process, no .NET SDK required). Falls back to text-based
        heuristics (balanced braces, type declaration check) when tree-sitter
        is not installed.
        """
        from .csharp_parser import validate_csharp_syntax
        return validate_csharp_syntax(code)

    def generate_dependency_file(
        self,
        project_root: Path,
        service_name: str,
        module_path: str,
        dependencies: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Generate .csproj XML content from service metadata."""
        target_framework = "net8.0"
        if metadata:
            target_framework = str(
                metadata.get("target_framework", target_framework),
            )

        lines = [
            '<Project Sdk="Microsoft.NET.Sdk.Web">',
            "",
            "  <PropertyGroup>",
            f"    <TargetFramework>{target_framework}</TargetFramework>",
            "    <Nullable>enable</Nullable>",
            "  </PropertyGroup>",
        ]

        if dependencies:
            lines.append("")
            lines.append("  <ItemGroup>")
            for dep in dependencies:
                dep = dep.strip()
                if not dep:
                    continue
                # NuGet format: Name/Version or plain Name
                if "/" in dep:
                    name, version = dep.split("/", 1)
                    name = name.strip()
                    version = version.strip()
                else:
                    name = dep
                    version = "*"
                lines.append(
                    f'    <PackageReference Include="{name}" '
                    f'Version="{version}" />',
                )
            lines.append("  </ItemGroup>")

        lines.append("")
        lines.append("</Project>")
        lines.append("")

        return "\n".join(lines)

    def derive_service_metadata(
        self,
        features: Sequence[Any],
        *,
        onboarding: Optional[Dict[str, Any]] = None,
        api_signatures: Optional[List[str]] = None,
        runtime_dependencies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Derive C#-specific service metadata from plan features.

        Extracts csharp_namespace and target_framework.
        """
        metadata: Dict[str, Any] = {}

        # csharp_namespace: check explicit attribute first
        namespaces: list[str] = []
        for f in features:
            ns = getattr(f, "csharp_namespace", "")
            if ns:
                namespaces.append(ns)
        if namespaces:
            metadata["csharp_namespace"] = namespaces[0]
        else:
            # Infer from target file paths
            for f in features:
                for tf in getattr(f, "target_files", []):
                    if tf.endswith(".cs"):
                        ns = _derive_namespace(tf)
                        if ns:
                            metadata["csharp_namespace"] = ns
                            break
                if "csharp_namespace" in metadata:
                    break

        # target_framework
        target_framework = "net8.0"
        for f in features:
            tf_val = getattr(f, "target_framework", "")
            if tf_val:
                target_framework = tf_val
                break
        if onboarding:
            target_framework = str(
                onboarding.get("target_framework", target_framework),
            )
        metadata["target_framework"] = target_framework

        return metadata

    def build_project_context_section(self, context: Dict[str, Any]) -> str:
        """Build C# project context section for correct namespace and using generation."""
        target_files = context.get("target_files") or []
        csharp_namespace = context.get("csharp_namespace", "")
        target_framework = context.get("target_framework", "net8.0")

        # Check service_metadata fallback
        svc_meta = context.get("service_metadata")
        if isinstance(svc_meta, dict):
            if not csharp_namespace:
                csharp_namespace = svc_meta.get("csharp_namespace", "")
            if target_framework == "net8.0":
                target_framework = svc_meta.get(
                    "target_framework", target_framework,
                )

        # Derive namespace from target file if not provided
        if not csharp_namespace and target_files:
            for tf in target_files:
                if tf.endswith(".cs"):
                    ns = _derive_namespace(tf)
                    if ns:
                        csharp_namespace = ns
                        break

        lines = [
            "## C# Project Context (CRITICAL -- required for compilation)\n",
        ]
        if csharp_namespace:
            lines.append(
                f"- **Namespace**: `namespace {csharp_namespace};`"
            )
        lines.append(f"- **Target framework**: {target_framework}")

        lines.extend([
            "",
            "**C# using rules:**",
            "- Every type must have a corresponding `using` directive",
            "- Group usings: `System.*` first, then `Microsoft.*`, then third-party",
            "- No unused using directives",
            "- Every using must end with `;`",
            "",
            "**C# structural rules:**",
            "- PascalCase for types, methods, and public members",
            "- camelCase for local variables and private fields (prefix with `_`)",
            "- Enable nullable reference types (`#nullable enable` or via .csproj)",
            "- Prefer async/await for I/O-bound operations",
            "- Use `using` declarations for IDisposable resources",
        ])

        return "\n".join(lines)

    def strip_dependency_version(self, dep: str) -> str:
        """Strip version from NuGet dependency. 'Package/1.0.0' -> 'Package'."""
        if "/" in dep:
            return dep.split("/")[0].strip()
        return dep.strip()

    def get_import_syntax_guidance(self) -> str:
        """Return C# using rules for LLM prompts."""
        return (
            "Use ONLY these packages plus .NET BCL (System.*/Microsoft.*). Every\n"
            "type you reference MUST have a corresponding `using` directive.\n"
            "Use fully qualified namespace imports. Do NOT reference packages "
            "not listed above.\n"
        )


def _derive_namespace(file_path: str) -> str:
    """Derive a C# namespace from a file path.

    Converts directory structure to dotted namespace.
    Strips common prefixes like 'src/' and removes the filename.

    Examples:
        'src/MyApp/Services/UserService.cs' -> 'MyApp.Services'
        'Services/UserService.cs' -> 'Services'
    """
    from pathlib import PurePosixPath

    parts = PurePosixPath(file_path).parent.parts

    # Strip common prefixes
    skip_prefixes = {"src", "source", "lib"}
    if parts and parts[0].lower() in skip_prefixes:
        parts = parts[1:]

    if not parts or parts == (".",):
        return ""

    return ".".join(parts)
