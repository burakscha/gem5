#!/usr/bin/env bash
# Helper: build a Linux x86_64 ELF binary for matrix_spill using dockcross
# Usage: ./build_matrix_with_dockcross.sh
set -euo pipefail
WORKDIR=$(cd "$(dirname "$0")" && pwd)
DOCKCROSS=$WORKDIR/dockcross-x64
TARGET=x86_matrix_linux
SOURCE=x86_matrix_spill_test.c

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Please install and start Docker, or build on a Linux machine."
  exit 2
fi

if [ ! -x "$DOCKCROSS" ]; then
  echo "Creating dockcross wrapper..."
  docker run --rm dockcross/linux-x64 > "$DOCKCROSS"
  chmod +x "$DOCKCROSS"
fi

echo "Building $TARGET with dockcross..."
# Use the wrapper to compile inside the dockcross container
./dockcross-x64 -c "gcc -O2 -march=x86-64 -fno-tree-vectorize -funroll-loops -std=c11 -o ${TARGET} ${SOURCE}"

if [ -f "$TARGET" ]; then
  echo "Built $TARGET"
  file $TARGET || true
else
  echo "Build failed: $TARGET not found"
  exit 1
fi
