#!/data/data/com.termux/files/usr/bin/bash
# TheHand — Termux one-shot setup
# Run once: bash scripts/setup-termux.sh
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   TheHand — Termux Setup             ║"
echo "╚══════════════════════════════════════╝"
echo ""

# 1. System packages
echo "→ Installing system packages..."
pkg update -y && pkg upgrade -y
pkg install -y python ffmpeg clang cmake git

# 2. Python deps
echo "→ Installing Python packages..."
pip install -r "$REPO_DIR/server/requirements.txt"

# 3. whisper.cpp
if [ ! -f "$HOME/whisper.cpp/build/bin/whisper-cli" ] && [ ! -f "$HOME/whisper.cpp/build/bin/main" ]; then
  echo "→ Cloning whisper.cpp..."
  git clone https://github.com/ggml-org/whisper.cpp "$HOME/whisper.cpp"
  cd "$HOME/whisper.cpp"

  echo "→ Downloading small model (~466MB)..."
  bash models/download-ggml-model.sh small

  echo "→ Compiling whisper.cpp (ARM, no OpenMP)..."
  cmake -B build -DGGML_NO_OPENMP=ON
  cmake --build build -j"$(nproc)"
  cd "$REPO_DIR"
else
  echo "→ whisper.cpp already compiled, skipping."
fi

# 4. Build frontend
echo "→ Building React frontend..."
cd "$REPO_DIR/app"
if ! command -v node &>/dev/null; then
  echo "  ⚠  Node.js not found. Install from https://nodejs.org then re-run."
  echo "     Or build on a desktop and copy app/dist → server/dist manually."
else
  npm install
  npm run build
  echo "→ Copying dist to server/dist..."
  rm -rf "$REPO_DIR/server/dist"
  cp -r "$REPO_DIR/app/dist" "$REPO_DIR/server/dist"
fi

echo ""
echo "✅ Setup complete."
echo ""
echo "Start the server with:"
echo "  bash scripts/start.sh"
echo ""
