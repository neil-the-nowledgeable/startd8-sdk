"""CSharpLanguageProfile -- C# / .NET language support for Prime Contractor.

Follows the Java profile as the closest structural analog: brace-delimited,
namespace-scoped, NuGet dependency management.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ._validation_utils import PYTHON_FINGERPRINTS, check_balanced_braces


_CSHARP_STDLIB_PREFIXES: tuple[str, ...] = (
    "System",
    "Microsoft",
    "Windows",
)


# ~80 C# keywords + contextual keywords (C# 12/13)
_CSHARP_RESERVED: frozenset[str] = frozenset({
    # Standard keywords
    "abstract", "as", "base", "bool", "break", "byte", "case", "catch",
    "char", "checked", "class", "const", "continue", "decimal", "default",
    "delegate", "do", "double", "else", "enum", "event", "explicit",
    "extern", "false", "finally", "fixed", "float", "for", "foreach",
    "goto", "if", "implicit", "in", "int", "interface", "internal", "is",
    "lock", "long", "namespace", "new", "null", "object", "operator",
    "out", "override", "params", "private", "protected", "public",
    "readonly", "ref", "return", "sbyte", "sealed", "short", "sizeof",
    "stackalloc", "static", "string", "struct", "switch", "this", "throw",
    "true", "try", "typeof", "uint", "ulong", "unchecked", "unsafe",
    "ushort", "using", "virtual", "void", "volatile", "while",
    # Contextual keywords (C# 7+/8+/9+/10+/11+/12+)
    "add", "and", "alias", "ascending", "args", "async", "await", "by",
    "descending", "dynamic", "equals", "file", "from", "get", "global",
    "group", "init", "into", "join", "let", "managed", "nameof", "nint",
    "not", "notnull", "nuint", "on", "or", "orderby", "partial",
    "record", "remove", "required", "scoped", "select", "set",
    "unmanaged", "value", "var", "when", "where", "with", "yield",
})


def _csharp_literal_coerce(value: object) -> str:
    """Coerce a Python literal to C# syntax.

    ``True`` -> ``true``, ``None`` -> ``null``, ``[1, 2]`` -> ``new[] { 1, 2 }``.
    """
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, list):
        items = ", ".join(_csharp_literal_coerce(v) for v in value)
        return f"new[] {{ {items} }}"
    if isinstance(value, dict):
        entries = ", ".join(
            f"{{ {_csharp_literal_coerce(k)}, {_csharp_literal_coerce(v)} }}"
            for k, v in value.items()
        )
        return f"new Dictionary<string, object> {{ {entries} }}"
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)

# Re-export for backward compat; canonical source is _validation_utils
_PYTHON_FINGERPRINTS = PYTHON_FINGERPRINTS

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
        # REQ-KZ-CS-400a/400b: Phase 1-2 repair (fence strip + dotnet format)
        return True

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
        """Run ``dotnet format`` on generated C# files if available (REQ-CS-300).

        Best-effort style formatting only — does not fix missing ``using``
        directives.  Requires a ``.csproj`` in *project_root* or a parent
        directory.  Skips silently when ``dotnet`` is not on PATH.
        """
        import shutil
        import subprocess

        dotnet = shutil.which("dotnet")
        if not dotnet:
            return []

        # dotnet format needs a project file — check if one exists
        csproj_files = list(project_root.glob("**/*.csproj"))
        if not csproj_files:
            return []

        formatted: List[str] = []
        cs_files = [f for f in files if f.suffix.lower() == ".cs"]
        if not cs_files:
            return []

        # dotnet format operates on the whole project, not individual files.
        # Run once and report all .cs files as formatted.
        try:
            proc = subprocess.run(
                [dotnet, "format", str(csproj_files[0]), "--no-restore"],
                capture_output=True,
                timeout=60,
                cwd=str(project_root),
            )
            if proc.returncode == 0:
                formatted = [str(f) for f in cs_files]
        except (subprocess.TimeoutExpired, OSError):
            pass  # best-effort — skip on failure
        return formatted

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
        """Generate .csproj XML content from service metadata.

        Handles dependency formats: ``Name/Version``, ``Name Version``,
        or plain ``Name``.  Supports ``sdk_type`` and ``protobuf_items``
        in *metadata*.
        """
        target_framework = "net8.0"
        sdk_type = "Microsoft.NET.Sdk.Web"
        protobuf_items: List[str] = []
        if metadata:
            target_framework = str(
                metadata.get("target_framework", target_framework),
            )
            sdk_type = str(metadata.get("sdk_type", sdk_type))
            protobuf_items = metadata.get("protobuf_items", [])

        lines = [
            f'<Project Sdk="{sdk_type}">',
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
                # NuGet format: Name/Version, Name Version, or plain Name
                if "/" in dep:
                    name, version = dep.split("/", 1)
                elif " " in dep:
                    parts = dep.split(None, 1)
                    name, version = parts[0], parts[1]
                else:
                    name, version = dep, ""
                name = name.strip()
                version = version.strip()
                if version:
                    lines.append(
                        f'    <PackageReference Include="{name}" '
                        f'Version="{version}" />',
                    )
                else:
                    lines.append(
                        f'    <PackageReference Include="{name}" />',
                    )
            lines.append("  </ItemGroup>")

        if protobuf_items:
            lines.append("")
            lines.append("  <ItemGroup>")
            for proto in protobuf_items:
                lines.append(
                    f'    <Protobuf Include="{proto}" GrpcServices="Both" />',
                )
            lines.append("  </ItemGroup>")

        lines.append("")
        lines.append("</Project>")
        lines.append("")

        return "\n".join(lines)

    def generate_solution_file(
        self,
        solution_name: str,
        projects: List[Dict[str, str]],
    ) -> str:
        """Generate .sln file content (REQ-CS-104).

        Args:
            solution_name: Solution name (used in header comment).
            projects: List of dicts with keys ``name``, ``path``, ``guid``.
                ``guid`` should include braces, e.g. ``{2348C29F-...}``.

        Returns:
            Complete .sln file content with correct Visual Studio format.
        """
        cs_project_type = "{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}"

        lines = [
            "",
            "Microsoft Visual Studio Solution File, Format Version 12.00",
            "# Visual Studio 15",
        ]

        for proj in projects:
            name = proj["name"]
            path = proj["path"]
            guid = proj["guid"]
            lines.append(
                f'Project("{cs_project_type}") = "{name}", '
                f'"{path}", "{guid}"'
            )
            lines.append("EndProject")

        lines.append("Global")
        lines.append(
            "\tGlobalSection(SolutionConfigurationPlatforms) = preSolution"
        )
        for config in ("Debug", "Release"):
            for platform in ("Any CPU",):
                lines.append(f"\t\t{config}|{platform} = {config}|{platform}")
        lines.append("\tEndGlobalSection")

        lines.append(
            "\tGlobalSection(ProjectConfigurationPlatforms) = postSolution"
        )
        for proj in projects:
            guid = proj["guid"]
            for config in ("Debug", "Release"):
                for platform in ("Any CPU",):
                    lines.append(
                        f"\t\t{guid}.{config}|{platform}.ActiveCfg = "
                        f"{config}|{platform}"
                    )
                    lines.append(
                        f"\t\t{guid}.{config}|{platform}.Build.0 = "
                        f"{config}|{platform}"
                    )
        lines.append("\tEndGlobalSection")
        lines.append("EndGlobal")
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

        # sdk_type: detect from target files and dependencies
        all_files = [
            tf for f in features for tf in getattr(f, "target_files", [])
        ]
        has_web_files = any(
            "Startup.cs" in tf or "Program.cs" in tf for tf in all_files
        )
        all_deps = " ".join(runtime_dependencies or []).lower()
        if has_web_files or "grpc" in all_deps or "aspnetcore" in all_deps:
            metadata["sdk_type"] = "Microsoft.NET.Sdk.Web"
        else:
            metadata["sdk_type"] = "Microsoft.NET.Sdk"

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
            "**C# structural rules (MANDATORY):**",
            "- **PascalCase namespaces** matching directory structure "
            "(e.g., `src/CartService/Services/` → `namespace CartService.Services;`)",
            "- PascalCase for types, methods, and public members",
            "- camelCase for local variables and private fields (prefix with `_`)",
            "- **File-scoped namespaces REQUIRED**: `namespace Foo.Bar;` "
            "(NEVER block-scoped `namespace Foo.Bar { ... }`)",
            "- Enable nullable reference types (`<Nullable>enable</Nullable>` in .csproj)",
            "- Prefer async/await for I/O-bound operations",
            "- Use `using` declarations for IDisposable resources",
            "",
            "**Logging (MANDATORY for service classes):**",
            "- Constructor-inject `ILogger<T>` — do NOT use `Console.WriteLine()`",
            "- Use `_logger.LogInformation()` for lifecycle events",
            "- Use `_logger.LogError(ex, \"message\")` for exception handling",
            "- Use `_logger.LogWarning()` for degraded-but-functional paths",
            "- Example: `private readonly ILogger<CartService> _logger;`",
            "",
            "**Exception handling:**",
            "- NEVER use empty catch blocks (`catch { }` or `catch (Exception) { }`)",
            "- Always log the exception or rethrow",
            "- Prefer `catch (SpecificException ex)` over `catch (Exception ex)`",
        ])

        # REQ-CS-601: Dockerfile context for .NET services
        has_dockerfile = any(
            Path(f).name.lower().startswith("dockerfile")
            for f in target_files
        )
        if has_dockerfile:
            csproj_name = ""
            if isinstance(svc_meta, dict):
                csproj_name = svc_meta.get("csproj_name", "")
            lines.extend([
                "",
                "**Dockerfile patterns for .NET:**",
                "- Multi-stage build: `dotnet/sdk` builder → `dotnet/runtime-deps` runtime (chiseled/distroless)",
                f"- Builder: `COPY {csproj_name or '*.csproj'} .` then `RUN dotnet restore`",
                "- Publish: `RUN dotnet publish -c release -o /app --self-contained true -p:PublishTrimmed=true`",
                "- Runtime: `COPY --from=builder /app .`",
                "- Set `ENV DOTNET_EnableDiagnostics=0` and `ENV ASPNETCORE_HTTP_PORTS=<port>`",
                "- Run as non-root: `USER 1000`",
                "- No HEALTHCHECK instruction — use gRPC health protocol instead",
            ])

        # REQ-CS-602: Proto file context for gRPC services
        has_proto = any(f.endswith(".proto") for f in target_files)
        if has_proto:
            lines.extend([
                "",
                "**Proto file patterns for C# gRPC:**",
                "- Use `syntax = \"proto3\";`",
                "- Define `package` matching the C# namespace convention",
                "- Service RPCs use `returns (ResponseType)` syntax",
                "- Messages use snake_case field names (C# codegen converts to PascalCase)",
                "- This is a service-specific proto, NOT a shared demo.proto",
            ])

        return "\n".join(lines)

    def strip_dependency_version(self, dep: str) -> str:
        """Strip version from NuGet dependency.

        Handles 'Package/1.0.0' and 'Package 1.0.0' formats.
        """
        if "/" in dep:
            return dep.split("/")[0].strip()
        # Space-separated: 'Grpc.AspNetCore 2.76.0'
        return dep.split()[0].strip() if dep.strip() else dep

    def get_import_syntax_guidance(self) -> str:
        """Return C# using rules for LLM prompts."""
        return (
            "Use ONLY these packages plus .NET BCL (System.*/Microsoft.*). Every\n"
            "type you reference MUST have a corresponding `using` directive.\n"
            "Use fully qualified namespace imports. Do NOT reference packages "
            "not listed above.\n"
        )

    def extract_import_lines(self, source: str) -> list[str]:
        """Extract using directives from C# source (REQ-PE-400)."""
        import re
        return [
            m.group(0)
            for m in re.finditer(r'^using\s+[\w.]+\s*;', source, re.MULTILINE)
        ]

    @property
    def stub_marker_text(self) -> str:
        """C# stub marker for skeleton fill prompts."""
        return '`throw new NotImplementedException()`'


def _derive_namespace(file_path: str) -> str:
    """Derive a C# namespace from a file path.

    Converts directory structure to dotted namespace.
    Strips directory components named ``src``, ``source``, ``lib`` (common
    in .NET project layouts like ``src/cartservice/src/cartstore/``).

    Examples::

        'src/cartservice/src/cartstore/RedisCartStore.cs' -> 'cartservice.cartstore'
        'src/MyApp/Services/UserService.cs' -> 'MyApp.Services'
        'Services/UserService.cs' -> 'Services'
    """
    from pathlib import PurePosixPath

    parts = PurePosixPath(file_path).parent.parts

    # Strip common non-namespace directory names
    skip = {"src", "source", "lib"}
    parts = tuple(p for p in parts if p.lower() not in skip)

    if not parts or parts == (".",):
        return ""

    return ".".join(parts)
