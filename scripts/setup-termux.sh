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

# 1. System packages (rust required for pydantic-core, nodejs for frontend build)
echo "→ Installing system packages..."
pkg update -y && pkg upgrade -y
pkg install -y python ffmpeg clang cmake git nodejs rust

# 2. Python deps
# ANDROID_API_LEVEL required by maturin when building pydantic-core from source
echo "→ Installing Python packages..."
export ANDROID_API_LEVEL=24
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
npm install --legacy-peer-deps
npm run build
echo "→ Copying dist to server/dist..."
rm -rf "$REPO_DIR/server/dist"
cp -r "$REPO_DIR/app/dist" "$REPO_DIR/server/dist"

echo ""
echo "✅ Setup complete."
echo ""
echo "Start the server with:"
echo "  bash scripts/start.sh"
echo ""
