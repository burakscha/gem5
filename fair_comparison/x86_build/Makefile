# Makefile for X86 Matrix Spill Test
# Based on gem5's test-progs Makefile structure

CC = gcc
CFLAGS = -O1 -static
TARGET = x86_matrix_linux
SOURCE = x86_matrix_spill_test.c

# Default target - use docker cross-compilation
all: docker-build

# Docker-based cross-compilation (recommended)
docker-build: dockcross-x64
	./dockcross-x64 -c '$$CC $(CFLAGS) $(SOURCE) -o $(TARGET)'

# Create docker cross-compilation script
dockcross-x64:
	docker run --rm dockcross/linux-x64 > ./dockcross-x64
	chmod +x ./dockcross-x64

# Native compilation (if on Linux)
native:
	$(CC) $(CFLAGS) $(SOURCE) -o $(TARGET)

# Test the binary
test: $(TARGET)
	@echo "Testing X86 matrix binary..."
	@if [ -f $(TARGET) ]; then echo "Binary exists: $(TARGET)"; else echo "Binary not found!"; fi
	@file $(TARGET) || echo "File command not available"

clean:
	rm -f $(TARGET) dockcross-x64

.PHONY: all docker-build native test clean
