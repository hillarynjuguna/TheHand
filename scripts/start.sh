#!/data/data/com.termux/files/usr/bin/bash
# TheHand — start server in Termux
# Usage: bash scripts/start.sh [--port 8080]

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_DIR="$REPO_DIR/server"
PORT="${THEHAND_PORT:-8080}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if command -v termux-wake-lock &>/dev/null; then
  echo "→ Acquiring termux-wake-lock..."
  termux-wake-lock
fi

# Get local IP (Termux-safe)
LOCAL_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"

echo "→ Starting TheHand on port $PORT..."
echo "   Local:  http://localhost:$PORT"
if [ -n "$LOCAL_IP" ]; then
  echo "   Network: http://$LOCAL_IP:$PORT"
fi
echo "   Press Ctrl+C to stop."
echo ""

cd "$SERVER_DIR"
exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
