#!/bin/bash

echo "🚀 Starting ExtremeGiveawaysDC..."

# Create data directory if it doesn't exist
mkdir -p ./data

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create a .env file with your configuration."
    exit 1
fi

# Load environment variables
export $(grep -v '^#' .env | xargs)

# Validate required variables
required_vars=(
    "DISCORD_BOT_TOKEN"
    "FLASK_SECRET_KEY"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: $var is not set in .env file"
        exit 1
    fi
done

# Build and start containers
echo "📦 Building and starting containers..."
docker-compose up --build -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Deployment successful!"
    echo "🌐 Web Interface: http://localhost:8080"
    echo "🤖 Bot is running"
    echo ""
    echo "📋 Next steps:"
    echo "1. Go to http://localhost:8080"
    echo "2. Login with Discord"
    echo "3. Configure your Discord OAuth app with redirect URI: http://localhost:8080/callback"
else
    echo "❌ Deployment failed!"
    docker-compose logs
    exit 1
fi