# Spill Load/Store Cache Validation — SUMMARY

## 1. Neden bu altyapı gerekli?

gem5'e eklediğimiz `SPILL_LOAD` ve `SPILL_STORE` request flag'leri ile
`spillLoad{Hits,Misses}` / `spillStore{Hits,Misses}` cache sayaçları,
gerçek benchmark verisine güvenebilmek için önce **kontrollü, belirleyici
koşullarda** doğrulanmalıdır. Bu mikro-test altyapısı:

- Tag'in CPU'dan cache hiyerarşisinin her katmanına doğru taşındığını,
- Hit vs. miss kararlarının doğru seviyede sayıldığını,
- False-positive ve false-negative üretilmediğini

deneysel olarak kanıtlar.

---

## 2. Doğrulanan pipeline

### SPILL_LOAD

```
TimingSimpleCPU::initiateMemRead()
  └─ spillDetector.onLoadInstruction(addr, pc, tick, size, sp, tc)
       └─ store_map.find(addr) → isLikelySpill()
            [stack addr? + size match? + temporal order? + inside_roi?]
            → return true
               └─ req->setFlags(Request::SPILL_LOAD)

L1 dcache:
  hit  → BaseCache::incHitCount(pkt)  → isDemand() && isSpillLoad()
          → dcache.spillLoadHits++
  miss → BaseCache::incMissCount(pkt) → dcache.spillLoadMisses++
           packet forwarded to L2 with SPILL_LOAD intact

L2:
  hit  → l2.spillLoadHits++
  miss → l2.spillLoadMisses++   (continues to DRAM)
```

### SPILL_STORE

```
TimingSimpleCPU::initiateMemWrite()
  └─ spillDetector.onStoreInstruction(addr, pc, tick, size, sp, tc)
       └─ inside_roi && isStackAddress(addr)   [over-approximation]
            → return true
               └─ req->setFlags(Request::SPILL_STORE)

L1 dcache:
  hit  → dcache.spillStoreHits++
  miss → dcache.spillStoreMisses++
           L1 emits write-allocate RFO (ReadExReq) to L2
           *** RFO packet INHERITS SPILL_STORE flag ***

L2 (receives RFO):
  hit  → l2.spillStoreHits++
  miss → l2.spillStoreMisses++  (continues to DRAM)
```

---

## 3. Önemli keşif: SPILL_STORE RFO yoluyla L2'ye taşınıyor

Başlangıçta "write-allocate RFO paketi SPILL_STORE flag'ini taşımaz,
dolayısıyla `l2.spillStore*` hep 0 olur" varsayılmıştı.

**Bu yanlış çıktı.**

`store/l1_miss` simülasyonu `l2.spillStoreHits = 1` döndürdü; `store/l1miss_l2miss`
ise `l2.spillStoreMisses = 1` döndürdü. gem5, L1 write-miss RFO'sunu orijinal
store request'ten türetirken SPILL_STORE flag'ini kopyalıyor. Dolayısıyla:

- `l2.spillStoreHits`   = L1 store miss'te stack line'ın L2'de bulunması
- `l2.spillStoreMisses` = L1 store miss'te stack line'ın L2'de de bulunmaması

Bu, **store tarafında da tam dört sayaç görünürlüğü** sağladığı anlamına gelir
ve load tarafıyla tam simetri kurar.

---

## 4. Cache konfigürasyonu

| Parametre | Değer | Neden |
|-----------|-------|-------|
| `--l1d_size=1kB --l1d_assoc=4` | 4 set × 4 way = 16 line | 32 flush line L1'i doldurur; 160 line kesinlikle doldurur |
| `--l2_size=8kB  --l2_assoc=4`  | 32 set × 4 way = 128 line | 160 line → 5 line/set > 4 way → L2 overflow |
| `--mem-type=SimpleMemory` | ~30 ns | Flush süresi < MAX_SPILL_WINDOW |
| `MAX_SPILL_WINDOW` | 50,000,000 ticks (50 µs) | 160 cold access × ~162K tick ≈ 26M < 50M |

---

## 5. Flush matematiği

### L1-only eviction (32 line)
```
L1: 4 set  →  32 / 4  = 8 line/set >> 4 ways  → TAM EVICTION ✓
L2: 32 set →  32 / 32 = 1 line/set << 4 ways  → HAYATTA KALIR ✓
```

### L1 + L2 eviction (160 line)
```
L1: 4 set  →  160 / 4  = 40 line/set >> 4 ways → EVICTION ✓
L2: 32 set →  160 / 32 = 5  line/set >  4 ways → EVICTION ✓
```

---

## 6. Flush fonksiyonu izolasyonu

Flush döngüleri `__attribute__((noinline))` + `-O2` kombinasyonuyla
sadece caller-saved register kullanacak şekilde derleniyor:

- `ra` push/pop yok → stack erişimi yok → `isStackAddress()` tetiklenmiyor
- BSS adresleri stack range dışında → flush yüklemeleri asla SPILL_LOAD sayılmıyor
- Disassembly ile doğrulandı: `flush_l1` / `flush_l1_l2` fonksiyonlarında hiç `sd/ld sp` yok

---

## 7. Sonuç tablosu (6/6 PASS)

### Load tarafı

| Test | dcache.spillLoadHits | dcache.spillLoadMisses | l2.spillLoadHits | l2.spillLoadMisses |
|------|:-------------------:|:----------------------:|:----------------:|:------------------:|
| `load/l1_hit` | **1** | 0 | 0 | 0 |
| `load/l1miss_l2hit` | 0 | **1** | **1** | 0 |
| `load/l1miss_l2miss` | 0 | **1** | 0 | **1** |

