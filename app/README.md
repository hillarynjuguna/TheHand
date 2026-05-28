# TheHand — Local AI Transcription Wrapper

> **Paste a link. Get clean text. Zero cloud. Zero friction.**

TheHand is a beautiful, privacy-first web UI for running AI-powered transcription entirely on your own device — no API keys, no subscriptions, no data ever leaving your phone or computer.

Built on top of **whisper.cpp** (OpenAI's Whisper model, compiled in C++ for ARM), it chains together `yt-dlp` → `ffmpeg` → `whisper.cpp` into a single pipeline served locally via FastAPI. The frontend is a polished React + TypeScript app that runs in any browser on your local network.

---

## What it does

- Paste any YouTube, TikTok, Instagram, podcast, or audio URL — it downloads, converts, and transcribes automatically
- Upload a local audio or video file directly from the browser
- Watch the pipeline run in real time (yt-dlp → ffmpeg → whisper.cpp)
- Export transcripts as plain text, SRT subtitles, VTT web captions, or timestamped JSON
- Choose from multiple Whisper model sizes (tiny 75MB → large-v3 3GB) to balance speed vs accuracy
- Works in 99 languages with automatic language detection

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite 7, Tailwind CSS v3, shadcn/ui, GSAP |
| UI Components | 40+ Radix UI primitives via shadcn |
| Animations | GSAP + ScrollTrigger, custom organic canvas shader |
| Backend | FastAPI (Python), Uvicorn |
| Transcription | whisper.cpp (C++ port of OpenAI Whisper) |
| Audio download | yt-dlp (1000+ supported sites) |
| Audio conversion | ffmpeg (any format → 16kHz mono WAV) |

---

## Running it on your phone (Termux)

This is the primary use case — running the full stack on Android via **Termux**, then opening the UI in your phone's browser.

### Prerequisites
- Android phone with [Termux](https://f-droid.org/packages/com.termux/) installed (use F-Droid, not Play Store)
- ~600MB free storage for the small model
- ~850MB RAM free while transcribing

### 1. Install system dependencies

```bash
pkg update && pkg upgrade
pkg install python ffmpeg clang cmake git
```

### 2. Install Python packages

```bash
pip install yt-dlp fastapi uvicorn python-multipart websockets
```

### 3. Clone and build whisper.cpp

```bash
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp

# Download the small model (466MB, good balance of speed/accuracy)
bash models/download-ggml-model.sh small

# Compile for ARM (disable OpenMP for Termux compatibility)
cmake -B build -DGGML_NO_OPENMP=ON
cmake --build build -j$(nproc)
```

### 4. Set up the server

```bash
cd ~
mkdir transcribe-local && cd transcribe-local
# Place main.py here (see /server/main.py in this repo)
```

### 5. Start the server

```bash
uvicorn main:app --host 0.0.0.0 --port 8080
```

### 6. Open in browser

On your phone: `http://localhost:8080`  
From another device on the same Wi-Fi: `http://<your-phone-ip>:8080`

---

## Running the frontend locally (development)

```bash
# Clone the repo
git clone https://github.com/hillarynjuguna/TheHand.git
cd TheHand

# Install dependencies (Node 20+ required)
npm install

# Start dev server
npm run dev
```

Open `http://localhost:5173` in your browser.

```bash
# Production build
npm run build
npm run preview
```

---

## Model size guide

| Model | Size | Speed (mobile) | Use case |
|---|---|---|---|
| tiny | 75MB | ~8x realtime | Quick notes, testing |
| base | 142MB | ~5x realtime | General use |
| small | 466MB | ~2x realtime | **Recommended** |
| medium | 1.5GB | ~1x realtime | High accuracy |
| large-v3 | 3.1GB | 0.5x realtime | Maximum quality |

---

## Privacy

Everything runs locally. No audio is ever uploaded anywhere. No accounts. No telemetry. The pipeline is:

```
Your device → yt-dlp (download) → ffmpeg (convert) → whisper.cpp (transcribe) → Your screen
```

---

## Requirements summary

- **Storage:** ~600MB (small model + tools)
- **RAM:** ~850MB during transcription (small model)
- **Setup time:** ~3 minutes
- **Internet:** Only needed for downloading URLs to transcribe (not for the transcription itself)
- **Node.js:** v20+ (frontend only)
- **Python:** 3.10+

---

## License

MIT
