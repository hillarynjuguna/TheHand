#!/usr/bin/env bash
# Minimal script to test /api/transcribe/url contract
API=${1:-http://localhost:8080}
URL=${2:-https://www.youtube.com/watch?v=dQw4w9WgXcQ}

echo "Posting URL to $API/api/transcribe/url"
curl -s -X POST -F "url=$URL" -F "model=small" -F "language=auto" "$API/api/transcribe/url" | jq || true
