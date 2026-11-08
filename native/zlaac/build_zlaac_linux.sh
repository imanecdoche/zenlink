#!/usr/bin/env bash
# Compiles zlaac.so for Linux using system FFmpeg or provided pkg-config
set -euo pipefail

OUT=${1:-"$(cd "$(dirname "$0")/../../zenlink" && pwd)"}
HERE=$(cd "$(dirname "$0")" && pwd)

mkdir -p "$OUT"

CFLAGS=$(pkg-config --cflags libavcodec libswresample libavutil 2>/dev/null || true)
LIBS=$(pkg-config --libs libavcodec libswresample libavutil 2>/dev/null || echo "-lavcodec -lswresample -lavutil")

gcc -O2 -fPIC -shared -s -o "$OUT/zlaac.so" "$HERE/zlaac.c" \
  $CFLAGS $LIBS -Wl,--gc-sections

echo "Built: $OUT/zlaac.so"
ls -lh "$OUT/zlaac.so"
