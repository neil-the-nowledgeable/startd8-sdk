# Loki Log Export Setup Guide

This guide explains how to set up Promtail to automatically export startd8 logs to a local Loki instance.

## Prerequisites

- Docker and Docker Compose installed
- Loki instance running locally (or use the provided docker-compose file)

## Quick Start

### Option 1: Use Quick Start Script (Easiest)

1. **Run the start script:**
   ```bash
   ./scripts/start-loki-stack.sh
   ```

   This script will:
   - Check Docker is running
   - Create log directories if needed
   - Start Loki, Promtail, and Grafana
   - Display service status and access URLs

### Option 2: Use Docker Compose (Manual)

1. **Start Loki and Promtail stack:**
   ```bash
   docker-compose -f docker-compose.loki-stack.yml up -d
   ```

2. **Verify services are running:**
   ```bash
   docker ps | grep -E "loki|promtail|grafana"
   ```

3. **Check Promtail logs:**
   ```bash
   docker logs startd8-promtail
   ```

4. **Access Grafana:**
   - Open http://localhost:3000
   - Logs are available in Explore → Select Loki data source

### Option 2: Standalone Promtail (Loki Already Running)

If you already have Loki running:

1. **Update Promtail config** (`promtail-config.yml`):
   ```yaml
   clients:
     - url: http://localhost:3100/loki/api/v1/push  # Your Loki endpoint
   ```

2. **Run Promtail:**
   ```bash
   docker run -d \
     --name startd8-promtail \
     -v ${HOME}/.startd8/logs:/logs:ro \
     -v $(pwd)/promtail-config.yml:/etc/promtail/promtail-config.yml:ro \
     grafana/promtail:latest \
     -config.file=/etc/promtail/promtail-config.yml
   ```

## Configuration Details

### Log File Locations

Promtail watches these directories:
- `~/.startd8/logs/*.log` (user config directory)
- `./.startd8/logs/*.log` (project data directory)

### Log Format

startd8 logs are in JSON format with the following structure:
```json
{
  "timestamp": "2025-12-22T10:30:45.123Z",
  "level": "ERROR",
  "logger": "startd8.agents",
  "message": "API call failed",
  "exception": "Traceback...",
  "exception_type": "APIConnectionError",
  "exception_message": "Connection error",
  "trace_id": "abc123...",
  "correlation_id": "req-456...",
  "agent_name": "claude",
  "source": {
    "file": "/path/to/file.py",
    "function": "function_name",
    "line": 123
  }
}
```

### Promtail Pipeline

The Promtail configuration:
1. **Parses JSON** - Extracts structured fields from log entries
2. **Extracts Labels** - Creates Loki labels from `level`, `logger`, `exception_type`, `agent_name`
3. **Sets Timestamp** - Uses the `timestamp` field from JSON
4. **Outputs Message** - Sends the full JSON as the log line

### Labels (Low Cardinality)

Labels are used for filtering in Loki queries. Only low-cardinality fields are used as labels:
- `level` - Log level (ERROR, INFO, WARNING, etc.)
- `logger` - Logger name (startd8.agents, startd8.framework, etc.)
- `exception_type` - Exception class name
- `agent_name` - Agent name (if available)

High-cardinality fields (like `trace_id`, `correlation_id`) are kept in the log message JSON, not as labels.

## Querying Logs in Grafana

### Basic Queries

**All startd8 logs:**
```logql
{job="startd8"}
```

**Error logs only:**
```logql
{job="startd8", level="ERROR"}
```

**Logs from specific logger:**
```logql
{job="startd8", logger="startd8.agents"}
```

**Logs with specific exception type:**
```logql
{job="startd8", exception_type="APIConnectionError"}
```

### Advanced Queries

**Find logs by correlation ID:**
```logql
{job="startd8"} | json | correlation_id="req-456"
```

**Find logs by trace ID:**
```logql
{job="startd8"} | json | trace_id="abc123"
```

**Error logs with traceback:**
```logql
{job="startd8", level="ERROR"} | json | exception != ""
```

**Recent errors from specific agent:**
```logql
{job="startd8", level="ERROR", agent_name="claude"} | json
```

## Troubleshooting

### Promtail Not Reading Logs

1. **Check file permissions:**
   ```bash
   ls -la ~/.startd8/logs/
   ```
   Promtail needs read access to the log files.

2. **Verify log files exist:**
   ```bash
   ls -la ~/.startd8/logs/*.log
   ```

3. **Check Promtail logs:**
   ```bash
   docker logs startd8-promtail
   ```

### Logs Not Appearing in Loki

1. **Verify Loki is running:**
   ```bash
   curl http://localhost:3100/ready
   ```
   Should return: `ready`

2. **Check Promtail can reach Loki:**
   ```bash
   docker exec startd8-promtail wget -O- http://loki:3100/ready
   ```

3. **Verify Promtail config:**
   ```bash
   docker exec startd8-promtail cat /etc/promtail/promtail-config.yml
   ```

4. **Check if log files exist:**
   ```bash
   # User config logs
   ls -la ~/.startd8/logs/*.log
   
   # Project data logs (if directory exists)
   ls -la ./.startd8/logs/*.log 2>/dev/null || echo "Project log directory doesn't exist yet"
   ```
   
   Note: If the project log directory doesn't exist, Promtail will skip it (no error). Logs will only appear once you run workflows that create logs.

5. **Verify Promtail is reading files:**
   ```bash
   docker logs startd8-promtail | grep -i "error\|warn\|started"
   ```

### Position File Issues

If Promtail restarts and misses logs, check the positions file:
```bash
docker exec startd8-promtail cat /tmp/positions.yaml
```

To reset and re-read all logs:
```bash
docker exec startd8-promtail rm /tmp/positions.yaml
docker restart startd8-promtail
```

## Environment Variables

You can customize the setup using environment variables:

```bash
# Custom Loki endpoint
export LOKI_ENDPOINT=http://localhost:3100/loki/api/v1/push

# Custom log directory
export STARTD8_LOG_DIR=/custom/path/to/logs
```

Then update `promtail-config.yml` accordingly.

## Stopping the Stack

```bash
docker-compose -f docker-compose.loki-stack.yml down
```

To also remove volumes (deletes stored logs):
```bash
docker-compose -f docker-compose.loki-stack.yml down -v
```

## Next Steps

1. **Set up Grafana Dashboards** - Create dashboards for error monitoring
2. **Configure Alerts** - Set up alerts for critical errors
3. **Explore LogQL** - Learn advanced LogQL queries for analysis
4. **Integrate with Traces** - Connect logs with traces using trace_id

## Additional Resources

- [Promtail Documentation](https://grafana.com/docs/loki/latest/clients/promtail/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/logql/)
- [Grafana Loki Documentation](https://grafana.com/docs/loki/latest/)
