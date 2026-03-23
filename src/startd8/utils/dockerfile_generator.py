"""Deterministic Dockerfile generation — REQ-DFA-106.

Produces multi-stage Dockerfiles from 3-5 variables per language.
Templates extracted from ``LanguageProfile.build_project_context_section()``
literal patterns.
"""

from __future__ import annotations

from typing import Optional

_CSHARP_TEMPLATE = """\
# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM {builder_image} AS builder

WORKDIR /src
COPY {project_file} .
RUN dotnet restore

COPY . .
RUN dotnet publish -c release -o /app --self-contained true \\
    -p:PublishTrimmed=true -p:PublishSingleFile=true

FROM {runtime_image}
WORKDIR /app
COPY --from=builder /app .
ENV DOTNET_EnableDiagnostics=0
USER 65532:65532
EXPOSE {port}
ENTRYPOINT ["./{service_name}"]
"""

_GO_TEMPLATE = """\
# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM {builder_image} AS builder

ARG TARGETOS
ARG TARGETARCH
ARG SKAFFOLD_GO_GCFLAGS

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=${{TARGETOS}} GOARCH=${{TARGETARCH}} \\
    go build -ldflags="-s -w" \\
             -gcflags="${{SKAFFOLD_GO_GCFLAGS}}" \\
             -o /{service_name} .

FROM {runtime_image}
WORKDIR /src
COPY --from=builder /{service_name} /src/{service_name}
ENV GOTRACEBACK=single
EXPOSE {port}
ENTRYPOINT ["/src/{service_name}"]
"""

_JAVA_TEMPLATE = """\
# syntax=docker/dockerfile:1
FROM {builder_image} AS builder

WORKDIR /app
COPY build.gradle settings.gradle ./
COPY gradle/ gradle/
COPY gradlew .
RUN ./gradlew dependencies --no-daemon

COPY . .
RUN ./gradlew bootJar --no-daemon -x test

FROM {runtime_image}
WORKDIR /app
COPY --from=builder /app/build/libs/*.jar app.jar
USER 65532:65532
EXPOSE {port}
ENTRYPOINT ["java", "-jar", "app.jar"]
"""

_NODEJS_TEMPLATE = """\
# syntax=docker/dockerfile:1
FROM {builder_image} AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

COPY . .

FROM {runtime_image}
WORKDIR /app
COPY --from=builder /app .
USER 65532:65532
EXPOSE {port}
ENTRYPOINT ["node", "{entry_point}"]
"""

_PYTHON_TEMPLATE = """\
# syntax=docker/dockerfile:1
FROM {builder_image} AS builder

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

FROM {runtime_image}

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT={port}

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app .

USER 65532:65532
EXPOSE {port}
ENTRYPOINT ["python", "{entry_point}"]
"""

_TEMPLATES = {
    "csharp": _CSHARP_TEMPLATE,
    "go": _GO_TEMPLATE,
    "java": _JAVA_TEMPLATE,
    "nodejs": _NODEJS_TEMPLATE,
    "python": _PYTHON_TEMPLATE,
}

_DEFAULT_PORTS = {
    "csharp": 8080,
    "go": 8080,
    "java": 8080,
    "nodejs": 3000,
    "python": 8080,
}

_DEFAULT_BUILDER_IMAGES = {
    "csharp": "mcr.microsoft.com/dotnet/sdk:10.0",
    "go": "golang:1.25-alpine",
    "java": "eclipse-temurin:21-jdk",
    "nodejs": "node:20-alpine",
    "python": "python:3.12-slim",
}

_DEFAULT_RUNTIME_IMAGES = {
    "csharp": "mcr.microsoft.com/dotnet/runtime-deps:10.0-chiseled",
    "go": "gcr.io/distroless/static",
    "java": "eclipse-temurin:21-jre-alpine",
    "nodejs": "node:20-alpine",
    "python": "python:3.12-slim",
}


def generate_dockerfile(
    language_id: str,
    service_name: str,
    *,
    port: Optional[int] = None,
    entry_point: str = "",
    project_file: str = "",
    builder_image: str = "",
    runtime_image: str = "",
) -> Optional[str]:
    """Generate a multi-stage Dockerfile for the given language.

    Args:
        language_id: Language identifier (csharp, go, java, nodejs).
        service_name: Service/binary name for the ENTRYPOINT.
        port: Port to EXPOSE. Defaults to language-specific default.
        entry_point: Entry point file (Node.js: ``index.js``).
        project_file: Project file to restore first (C#: ``*.csproj``).
        builder_image: Override builder stage base image.
        runtime_image: Override runtime stage base image.

    Returns:
        Dockerfile content string, or None if language not supported.
    """
    template = _TEMPLATES.get(language_id)
    if template is None:
        return None

    return template.format(
        service_name=service_name,
        port=port or _DEFAULT_PORTS.get(language_id, 8080),
        entry_point=entry_point or "index.js",
        project_file=project_file or f"{service_name}.csproj",
        builder_image=builder_image or _DEFAULT_BUILDER_IMAGES.get(language_id, ""),
        runtime_image=runtime_image or _DEFAULT_RUNTIME_IMAGES.get(language_id, ""),
    )
