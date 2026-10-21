#!/usr/bin/env bash
# Downloads MediaPipe's bundled Gesture Recognizer model into this folder.
# Source: https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task"
DEST="${SCRIPT_DIR}/gesture_recognizer.task"

echo "Downloading gesture_recognizer.task to ${DEST} ..."
curl -L --fail -o "${DEST}" "${MODEL_URL}"
echo "Done."
