#!/data/data/com.termux/files/usr/bin/bash
# TheHand — start server in Termux
# Usage: bash scripts/start.sh [--port 8080]

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_DIR="$REPO_DIR/server"
PORT="${THEHAND_PORT:-8080}"

# Parse --port flag
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Acquire wake lock so Android does not kill the process mid-transcription
if command -v termux-wake-lock &>/dev/null; then
  echo "→ Acquiring termux-wake-lock..."
  termux-wake-lock
fi

echo "→ Starting TheHand server on port $PORT..."
echo "   Open in browser: http://localhost:$PORT"
echo "   From another device: http://$(hostname -I | awk '{print $1}'):$PORT"
echo "   Press Ctrl+C to stop."
echo ""

cd "$SERVER_DIR"
exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
