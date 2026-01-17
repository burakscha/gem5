# Controlled Spill Validation Test

## Test Dosyası: `spill_exact.S`

### Beklenen Sonuçlar (EXPECTED)

| Metrik | Beklenen Değer |
|--------|----------------|
| **Total Stores** | 4 |
| **Total Loads** | 4 |
| **Total Spills** | 4 |

### Spill Pattern

| # | Store Adresi | Load Adresi | Spill? |
|---|--------------|-------------|--------|
| 1 | sp+8 | sp+8 | ✅ YES |
| 2 | sp+16 | sp+16 | ✅ YES |
| 3 | sp+24 | sp+24 | ✅ YES |
| 4 | sp+32 | sp+32 | ✅ YES |

---

## Build ve Test Komutları

```bash
# Container içinde
cd /workspace/tests/spill_test

# Assemble
riscv64-linux-gnu-as -o spill_exact.o spill_exact.S

# Link
riscv64-linux-gnu-ld -o spill_exact.riscv spill_exact.o

# Simülasyonu çalıştır
cd /workspace
./build/RISCV/gem5.opt configs/deprecated/example/se.py \
  --cmd=tests/spill_test/spill_exact.riscv \
  --cpu-type=TimingSimpleCPU

# Sonuçları kontrol et
cat m5out/riscv_spill_stats.txt
grep "^SPILL" m5out/riscv_spill_stats.txt | wc -l
```

---

## Doğrulama Kriterleri

✅ **PASS**: `grep "^SPILL" m5out/riscv_spill_stats.txt | wc -l` = **4**
❌ **FAIL**: Farklı sayı

---

## Sonuç

| Test | Beklenen | Gerçek | Durum |
|------|----------|--------|-------|
| Spill Sayısı | 4 | ___ | ⏳ |
