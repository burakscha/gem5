# Makefile — spill_asm_test
# Cross-compiles for RISC-V (RV64GC, Linux ABI).

CROSS    := /cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu
CC       := $(CROSS)-gcc
AS       := $(CROSS)-as
LD       := $(CROSS)-ld
OBJDUMP  := $(CROSS)-objdump

GEM5_ROOT    := $(realpath ../..)
GEM5_INCLUDE := $(GEM5_ROOT)/include
LIBM5        := $(GEM5_ROOT)/util/m5/build/riscv/out/libm5.a

CFLAGS := \
    -O1 \
    -march=rv64gc \
    -mabi=lp64d \
    -static \
    -I$(GEM5_INCLUDE)

ASFLAGS := \
    -march=rv64gc \
    -mabi=lp64d

TARGET := spill_asm_test

.PHONY: all clean disasm

all: $(TARGET)

$(TARGET): spill_tests.S
	$(CC) $(CFLAGS) -o $@ $< $(LIBM5)

# -----------------------------------------------------------------------
# disasm: show test_spill_l1_hit and test_no_spill disassembly.
#
# What to verify:
#   test_spill_l1_hit:
#     addi  sp, sp, -8
#     sd    t0, 0(sp)    ← STORE (or register alias: s1/t0 etc.)
#     ld    t0, 0(sp)    ← LOAD  same offset as sd above
#     addi  sp, sp, 8
#     ret
#   NO c.sdsp / c.ldsp (compressed) due to .option norvc in source.
#   NO other sd/ld instructions.
#
#   test_no_spill:
#     sw    t0, 0(sp)    ← 4-byte store
#     ld    t0, 0(sp)    ← 8-byte load (size mismatch)
# -----------------------------------------------------------------------
disasm: $(TARGET)
	@echo "=== test_spill_l1_hit ==="
	$(OBJDUMP) -d -M no-aliases --disassemble=test_spill_l1_hit $(TARGET)
	@echo ""
	@echo "=== test_no_spill ==="
	$(OBJDUMP) -d -M no-aliases --disassemble=test_no_spill $(TARGET)
	@echo ""
	@echo "=== main ==="
	$(OBJDUMP) -d -M no-aliases --disassemble=main $(TARGET)

clean:
	rm -f $(OBJS) $(TARGET)