### Store tarafı

| Test | dcache.spillStoreHits | dcache.spillStoreMisses | l2.spillStoreHits | l2.spillStoreMisses |
|------|:--------------------:|:-----------------------:|:-----------------:|:-------------------:|
| `store/l1_hit` | **1** | 0 | 0 | 0 |
| `store/l1_miss` | 0 | **1** | **1** | 0 |
| `store/l1miss_l2miss` | 0 | **1** | 0 | **1** |

### Simetri özeti

```
                  L1 hit   L1 miss / L2 hit   L1 miss / L2 miss
  Load side:       ✓              ✓                   ✓
  Store side:      ✓              ✓                   ✓
```

---

## 8. Negative test öncelik sırası (Phase 3)

Aşağıdaki testler **sıfır spill** sayması gerekiyor.
Her biri SpillDetector içindeki bir guard koşulunu izole eder:

### #1 — `negative/non_stack` (en yüksek öncelik)

**Guard:** `isStackAddress(addr, tc)` → false  
BSS veya global değişkene yapılan store+load ROI içinde olsa bile spill sayılmamalı.

```c
static volatile int64_t bss_var;  // BSS, not stack

m5_work_begin(0, 0);
bss_var = 0xA5A5LL;    // SPILL_STORE? Hayır — isStackAddress() false
int64_t v = bss_var;  // SPILL_LOAD?  Hayır — isStackAddress() false
m5_work_end(0, 0);
// Beklenen: spillLoad=0, spillStore=0, spillLoadHits=0, spillLoadMisses=0
```

Bu test SpillDetector'ın en temel ayrımını — stack vs. non-stack — izole eder.

---

### #2 — `negative/roi_outside` (ikinci öncelik)

**Guard:** `inside_roi` → false at load time  
Store ROI içinde, load ROI **dışında** yapılırsa SPILL_LOAD sayılmamalı.

```c
volatile int64_t x;

m5_work_begin(0, 0);
x = 0xA5A5LL;           // store inside ROI → store_map'e eklendi
m5_work_end(0, 0);

int64_t v = x;          // load OUTSIDE ROI → inside_roi=false → no SPILL_LOAD
// Beklenen: dcache.spillLoadHits=0, dcache.spillLoadMisses=0
// (spillStoreHits veya spillStoreMisses olabilir — sadece load tarafını assert et)
```

ROI sınırı kontrolü: tag'in ROI dışına sızmamasını garanti eder.

---

### #3 — `negative/size_mismatch` (üçüncü öncelik)

**Guard:** `isLikelySpill()` size check — `store_info.size != load_size`  
8B store → 4B load olursa `isLikelySpill()` false döner, spill sayılmaz.

```c
m5_work_begin(0, 0);
volatile int64_t x;
x = 0xA5A5A5A5A5A5A5A5LL;   // 8B store → store_map[addr] = {size=8}

volatile int32_t *p = (volatile int32_t *)&x;
int32_t v = *p;               // 4B load → size mismatch → not a spill
m5_work_end(0, 0);
// Beklenen: dcache.spillLoadHits=0, dcache.spillLoadMisses=0
```

---

### #4 — `negative/window_expired` (dördüncü öncelik)

**Guard:** `cleanupOldStores(tick)` — store_map entry MAX_SPILL_WINDOW'dan eski  
Store sonrası ~50M tick'ten fazla bekleme → entry silinir → load artık spill sayılmaz.

```c
m5_work_begin(0, 0);
volatile int64_t x;
x = 0xA5A5LL;           // store → store_map entry (tick = T)

// BSS volatile döngüsüyle 50M+ tick geçir:
//   Her BSS yüklemesi cleanupOldStores() tetikler
//   50M tick geçince entry silinir

int64_t v = x;          // load → store_map.find → bulunamaz → no spill
m5_work_end(0, 0);
```

Bu test MAX_SPILL_WINDOW'un doğru çalıştığını doğrular ve
gerçek spill penceresiyle sahte-eşleşme riskini kanıtlar.

---

## 9. Derived metrikler (benchmark analizi için)

Doğrulanmış sayaçlardan hesaplanacak metrikler:

```
L1 spill load hit rate   = spillLoadHits  / (spillLoadHits + spillLoadMisses)
L2 rescue rate           = l2.spillLoadHits / dcache.spillLoadMisses
DRAM spill rate          = l2.spillLoadMisses / dcache.spillLoadMisses

L1 spill store hit rate  = spillStoreHits / (spillStoreHits + spillStoreMisses)

Spill fraction of demand =
    (dcache.spillLoadHits + dcache.spillLoadMisses) / system.cpu.dcache.demand_accesses
```

Bu metrikler benchmark başına toplanacak (tüm SPEC CPU2017, `--l2cache` ile).

---

## 10. Dizin yapısı

```
gem5/tests/cache_hit_miss/
├── run_all.sh              (6 testi sırayla build + sim + check)
├── SUMMARY.md              (bu dosya)
├── ROADMAP.md              (9-phase plan)
├── load/
│   ├── l1_hit/             PASS: spillLoadHits=1
│   ├── l1miss_l2hit/       PASS: spillLoadMisses=1, l2.spillLoadHits=1
│   └── l1miss_l2miss/      PASS: spillLoadMisses=1, l2.spillLoadMisses=1
└── store/
    ├── l1_hit/             PASS: spillStoreHits=1
    ├── l1_miss/            PASS: spillStoreMisses=1, l2.spillStoreHits=1
    └── l1miss_l2miss/      PASS: spillStoreMisses=1, l2.spillStoreMisses=1
```
