# Cross-compile for RISC-V (RV64GC, static, bare-metal ELF)
# Usage:  make
#         make clean
#         make GEM5_ROOT=/path/to/gem5   (override if needed)

GEM5_ROOT ?= $(abspath ../../../../)

CROSS  = /cta/research/level0/RISCV/bin/riscv64-unknown-elf-gcc
CC     = $(CROSS)

CFLAGS = -O2 -static \
         -march=rv64gc -mabi=lp64d \
         -I$(GEM5_ROOT)/include

LDFLAGS = -L$(GEM5_ROOT)/util/m5/build/riscv/out -lm5 -static

TARGET = test.riscv

$(TARGET): test.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f $(TARGET)

.PHONY: clean
