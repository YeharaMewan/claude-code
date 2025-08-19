#!/bin/bash
set -e

echo "🚀 Starting HR Agent Application"
echo "================================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "📝 Please edit .env and add your OPENAI_API_KEY"
    echo "Then run this script again."
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Load environment variables
source .env

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your_openai_api_key_here" ]; then
    echo "❌ OPENAI_API_KEY is not set in .env file"
    echo "Please edit .env and add your OpenAI API key."
    exit 1
fi

echo "✅ Environment variables loaded"

# Build and start services
echo "🔨 Building and starting services..."
docker-compose down --remove-orphans
docker-compose up --build -d

echo "⏳ Waiting for services to start..."
sleep 30

# Check service health
echo "🔍 Checking service health..."

# Check database
if docker-compose exec -T db pg_isready -U hruser -d hrdb > /dev/null 2>&1; then
    echo "✅ Database is ready"
else
    echo "❌ Database is not ready"
    echo "Check logs: docker-compose logs db"
fi

# Check API
if curl -f http://localhost:5000/api/health > /dev/null 2>&1; then
    echo "✅ API server is ready"
else
    echo "❌ API server is not ready"
    echo "Check logs: docker-compose logs api"
fi

# Check web server
if curl -f http://localhost:3000 > /dev/null 2>&1; then
    echo "✅ Web server is ready"
else
    echo "❌ Web server is not ready"
    echo "Check logs: docker-compose logs web"
fi

echo ""
echo "🎉 HR Agent Application is starting up!"
echo "================================="
echo "📱 Web Interface: http://localhost:3000"
echo "🔧 API Health: http://localhost:5000/api/health"
echo "📊 View logs: docker-compose logs -f"
echo "🛑 Stop services: docker-compose down"
echo ""
echo "If you encounter any issues, check the logs with:"
echo "  docker-compose logs [service_name]"
echo ""

# Run integration tests if requested
if [ "$1" = "--test" ]; then
    echo "🧪 Running integration tests..."
    python3 test_integration.py --wait-for-services
fi