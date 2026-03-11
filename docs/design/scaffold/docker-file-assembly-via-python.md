# Dockerfile Assembly via Python — Research & Best Practices

> **Purpose:** Organized reference notes for understanding how to create and manage Dockerfiles in a Python context.
> Cross-synthesized from multiple sources for use in tooling design or automated Dockerfile generation.

---

## Sources

| Source | URL | Validity |
|---|---|---|
| TestDriven.io — Docker Best Practices for Python Developers | <https://testdriven.io/blog/docker-best-practices/> | ✅ Live, comprehensive |
| CyberPanel — Python Docker Image: Proven Hacks for Best Builds in 2026 | <https://cyberpanel.net/blog/python-docker-image> | ✅ Live, practical guide |
| Google AI Overview — Key Dockerfile Best Practices | (AI-generated summary) | ✅ Validates sources above |

---

## Key Insight Areas

1. [Base Image Selection](#1-base-image-selection)
2. [Multi-Stage Builds](#2-multi-stage-builds)
3. [Layer Ordering & Caching](#3-layer-ordering--caching)
4. [Layer Minimization & Cleanup](#4-layer-minimization--cleanup)
5. [Security Practices](#5-security-practices)
6. [CMD vs ENTRYPOINT](#6-cmd-vs-entrypoint)
7. [The .dockerignore File](#7-the-dockerignore-file)
8. [Health Checks](#8-health-checks)
9. [Secrets Management](#9-secrets-management)
10. [Runtime & Operational Concerns](#10-runtime--operational-concerns)
11. [Dev Workflow Patterns](#11-dev-workflow-patterns)
12. [Reference: Gold Standard Dockerfile](#12-reference-gold-standard-dockerfile)

---

## 1. Base Image Selection

**Decision matrix for Python base images:**

| Image | Size | Best For | Caveats |
|---|---|---|---|
| `python:3.12` (full) | ~1GB | Dev / debugging | Too large for production |
| `python:3.12-slim` | ~130MB | **Most production cases** | Recommended default |
| `python:3.12-alpine` | ~52MB | Size-critical scenarios | May break binary packages; 50× slower builds |
| `gcr.io/distroless/python3` | Minimal | High-security production | Hard to debug |
| `python:3.12-bookworm` | ~130MB | Debian-stable environments | Same size as slim |

> **Rule:** When in doubt, start with `python:3.12-slim`. Avoid Alpine unless you have specific reasons and no C-extension packages.

**Why not Alpine?**

- Many Python packages need compiled C extensions
- Alpine uses `musl` libc vs `glibc` — many wheels don't ship Alpine-compatible binaries
- You end up compiling from source → longer builds → potentially larger images

**Keep base images updated:** When a new patch version is released (e.g., `3.11.8-slim` → `3.12.2-slim`), pull and rebuild to capture security patches.

---

## 2. Multi-Stage Builds

Multi-stage builds are the **single biggest size/security win** available. Separate build tooling from the runtime image.

**Core pattern — Wheels approach (TestDriven.io):**

```dockerfile
# --- Stage 1: Build ---
FROM python:3.12-slim as builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# --- Stage 2: Runtime ---
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache /wheels/*
```

**Variant — Virtualenv approach (used in existing scaffold draft):**

```dockerfile
# --- Stage 1: Build ---
FROM python:3.11-slim as builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage 2: Runtime ---
FROM python:3.11-slim
RUN groupadd -r appuser && useradd -r -g appuser appuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY . .
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER appuser
CMD ["python", "main.py"]
```

**Measured size impact:**

| Build Type | Image Size |
|---|---|
| Single-stage (with gcc) | ~259 MB |
| Multi-stage | ~156 MB |
| Data science single-stage | ~969 MB |
| Data science multi-stage | ~357 MB |

> **Insight for tooling:** When generating Dockerfiles programmatically, always emit multi-stage unless user explicitly opts out. The virtualenv variant is cleaner; the wheels variant is lighter.

---

## 3. Layer Ordering & Caching

Docker caches each instruction as a layer. When a layer changes, **all subsequent layers are invalidated**. This means ordering matters enormously for build speed.

**Anti-pattern:**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY sample.py .         # ❌ Changes often — invalidates pip install below
COPY requirements.txt .
RUN pip install -r requirements.txt
```

**Correct pattern:**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .  # ✅ Stable — cached until deps change
RUN pip install -r requirements.txt
COPY sample.py .         # ✅ Volatile code goes last
```

**Rules:**

1. Instructions likely to change → push toward **bottom**
2. System dependencies (`apt-get`) → **top** (change rarely)
3. `requirements.txt` install → **before** app code copy
4. Always combine `RUN apt-get update && apt-get install` — never split them

---

## 4. Layer Minimization & Cleanup

Only `RUN`, `COPY`, and `ADD` create new layers with size. Every other instruction (e.g., `ENV`, `WORKDIR`) is essentially free size-wise.

**Combine apt installs:**

```dockerfile
# ❌ Two layers
RUN apt-get update
RUN apt-get install -y netcat

# ✅ One layer, with cleanup in same step
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    netcat \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
```

**Why cleanup must be in the same `RUN`:** If you clean up in a separate layer, the original layer (with the cache data) is still baked into the image. The cleanup must happen in the same instruction that created the files.

**Audit your layers:**

```bash
docker history <image-id>
```

> **Note:** Focus optimization energy on stages 1-3 (base image, multi-stage, ordering). Over-optimizing individual commands yields diminishing returns.

---

## 5. Security Practices

### 5a. Run as Non-Root User

By default Docker containers run as `root` — a serious security risk if an attacker gains container access.

```dockerfile
# Simple approach
RUN addgroup --system app && adduser --system --group app
USER app

# Hardened approach (no home dir, no shell)
RUN addgroup --gid 1001 --system app && \
    adduser --no-create-home --shell /bin/false \
            --disabled-password --uid 1001 --system --group app
USER app
```

Verify: `docker run -i <image> id` → should show `uid=1001(app)`

### 5b. COPY vs ADD

Always prefer `COPY` over `ADD`.

| Instruction | Does What |
|---|---|
| `COPY` | Copies local files only — predictable |
| `ADD` | Copies files **+** extracts archives **+** downloads URLs — implicit "magic" |

`ADD`'s hidden behaviors can introduce security issues. Only use `ADD` if you specifically need archive extraction.

### 5c. Scan Images for Vulnerabilities

```bash
# Trivy (recommended)
trivy image yourname/myflask:1.0.0

# Grype
grype yourname/myflask:1.0.0
```

Integrate into CI pipeline so catches happen before deployment.

### 5d. Pin Image Versions

```dockerfile
# ❌ Mutable — unpredictable
FROM python:latest

# ✅ Pinned — reproducible
FROM python:3.12.2-slim
```

---

## 6. CMD vs ENTRYPOINT

Both start the container process, but behave differently when overridden at `docker run` time.

| | `CMD` | `ENTRYPOINT` |
|---|---|---|
| Overridable? | Yes — any `docker run` argument replaces it | Only with `--entrypoint` flag |
| Best for | Default arguments / flexible defaults | Fixed executable that always runs |
| Shell wrapping | Shell form strings wrap in `/bin/sh -c` | Same — prefer exec (array) form |

**Always use exec (array) form — not shell (string) form:**

```dockerfile
# ❌ Shell form — CTRL-C won't kill process; signals not forwarded
CMD "gunicorn -w 4 main:app"

# ✅ Exec form — proper PID 1, signal handling works
CMD ["gunicorn", "-w", "4", "main:app"]
```

**Combined pattern — fixed binary with configurable default args:**

```dockerfile
ENTRYPOINT ["gunicorn", "config.wsgi", "-w"]
CMD ["4"]
# docker run <img>     → gunicorn config.wsgi -w 4
# docker run <img> 8   → gunicorn config.wsgi -w 8
```

---

## 7. The .dockerignore File

Reduces build context size and prevents secrets from accidentally entering the image.

```text
# .dockerignore
__pycache__/
*.pyc
*.pyo
*.pyd
.env
.git
.vscode
.idea
venv/
.pytest_cache/
**/.aws
**/.ssh
```

> **Security insight:** Even if you don't `COPY` these explicitly, a `COPY . .` will include them. Always maintain `.dockerignore`.

---

## 8. Health Checks

`HEALTHCHECK` lets Docker (and orchestrators) know if the container is *actually healthy*, not just running.

```dockerfile
HEALTHCHECK CMD curl --fail http://localhost:8000 || exit 1
```

In Docker Compose:

```yaml
healthcheck:
  test: curl --fail http://localhost:8000 || exit 1
  interval: 10s
  timeout: 10s
  start_period: 10s
  retries: 3
```

**Options:**

- `interval`: How often to run the check
- `timeout`: Max wait for a response
- `start_period`: Grace period before checks begin (useful for slow startup)
- `retries`: Failures before marking `unhealthy`

Inspect health state: `docker inspect --format "{{json .State.Health}}" <container-id>`

> Note: If using Kubernetes or ECS, those platforms have their own liveness/readiness probes — prefer those over `HEALTHCHECK`.

---

## 9. Secrets Management

**Never bake secrets into images:**

```dockerfile
# ❌ Terrible — secret baked into layer history
FROM python:3.12-slim
ENV DATABASE_PASSWORD "SuperSecretSauce"
```

| Method | Safety Level | How |
|---|---|---|
| Runtime env vars | Low | `docker run -e KEY=val` |
| `.env` file via Compose | Medium | `env_file: .env` in compose.yaml |
| Build-time `ARG` | Low (visible in `docker history`) | `--build-arg KEY=val` |
| Multi-stage build secrets | High | Build secret only in temp stage, doesn't persist |
| Docker Secrets / K8s Secrets | Highest | Orchestration-native |
| Vault / AWS KMS + shared volume | High | External secret store |

**BuildKit secrets (best for build-time use):**

```dockerfile
# syntax = docker/dockerfile:1.2
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

---

## 10. Runtime & Operational Concerns

### One Process Per Container

Run a single service per container. Benefits:

- **Scaling:** Scale individual services independently
- **Reuse:** Share database containers without bundling extra services
- **Logging:** Simpler, decoupled log streams
- **Debugging:** Smaller blast radius

### Resource Limits

```bash
docker run --cpus=2 -m 512m <image>
```

Or in Compose:

```yaml
deploy:
  resources:
    limits:
      cpus: 2
      memory: 512M
    reservations:
      cpus: 1
      memory: 256M
```

### Log to stdout/stderr

Never write logs to files inside a container. Write to `stdout`/`stderr` and let the Docker daemon route them to your logging backend (CloudWatch, Papertrail, etc.).

### Cache pip to Docker Host

```bash
docker run -v $HOME/.cache/pip-docker/:/root/.cache/pip ...
```

Or with BuildKit:

```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

### Add Metadata Labels

```dockerfile
LABEL maintainer="team@example.com" \
      version="1.0.0" \
      description="My Python service"
```

### Virtual Environments in Containers

You generally **don't need** a venv in a container (the container itself is the isolation layer). However, venvs in multi-stage builds are useful for cleanly copying the installed packages into the final stage without bringing build tools along.

---

## 11. Dev Workflow Patterns

### Hot Reload (bind mount)

```bash
docker run -it --rm -p 8000:8000 \
  -v "$PWD/app":/app \
  -w /app \
  python:3.12-slim \
  bash -lc "pip install -r requirements.txt && flask --app app run --host 0.0.0.0 --port 8000 --debug"
```

### Docker Compose Dev Config

```yaml
# compose.yaml
services:
  web:
    image: python:3.12-slim
    working_dir: /app
    command: bash -lc "pip install -r requirements.txt && flask --app app run --host 0.0.0.0 --port 8000 --debug"
    ports:
      - "8000:8000"
    volumes:
      - ./app:/app
```

### Automated Generation

```bash
docker init
```

Docker's built-in scaffolding command — scans your project and generates a `Dockerfile` and `.dockerignore` following current best practices.

### Quick Command Cheatsheet

```bash
docker pull python:3.12-slim
docker run -it --rm python:3.12-slim python      # interactive REPL
docker build -t myapp:latest .
docker run -p 8000:8000 myapp:latest
docker images
docker history <image-id>                         # inspect layers + sizes
docker image prune                                # clean dangling images
trivy image myapp:latest                          # vulnerability scan
```

---

## 12. Reference: Gold Standard Dockerfile

This is the "opinionated best practice" Dockerfile for a production Python service, combining all of the above recommendations:

```dockerfile
# --- Stage 1: Build ---
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System build deps — in same RUN to keep layer clean
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Deps before source — maximizes cache reuse
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


# --- Stage 2: Runtime ---
FROM python:3.12-slim

# Metadata
LABEL maintainer="team@example.com"

# Non-root user — principle of least privilege
RUN groupadd --gid 1001 --system appuser && \
    useradd --no-create-home --shell /bin/false \
            --uid 1001 --system --gid 1001 appuser

WORKDIR /app

# Install only pre-built wheels — no build tooling needed
COPY --from=builder /app/wheels /wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache /wheels/* && rm -rf /wheels

# Copy app source last (most likely to change)
COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Run as non-root
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Exec form — proper signal handling, PID 1 is the process
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
```

**Companion `.dockerignore`:**

```text
__pycache__/
*.pyc
*.pyo
*.pyd
.env
.git
.vscode
.idea
venv/
.pytest_cache/
**/.aws
**/.ssh
*.log
dist/
build/
```

---

## Summary: Priority-Ordered Best Practice Checklist

Use this when reviewing or generating a Dockerfile for Python:

| Priority | Practice | Impact |
|---|---|---|
| 🔴 Critical | Use `python:X.Y-slim` or versioned tag — never `:latest` | Reproducibility, security |
| 🔴 Critical | Multi-stage build | Size, security |
| 🔴 Critical | Non-root `USER` | Security |
| 🔴 Critical | `.dockerignore` covering `.env`, `.git`, `__pycache__` | Security, build speed |
| 🟠 High | `COPY requirements.txt` before `COPY . .` | Build cache efficiency |
| 🟠 High | Combine `apt-get update && install` with cleanup in one `RUN` | Image size |
| 🟠 High | Exec form for `CMD`/`ENTRYPOINT` | Signal handling |
| 🟠 High | Never hardcode secrets — use runtime env or secrets management | Security |
| 🟡 Medium | `HEALTHCHECK` instruction | Observability |
| 🟡 Medium | `LABEL` metadata | Maintainability |
| 🟡 Medium | Log to `stdout`/`stderr` only | Operational simplicity |
| 🟢 Nice-to-have | Pin CPU/memory limits | Resource safety |
| 🟢 Nice-to-have | `docker init` for new projects | Developer experience |
| 🟢 Nice-to-have | Vulnerability scan in CI (`trivy`) | Supply chain security |
