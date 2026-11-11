#!/usr/bin/env bash
# 下载 Kokoro 语音模型（约 350MB）到 models/
set -e
cd "$(dirname "$0")/.."
mkdir -p models
BASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
curl -L -o models/kokoro.onnx "$BASE/kokoro-v1.0.onnx"
curl -L -o models/voices.bin  "$BASE/voices-v1.0.bin"
echo "done"
