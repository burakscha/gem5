# Spill Load/Store Cache Hit/Miss Validation Suite

## Ne bu?

Bu dizin, gem5'e eklediğimiz register spill izleme altyapısının doğru çalıştığını
kanıtlamak için yazılmış mikro-testleri barındırıyor.

Altyapı üç katmandan oluşuyor:

```
┌─────────────────────────────────────────────────────┐
│  CPU (TimingSimpleCPU)                              │
│    SpillDetector: "bu işlem bir spill mi?"          │
│    → evet: isteğe SPILL_LOAD veya SPILL_STORE ekle │
└──────────────────────┬──────────────────────────────┘
                       │ flag'li istek
┌──────────────────────▼──────────────────────────────┐
│  L1 dcache                                          │
│    hit  → spillLoad/StoreHits++                     │
│    miss → spillLoad/StoreMisses++                   │
│           isteği L2'ye ilet (flag korunur)          │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  L2 cache                                           │
│    hit  → l2.spillLoad/StoreHits++                  │
│    miss → l2.spillLoad/StoreMisses++ → DRAM         │
└─────────────────────────────────────────────────────┘
```

---

## Neden bu testlere ihtiyaç duyduk?

Gerçek SPEC CPU2017 benchmark'larında milyarlarca işlem var. Sayaçların
doğru çalışıp çalışmadığı orada belli olmaz — çok fazla gürültü var.

Bu testlerde ise her şey deterministik:

- Cache boyutunu küçük tuttuk (L1 = 1 kB, L2 = 8 kB)
- Her test **tam olarak bir senaryoyu** üretiyor (sadece bir hit ya da sadece bir miss)
- Simülasyon bitince `stats.txt`'teki sayacın beklenen değerde olup olmadığını `check.sh` ile assert ediyoruz

---

## Cache konfigürasyonu

| Parametre | Değer | Açıklama |
|-----------|-------|----------|
| L1 dcache | 1 kB, 4-way, 64 B line | 4 set × 4 way = **16 satır toplam** |
| L2 cache | 8 kB, 4-way, 64 B line | 32 set × 4 way = **128 satır toplam** |
| Bellek | SimpleMemory (30 ns) | Deterministic latency |
| MAX_SPILL_WINDOW | 50.000.000 tick (50 µs) | 160 flush satırı ~26M tick sürer, pencere içinde kalır |

L1'i boşaltmak için **32 satır**, hem L1 hem L2'yi boşaltmak için **160 satır** erişmek yeterli:

```
L1 flush (32 satır):
  32 / 4 set  = 8 rakip satır/set  >> 4 way  → L1 tamamen boşalır ✓
  32 / 32 set = 1 rakip satır/set  << 4 way  → L2'de kalır ✓

L1 + L2 flush (160 satır):
  160 / 4  set = 40 rakip satır/set >> 4 way  → L1 boşalır ✓
  160 / 32 set =  5 rakip satır/set >  4 way  → L2 boşalır ✓
```

---

## BSS nedir, flush neden BSS'ten yapılır?

**BSS** (Block Started by Symbol): başlangıç değeri verilmemiş `static` ve
global değişkenlerin program belleğindeki bölgesi. Derleyici bu adresleri
stack'ten tamamen farklı bir sanal adres aralığına koyar.

Flush dizimiz (`flush_buf`) BSS'te tanımlı:

```c
static volatile char flush_buf[160 * 64];
```

Bunun iki kritik işlevi var:

1. **`isStackAddress()` false döner.** SpillDetector, bir adresi spill olarak
   sayabilmek için önce stack aralığında olup olmadığını kontrol eder. BSS
   adresleri bu kontrolden geçemez → flush yüklemeleri hiçbir zaman spill
   olarak sayılmaz. Aksi hâlde flush döngüsü yüzlerce sahte spill üretirdi.

2. **Stack'i bozmaz.** Flush için stack üzerinde büyük bir dizi açsaydık
   ABI kurallarını çiğner, prologue'u karmaşıklaştırırdık.

