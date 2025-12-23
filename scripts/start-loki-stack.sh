#!/bin/bash
# Start Loki stack with Promtail for startd8 log export

set -e

echo "🚀 Starting Loki stack for startd8 log export..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker first."
    exit 1
fi

# Ensure log directories exist
echo "📁 Ensuring log directories exist..."
mkdir -p ~/.startd8/logs
mkdir -p ./.startd8/logs

# Check if docker-compose file exists
if [ ! -f "docker-compose.loki-stack.yml" ]; then
    echo "❌ Error: docker-compose.loki-stack.yml not found in current directory"
    exit 1
fi

# Check if promtail config exists
if [ ! -f "promtail-config.yml" ]; then
    echo "❌ Error: promtail-config.yml not found in current directory"
    exit 1
fi

# Start the stack
echo "🐳 Starting Docker containers..."
docker-compose -f docker-compose.loki-stack.yml up -d

# Wait a moment for services to start
sleep 3

# Check service status
echo ""
echo "📊 Service Status:"
docker-compose -f docker-compose.loki-stack.yml ps

echo ""
echo "✅ Loki stack started!"
echo ""
echo "📝 Access points:"
echo "   • Grafana: http://localhost:3000"
echo "   • Loki API: http://localhost:3100"
echo "   • Promtail: http://localhost:9080"
echo ""
echo "📋 Useful commands:"
echo "   • View Promtail logs: docker logs startd8-promtail"
echo "   • View Loki logs: docker logs startd8-loki"
echo "   • Stop stack: docker-compose -f docker-compose.loki-stack.yml down"
echo "   • Restart Promtail: docker restart startd8-promtail"
echo ""
echo "🔍 To query logs in Grafana:"
echo "   1. Open http://localhost:3000"
echo "   2. Go to Explore → Select Loki"
echo "   3. Query: {job=\"startd8\"}"
echo ""
