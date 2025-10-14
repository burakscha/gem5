#!/bin/bash
# Rebuild gem5 Docker image with multi-architecture support

set -e

echo "🐳 Building gem5 Docker Development Image..."
echo "=============================================="
echo ""

# Check if Dockerfile exists
if [ ! -f "Dockerfile_x86.dev" ]; then
    echo "❌ Error: Dockerfile_x86.dev not found!"
    echo "Please run this script from the gem5 root directory."
    exit 1
fi

# Build the image
echo "📦 Building docker image: gem5-dev:amd64"
docker build -f Dockerfile_x86.dev -t gem5-dev:amd64 .

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Docker image built successfully!"
    echo ""
    echo "📋 Image details:"
    docker images gem5-dev:amd64
    echo ""
    echo "🚀 To use the image, run:"
    echo "   docker run -it --rm -v \$(pwd):/gem5 -w /gem5 gem5-dev:amd64"
else
    echo ""
    echo "❌ Docker build failed!"
    exit 1
fi
