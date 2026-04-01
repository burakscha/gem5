# Makefile — test_spill_cache
#
# Cross-compiles test_spill_cache.c for RISC-V (RV64GC, Linux ABI).
# Adjust CROSS_PREFIX if your toolchain lives elsewhere.

CROSS_PREFIX := /cta/research/level0/RISCV/bin/riscv64-unknown-linux-gnu

CC      := $(CROSS_PREFIX)-gcc
OBJDUMP := $(CROSS_PREFIX)-objdump

GEM5_ROOT   := $(realpath ../..)
GEM5_INCLUDE := $(GEM5_ROOT)/include
LIBM5        := $(GEM5_ROOT)/util/m5/build/riscv/out/libm5.a

# -O1: keeps volatile semantics (all stack accesses present), removes dead
# assignments only outside volatile.  Do NOT use -O2/-O3 — may hoist/sink
# loads across the evict_l1() call.
#
# Override L1D size at build time if you change --l1d_size in gem5:
#   make EVICT_BYTES=$((4 * 65536))    # for 64 KB L1D
EVICT_BYTES ?= 524288   # 512 KB = 16× default 32 KB L1D

CFLAGS := \
    -O1 \
    -march=rv64gc \
    -mabi=lp64d \
    -static \
    -I$(GEM5_INCLUDE) \
    -DEVICT_BYTES=$(EVICT_BYTES)

TARGET := test_spill_cache

.PHONY: all clean disasm

all: $(TARGET)

$(TARGET): test_spill_cache.c
	$(CC) $(CFLAGS) -o $@ $< $(LIBM5)

# Verify store/load pairs in the three test functions.
# Look for:
#   test_l1_hit:  sd  tx,N(sp)  immediately followed by  ld  ty,N(sp)  same N
#   test_l1_miss: sd  tx,N(sp)  ... call evict_l1 ...   ld  ty,N(sp)  same N
#   main:         ld  tz,<neg_var addr>  (no matching sd inside ROI)
disasm: $(TARGET)
	$(OBJDUMP) -d -M no-aliases $(TARGET) | \
	    awk '/^[0-9a-f]+ <(test_l1_hit|test_l1_miss|evict_l1|main)>:/{found=1} \
	         found{print} \
	         /^$$/{if(found) found=0}' | head -120

clean:
	rm -f $(TARGET)
