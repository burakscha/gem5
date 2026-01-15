# Register Spill Detection - Test Guide

Bu döküman, gem5 simülatöründe register spill tespiti için yapılan implementasyonu ve test sürecini açıklamaktadır.

---

## 📁 Proje Yapısı

```
gem5/
├── src/cpu/simple/
│   ├── spill_detector.hh          # SpillDetector sınıf tanımı
│   ├── spill_detector.cc          # SpillDetector implementasyonu
│   ├── timing.hh                  # TimingSimpleCPU (SpillDetector entegrasyonu)
│   ├── timing.cc                  # Load/Store hook'ları
│   └── SConscript                 # Build konfigürasyonu
├── docker/
│   ├── dockerfile.dev             # Docker build ortamı
│   └── run_docker.sh              # Docker başlatma scripti
├── tests/spill_test/
│   ├── spill_test.c               # Register pressure test programı
│   └── README.md                  # Bu dosya
└── m5out/
    └── riscv_spill_stats.txt      # Spill detection sonuçları
```

---

## 🔧 Implementasyon Özeti

### SpillDetector Mantığı

1. **Store Takibi**: Her `store` instruction'ı `std::unordered_map`'e kaydedilir
2. **Load Kontrolü**: Her `load` instruction'ında map'te eşleşen adres aranır
3. **Spill Tespiti**: Eğer bir `load`, yakın zamanda `store` edilen adresi okuyorsa → **SPILL**

### Entegrasyon Noktaları (timing.cc)

| Fonksiyon | Hook | Açıklama |
|-----------|------|----------|
| `initiateMemRead()` | `onLoadInstruction()` | Load işlemi başladığında |
| `writeMem()` | `onStoreInstruction()` | Store işlemi başladığında |
| `advanceInst()` | `onInstructionExecute()` | Instruction sayacı |

---

## 🐳 Test Ortamı Kurulumu

### Gereksinimler
- Docker Desktop
- ARM64 veya x86_64 host

### Adım 1: Docker Container Başlatma

```bash
cd /path/to/gem5
./docker/run_docker.sh
```

Bu script:
- `gem5-universal:latest` image'ını build eder
- Container'ı `/workspace` mount ederek başlatır

---

## 🔨 Build ve Test Adımları

### Container İçinde:

#### 1. RISC-V Test Binary Oluşturma
```bash
cd /workspace/tests/spill_test
riscv64-linux-gnu-gcc -O0 -static spill_test.c -o spill_test.riscv
```

> **Not**: `-O0` optimizasyonu kapatır, spill'leri tahmin edilebilir kılar

#### 2. gem5 Derleme (RISC-V)
```bash
cd /workspace
scons build/RISCV/gem5.opt -j8
```

> **Süre**: ~30-60 dakika (ilk build)

#### 3. Simülasyonu Çalıştırma
```bash
./build/RISCV/gem5.opt configs/deprecated/example/se.py \
  --cmd=tests/spill_test/spill_test.riscv \
  --cpu-type=TimingSimpleCPU \
  --caches
```

#### 4. Sonuçları Görüntüleme
```bash
cat m5out/riscv_spill_stats.txt
wc -l m5out/riscv_spill_stats.txt  # Satır sayısı
```

---

## 📊 Çıktı Formatı

```
SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,store_inst,load_inst
```

| Alan | Açıklama |
|------|----------|
| `store_pc` | Store instruction'ın PC adresi (hex) |
| `load_pc` | Load instruction'ın PC adresi (hex) |
| `memory_address` | Spill'in gerçekleştiği bellek adresi |
| `store_tick` | Store zamanı (simülasyon tick) |
| `load_tick` | Load zamanı (simülasyon tick) |
| `tick_diff` | Store-Load arası gecikme |
| `store_inst` | Store anındaki instruction sayacı |
| `load_inst` | Load anındaki instruction sayacı |

---

## ✅ Test Sonuçları (Örnek)

| Metrik | Değer |
|--------|-------|
| Tespit edilen spill sayısı | 750+ |
| Memory bölgesi | Stack (0x7fffff...) |
| Ortalama tick farkı | ~100,000 - 1,000,000 |

### Hot Spill Points
- `0x14ab4 → 0x14b1c`: libc fonksiyonları
- `0x21cd6 → 0x221d4`: `heavy_register_pressure()`
- `0x1c73c → 0x1c790`: Stack frame management

---

## 🔄 Farklı ISA'lar için Build

```bash
# X86
scons build/X86/gem5.opt -j8

# RISC-V
scons build/RISCV/gem5.opt -j8

# ARM
scons build/ARM/gem5.opt -j8
```

Her ISA için otomatik olarak doğru log dosyası oluşturulur:
- `m5out/x86_spill_stats.txt`
- `m5out/riscv_spill_stats.txt`
- `m5out/arm_spill_stats.txt`

---

## 📝 Notlar

1. **Docker Avantajı**: Host'taki dependency sorunlarından bağımsız, tutarlı build ortamı
2. **Static Linking**: `-static` flag'i simülasyonu basitleştirir
3. **TimingSimpleCPU**: SpillDetector sadece bu CPU modelinde aktif

---

## 📚 İlgili Dosyalar

- [spill_detector.hh](../../src/cpu/simple/spill_detector.hh)
- [spill_detector.cc](../../src/cpu/simple/spill_detector.cc)
- [timing.cc](../../src/cpu/simple/timing.cc)
- [spill_test.c](./spill_test.c)
