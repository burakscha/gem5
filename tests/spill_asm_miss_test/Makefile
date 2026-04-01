CROSS    := /cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu
CC       := $(CROSS)-gcc
OBJDUMP  := $(CROSS)-objdump

GEM5_ROOT    := $(realpath ../..)
GEM5_INCLUDE := $(GEM5_ROOT)/include
LIBM5        := $(GEM5_ROOT)/util/m5/build/riscv/out/libm5.a

CFLAGS := -O1 -march=rv64gc -mabi=lp64d -static -I$(GEM5_INCLUDE)
TARGET := spill_miss_test

.PHONY: all clean disasm

all: $(TARGET)

$(TARGET): spill_miss_test.S
	$(CC) $(CFLAGS) -o $@ $< $(LIBM5)

disasm: $(TARGET)
	@echo "=== test_spill_l1_miss ==="
	$(OBJDUMP) -d -M no-aliases --disassemble=test_spill_l1_miss $(TARGET)
	@echo ""
	@echo "=== warmup_evict_buf ==="
	$(OBJDUMP) -d -M no-aliases --disassemble=warmup_evict_buf $(TARGET)
	@echo ""
	@echo "=== main ==="
	$(OBJDUMP) -d -M no-aliases --disassemble=main $(TARGET)

clean:
	rm -f $(TARGET)