Flush fonksiyonu ayrıca `__attribute__((noinline))` + `-O2` ile derleniyor.
Bu kombinasyon derleyiciyi döngü için sadece caller-saved register kullanmaya
zorluyor — hiç `sd sp` / `ld sp` üretmiyor. Bunu disassembly ile doğruladık:

```asm
flush_l1:
    lui  a2, ...       # flush_buf base adresi — register'da
    li   a5, 0         # i = 0
.loop:
    lbu  a3, 0(a4)     # flush_buf[i*64] oku — BSS'ten yükle
    addiw a5, a5, 64
    bnez a4, .loop
    ret                # stack'e hiç dokunmadı ✓
```

---

## Testler ve sonuçlar

### Load tarafı

| Test | Senaryo | dcache.spillLoadHits | dcache.spillLoadMisses | l2.spillLoadHits | l2.spillLoadMisses | Sonuç |
|------|---------|:--------------------:|:----------------------:|:----------------:|:------------------:|:-----:|
| `load/l1_hit` | Spill reload, line L1'de | **1** | 0 | 0 | 0 | ✅ PASS |
| `load/l1miss_l2hit` | L1 miss, L2'de bulundu | 0 | **1** | **1** | 0 | ✅ PASS |
| `load/l1miss_l2miss` | L1 miss, L2 miss, DRAM | 0 | **1** | 0 | **1** | ✅ PASS |

**Kalın** rakam: o testin doğrulamak istediği sayaç. Diğerleri 0 — yanlış seviyede sayılmadı.

> `load/l1_hit`: Store ve load ROI içinde, cache line hiç boşaltılmadan yapıldı.
> L1 zaten line'ı tutuyor → hit.
>
> `load/l1miss_l2hit`: 32-satır flush ile L1 boşaltıldı, L2'de bırakıldı.
> Load → L1 miss → L2 hit.
>
> `load/l1miss_l2miss`: 160-satır flush ile hem L1 hem L2 boşaltıldı.
> Load → L1 miss → L2 miss → DRAM.

---

### Store tarafı

| Test | Senaryo | dcache.spillStoreHits | dcache.spillStoreMisses | l2.spillStoreHits | l2.spillStoreMisses | Sonuç |
|------|---------|:---------------------:|:-----------------------:|:-----------------:|:-------------------:|:-----:|
| `store/l1_hit` | Spill store, line L1'de | **1** | 0 | 0 | 0 | ✅ PASS |
| `store/l1_miss` | L1 miss → RFO → L2'de | 0 | **1** | **1** | 0 | ✅ PASS |
| `store/l1miss_l2miss` | L1 miss → RFO → L2 miss | 0 | **1** | 0 | **1** | ✅ PASS |

> `store/l1_hit`: ROI öncesi `x = 0` ile line ısıtıldı (pre-warm). m5_work_begin
> leaf fonksiyon olduğu için stack'e dokunmaz, line L1'de sıcak kalıyor → hit.
>
> `store/l1_miss`: 32-satır flush ile L1 boşaltıldı. ROI içi store → L1 miss.
> L1, L2'ye write-allocate RFO gönderir. **Bu RFO paketi SPILL_STORE flag'ini taşır**
> (başlangıçta aksini varsaymıştık — simülasyonla düzeltildi) → l2.spillStoreHits++.
>
> `store/l1miss_l2miss`: 160-satır flush → L1 ve L2 boşaltıldı. ROI içi store →
> L1 miss → RFO → L2 miss → DRAM → l2.spillStoreMisses++.

---

### Simetri tablosu

```
                  L1 hit   L1 miss / L2 hit   L1 miss / L2 miss
  Load side:        ✅             ✅                  ✅
  Store side:       ✅             ✅                  ✅
```

Her iki access türü için cache hiyerarşisinin tüm katmanları doğrulandı.

---

## Önemli keşif: SPILL_STORE RFO yoluyla L2'ye taşınıyor

