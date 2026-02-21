#!/bin/bash
# =============================================================
# CalledIt Backend — Deploy / Update Script
# Run this each time you want to pull latest code and redeploy.
# Usage: ./deploy/deploy.sh
# =============================================================

set -e

APP_DIR="/opt/calledit"
cd "$APP_DIR"

echo "=== CalledIt Deploy ==="

# 1. Pull latest code
echo "[1/4] Pulling latest code..."
git pull origin main

# 2. Rebuild and restart containers
echo "[2/4] Building and restarting containers..."
docker compose -f docker-compose.prod.yml up -d --build

# 3. Clean up old images
echo "[3/4] Cleaning up old Docker images..."
docker image prune -f

# 4. Health check
echo "[4/4] Waiting for health check..."
sleep 5
if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "Health check PASSED"
else
    echo "Health check FAILED — check logs with: docker compose -f docker-compose.prod.yml logs -f app"
    exit 1
fi

echo ""
echo "=== Deploy complete! ==="
