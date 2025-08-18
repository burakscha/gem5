#!/bin/bash

# RISC-V toolchain'in yüklü olduğunu varsayıyoruz
RISCV_AS=riscv64-unknown-elf-as
RISCV_LD=riscv64-unknown-elf-ld
RISCV_OBJDUMP=riscv64-unknown-elf-objdump

# Assembly'yi derle
$RISCV_AS test_sfk_comprehensive.s -o test_sfk.o

# Link et
$RISCV_LD test_sfk.o -o test_sfk

# Disassembly çıktısı (debug için)
$RISCV_OBJDUMP -d test_sfk > test_sfk.dump

echo "Derleme tamamlandı!"