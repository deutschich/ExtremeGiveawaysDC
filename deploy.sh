#!/bin/bash

# Deployment script for ExtremeGiveawaysDC
set -e

echo "🚀 Starting deployment of ExtremeGiveawaysDC..."

# Create data directory if it doesn't exist
mkdir -p ./data

# Check for .env file
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create a .env file with your configuration."
    exit 1
fi

# Load environment variables
source .env

# Validate required variables
required_vars=(
    "DISCORD_BOT_TOKEN"
    "DISCORD_CLIENT_ID"
    "DISCORD_CLIENT_SECRET"
    "DISCORD_REDIRECT_URI"
    "FLASK_SECRET_KEY"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: $var is not set in .env file"
        exit 1
    fi
done

# Pull latest images
echo "📦 Pulling latest images from GHCR..."
docker pull ghcr.io/deutschich/extremegiveawaysdc-bot:main
docker pull ghcr.io/deutschich/extremegiveawaysdc-web:main

# Stop and remove existing containers
echo "🛑 Stopping existing containers..."
docker compose down || true

# Start new containers
echo "🚀 Starting new containers..."
docker compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check if services are running
if docker compose ps | grep -q "Up"; then
    echo "✅ Deployment successful!"
    echo "🌐 Web Interface: http://localhost:8080"
    echo "🤖 Bot is running"
else
    echo "❌ Deployment failed!"
    docker compose logs
    exit 1
fi