Başlangıçta "write-allocate RFO paketi SPILL_STORE flag'ini taşımaz,
dolayısıyla `l2.spillStore*` hep 0 olur" varsayılmıştı.

`store/l1_miss` çalıştırıldığında `l2.spillStoreHits = 1` göründü.

gem5, L1 write-miss için L2'ye gönderdiği `ReadExReq` (RFO) paketini
orijinal store request'ten türetirken SPILL_STORE flag'ini kopyalıyor.
Dolayısıyla `l2.spillStoreHits` ve `l2.spillStoreMisses` gerçek anlam taşıyor —
load tarafıyla tam simetri sağlanmış oldu.

---

## Hit/miss oranı nasıl hesaplanır?

Bu testler sayaçların doğru arttığını kanıtladı. Gerçek benchmark üzerinde
aşağıdaki formüller kullanılacak:

| Metrik | Formül | Anlamı |
|--------|--------|--------|
| L1 spill load hit rate | `spillLoadHits / (spillLoadHits + spillLoadMisses)` | Spill reload'ların kaçı L1'de bulundu? |
| L2 rescue rate | `l2.spillLoadHits / dcache.spillLoadMisses` | L1'i kaçıranların kaçı L2'de kurtarıldı? |
| DRAM spill rate | `l2.spillLoadMisses / dcache.spillLoadMisses` | Kaçı DRAM'a kadar gitti? |
| L1 spill store hit rate | `spillStoreHits / (spillStoreHits + spillStoreMisses)` | Spill write'ların kaçı L1'de bulundu? |
| Spill fraction of demand | `(spillLoadHits + spillLoadMisses) / total_demand_accesses` | Cache trafiğinin ne kadarı spill'den geliyor? |

Bu metrikler Phase 7'de her SPEC CPU2017 benchmark'ı için ayrı ayrı hesaplanacak.

---

## Nasıl çalıştırılır?

```bash
cd gem5/tests/cache_hit_miss

# Tüm testleri sırayla derle + simüle et + assert et:
bash run_all.sh

# Tek bir test:
cd load/l1miss_l2hit
make
bash run.sh
bash check.sh
```

`run_all.sh` çıktısı:

```
Passed : 6
Failed : 0
All tests PASSED.
```

---

## Dizin yapısı

```
cache_hit_miss/
├── run_all.sh              ← 6 testi sırayla çalıştırır
├── README.md               ← bu dosya
├── SUMMARY.md              ← teknik detaylar (pipeline, matematik, formüller)
├── ROADMAP.md              ← 9-phase plan (negative tests, stress, benchmarks...)
├── load/
│   ├── l1_hit/             ← spillLoadHits = 1
│   ├── l1miss_l2hit/       ← spillLoadMisses = 1, l2.spillLoadHits = 1
│   └── l1miss_l2miss/      ← spillLoadMisses = 1, l2.spillLoadMisses = 1
└── store/
    ├── l1_hit/             ← spillStoreHits = 1
    ├── l1_miss/            ← spillStoreMisses = 1, l2.spillStoreHits = 1
    └── l1miss_l2miss/      ← spillStoreMisses = 1, l2.spillStoreMisses = 1
```

Her alt dizinde: `test.c` · `Makefile` · `run.sh` · `check.sh` · `README.md`

---

## Sıradaki adım: Phase 3 — Negative testler

Spill **sayılmaması** gereken durumları doğrulayacak 4 test:

| # | Test | Guard koşulu | Beklenen |
|---|------|-------------|---------|
| 1 | `negative/non_stack` | `isStackAddress()` → false | Tüm sayaçlar 0 |
| 2 | `negative/roi_outside` | `inside_roi = false` at load | spillLoad sayaçları 0 |
| 3 | `negative/size_mismatch` | size mismatch in `isLikelySpill()` | spillLoad sayaçları 0 |
| 4 | `negative/window_expired` | `cleanupOldStores()` evicts entry | spillLoad sayaçları 0 |
