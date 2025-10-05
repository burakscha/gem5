# Makefile for RISC-V Matrix Spill Test
# Based on gem5's test-progs Makefile structure

CC = gcc
CFLAGS = -O1 -static
TARGET = riscv_matrix_linux
SOURCE = riscv_matrix_spill_test.c

# Default target - use docker cross-compilation
all: docker-build

# Docker-based cross-compilation (recommended)
docker-build: dockcross-riscv64
	./dockcross-riscv64 -c '$$CC $(CFLAGS) $(SOURCE) -o $(TARGET)'

# Create docker cross-compilation script
dockcross-riscv64:
	docker run --rm dockcross/linux-riscv64 > ./dockcross-riscv64
	chmod +x ./dockcross-riscv64

# Native compilation (if using riscv64-linux-gnu-gcc)
native:
	riscv64-linux-gnu-gcc $(CFLAGS) $(SOURCE) -o $(TARGET)

# Test the binary
test: $(TARGET)
	@echo "Testing RISC-V matrix binary..."
	@if [ -f $(TARGET) ]; then echo "Binary exists: $(TARGET)"; else echo "Binary not found!"; fi
	@file $(TARGET) || echo "File command not available"

clean:
	rm -f $(TARGET) dockcross-riscv64

.PHONY: all docker-build native test clean
