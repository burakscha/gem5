#!/bin/bash
set -e

IMAGE_NAME="gem5-universal:latest"
DOCKERFILE="docker/dockerfile.dev"

echo "🔧 Building Docker image if needed..."
docker buildx build --platform linux/amd64 -t $IMAGE_NAME -f $DOCKERFILE .

echo "🚀 Starting container..."
docker run --rm -it --platform linux/amd64 -v "$(pwd)":/workspace $IMAGE_NAME bash