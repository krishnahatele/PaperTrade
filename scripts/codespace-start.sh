#!/usr/bin/env bash
# Start MarketOS inside a GitHub Codespace (database in Docker, API + web as processes).
# Usage:  bash scripts/codespace-start.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

[ -f .env ] || cp .env.example .env
docker compose up -d db

command -v uv >/dev/null || pip install -q uv

API_URL="https://${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
WEB_URL="https://${CODESPACE_NAME}-3000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"

pkill -f "next start" 2>/dev/null || true
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

echo "==> Backend"
cd "$ROOT/apps/api"
uv sync -q
uv run alembic upgrade head
MARKETOS_CORS_ORIGINS="[\"$WEB_URL\"]" nohup uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$HOME/api.log" 2>&1 &
sleep 6
curl -sf localhost:8000/health >/dev/null && echo "API is up (log: ~/api.log)" || { echo "API failed to start:"; tail -30 "$HOME/api.log"; exit 1; }
gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" >/dev/null 2>&1 \
  || echo "!! Set port 8000 to Public in the Ports tab (right-click 8000 > Port Visibility > Public)"

echo "==> Frontend (first build takes a few minutes)"
cd "$ROOT/apps/web"
npm ci --silent
NEXT_PUBLIC_API_URL="$API_URL" npm run build
echo
echo "Open: $WEB_URL"
npx next start -p 3000
