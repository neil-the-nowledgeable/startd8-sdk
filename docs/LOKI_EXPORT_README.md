# Loki Log Export Setup

This directory contains configuration files to export startd8 logs to a local Loki instance using Promtail.

## Files

- `promtail-config.yml` - Promtail configuration for parsing and exporting JSON logs
- `docker-compose.loki-stack.yml` - Docker Compose file for Loki, Promtail, and Grafana
- `scripts/start-loki-stack.sh` - Quick start script
- `docs/LOKI_SETUP_GUIDE.md` - Detailed setup and troubleshooting guide

## Quick Start

```bash
# Start the stack
./scripts/start-loki-stack.sh

# Or manually:
docker-compose -f docker-compose.loki-stack.yml up -d
```

## Access Points

- **Grafana**: http://localhost:3000 (Explore → Loki)
- **Loki API**: http://localhost:3100
- **Promtail**: http://localhost:9080

## Query Examples

**All logs:**
```logql
{job="startd8"}
```

**Error logs:**
```logql
{job="startd8", level="ERROR"}
```

**Logs by logger:**
```logql
{job="startd8", logger="startd8.agents"}
```

**Find by correlation ID:**
```logql
{job="startd8"} | json | correlation_id="req-123"
```

## Stopping

```bash
docker-compose -f docker-compose.loki-stack.yml down
```

For more details, see [docs/LOKI_SETUP_GUIDE.md](docs/LOKI_SETUP_GUIDE.md)
