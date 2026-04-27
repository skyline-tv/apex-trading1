#!/bin/bash
# ─────────────────────────────────────────────
#  APEX Trading Agent — Start Everything
# ─────────────────────────────────────────────

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${GREEN}  ⚡ APEX AI Trading Agent${NC}"
echo "  ─────────────────────────"
echo ""

# ── 1. Check .env ────────────────────────────
if [ ! -f "$BACKEND/.env" ]; then
  echo -e "${RED}  ✗ backend/.env not found${NC}"
  exit 1
fi

KEY=$(grep OPENAI_API_KEY "$BACKEND/.env" | cut -d= -f2 | tr -d '[:space:]')
if [ -z "$KEY" ] || [ "$KEY" = "your_openai_api_key_here" ]; then
  echo -e "${RED}  ✗ OPENAI_API_KEY is not set in backend/.env${NC}"
  echo "  Edit backend/.env and paste your key, then run this script again."
  exit 1
fi
echo -e "${GREEN}  ✓ API key found${NC}"

# ── 2. Backend deps ──────────────────────────
echo -e "${YELLOW}  → Installing Python dependencies…${NC}"
cd "$BACKEND"
pip install -r requirements.txt -q

# ── 3. Frontend deps ─────────────────────────
echo -e "${YELLOW}  → Installing Node dependencies…${NC}"
cd "$FRONTEND"
if [ ! -d node_modules ]; then
  npm install --silent
else
  echo "  (node_modules already present, skipping)"
fi

# ── 4. Launch both ───────────────────────────
echo ""
echo -e "${GREEN}  Starting backend  → http://localhost:8000${NC}"
echo -e "${GREEN}  Starting frontend → http://localhost:3000${NC}"
echo ""
echo "  Press Ctrl+C to stop both servers."
echo ""

# Start backend in background
cd "$BACKEND"
uvicorn app:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# Give backend a moment to boot
sleep 2

# Start frontend in foreground (so Ctrl+C kills everything)
cd "$FRONTEND"
npm run dev &
FRONTEND_PID=$!

# Trap Ctrl+C and kill both
trap "echo ''; echo 'Shutting down…'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

wait $FRONTEND_PID
