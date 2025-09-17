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

# Build target for the register-spill matrix test
## Dedicated native build for matrix_spill (avoids top-level -static)
MCC = gcc
MFLAGS = -O2 -march=native -fno-tree-vectorize -funroll-loops -std=c11 -Wall -Wextra

.PHONY: all matrix_spill matrix_spill_native clean

all: matrix_spill_native

matrix_spill: matrix_spill_native

matrix_spill_native: matrix_spill.c
	$(MCC) $(MFLAGS) -o matrix_spill matrix_spill.c

clean:
	rm -f matrix_spill

clean:
	rm -f $(TARGET) dockcross-x64

.PHONY: all docker-build native test clean
