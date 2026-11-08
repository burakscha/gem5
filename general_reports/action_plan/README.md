# Action plan: Saf Adres Kuralı (Plan B) ve sayaç temizliği (Plan C)

> **DURUM (2026-11-04 akşam): Plan B ve Plan C kullanıcı tarafından onaylandı
> ve kodda uygulandı.** Yeniden koşu kampanyası henüz başlatılmadı; uzun ve
> pahalı koşular için kullanıcıdan ayrıca onay alınır (5. bölüm).

> **Karar kaydı, 2026-11-04 akşam (kullanıcı):**
> - **Plan B onaylandı:** "yeni implementasyona başlıyoruz". Compiler etiketi
>   kullanılmayacak.
> - **"Spill store" (1.3):** iki küme ayrı tutulacak.
>   - (i) *spill store* = ROI içinde geri okunan store'lar (eşleşmiş). Cache
>     sonucu store başına bir kez sayılır, detector'den gelir.
>   - (ii) *stack store* = bütün stack store'ları. gem5 cache sayaçlarından
>     ve detector'den gelir.
>   - Eşleşmemiş store'lar (ii) − (i) farkından türetilir.
>   - Spill reload'ların cache sonucu ayrı tutulur.
> - **Xeon kuyruğu (açık karar 4):** kalan full ref koşuları durdurulacak
>   (`cache_scripts/run_on_host.sh stop --yes --inputs ref`, xeon'da).
> - **roms train** (5 koşu, xeon): devam ediyor, durdurulmayacak.
> - **Plan C (açık karar 5):** B ile birlikte yapılacak.
> - **Tanı sayaçları (açık karar 3):** compiler map tanısı da base register
>   tanısı da **olmayacak**. Sadece simülasyon ve eşleşme doğruluğunu
>   kontrol eden teknik sayaçlar kalır: `diag_store_map_evicted`,
>   `*_split_insts`, `*_extra_fragments`, `spill_reuse_log2`.
>
> **Uygulama (2026-11-04):**
> - Detector, CPU, request flag'leri ve cache istatistikleri schema 10'a
>   geçti; Plan C sayaçları kaldırıldı.
> - Binary ayrı dizinde: `build/RISCV_SCHEMA10/gem5.opt`. `build/RISCV` schema
>   9 olarak kaldı (yedeği `gem5.opt.schema9`).
> - Testler 22 vakaya indi; tc4a–tc4h `tests/spill_test/retired_schema9/`
>   altına taşındı.
> - Runner, SimPoint ve rapor script'leri güncellendi; schema 9 sonuçları
>   `--schema 9` ile okunabiliyor.
>
> **Karar kaydı, 2026-11-05 (kullanıcı, ChatGPT değerlendirmesiyle):**
>
> | # | Karar | Uygulama |
> |---|---|---|
> | 1 | Başlangıç adresi eşleşmesi korunur; load'un bütün byte sahiplerini saymak ileride ayrı bir genişletme olarak değerlendirilir | kod değişmedi; tc21 A kuralı sabitliyor |
> | 2 | Kısmen ezilen store, geçerli byte'ı kaldıkça tabloda kalır | zaten böyleydi; tc21 D, tc22 A |
> | 3 | Silent store yeni dinamik store sayılır | zaten böyleydi; tc22 B |
> | 4 | Warmup store → ROI load ana istatistiklere girmez | SimPoint shadow tracking kaldırıldı (`beginShadowTracking`, `spillShadowBegin`); Python'dan açılan ROI artık ilk instruction'ı da sayıyor; tc24 |
> | 5 | Ana raporda `spill_event` kullanılır | rapor script'leri |
> | 6 | Matched stack, unmatched stack ve non-stack store ayrı gösterilir | sayı, oran ve L1 miss rate olarak üçlü ayrım |
> | 7 | Cache erişimi bazlı hit/miss devam eder; L2 local miss rate ana metrik | L2 sütunları "local" olarak etiketlendi; non-stack store için L2 oranı yok (gem5 L2 sayaçları ayırmıyor) |
> | 8 | Atomic işlemler kapsam dışı; başarısız SC yazma sayılmaz | LR/SC/AMO hiçbir zaman stack store veya spill load değil; başarılı SC ve AMO yazdığı byte'ların sahibi olur; başarısız SC hiçbir şeyi değiştirmez; tc23 |
> | 9 | Testlere ROI/warmup, kısmi eşleşme ve atomic durumlar eklenir | tc22, tc23, tc24 (toplam 25 vaka) |
> | 10 | Tezde "runtime-detected stack store–load reuse" terimi kullanılır | dokümanlar |
>
> **Karar kaydı, 2026-11-05 öğleden sonra (kullanıcı): sayaç isimlendirmesi.**
> `total_` = bütün simülasyon, `roi_` = ROI içi, cache sonuçları
> `roi_<kategori>_<l1|l2>_<hits|misses>`. Ana sayaçlar: `total_insts`,
> `total_load`, `total_store`, `roi_total_insts`, `roi_load`, `roi_store`,
> `roi_spill_store`, `roi_spill_load`; yardımcı: `roi_stack_store`.
> `spill_event`/`spill_store`/`roi_spills` tek isimde birleşti:
> `roi_spill_store` (yukarıdaki 5. kararın yerine geçer). Tekrar eden alanlar
> (`spill_event`, `*_extra_fragments`) kaldırıldı; oranları script'ler
> hesaplar; gem5 `stats.txt` isimleri doğrulama için aynen kaldı. Eski → yeni
> tablo ve bağımlılık listesi: [`COUNTER_NAMING.md`](COUNTER_NAMING.md).
> **2026-11-08 güncellemesi (kullanıcı):** kanonik ad `roi_spill_event`
> oldu (`roi_spill_store` → `roi_spill_event`, cache sonuçları
> `roi_spill_event_*`, `diag_event_after_stack_release`). Gerekçe: compiler
> anlamında spill store, okunsun okunmasın allocator'ın ürettiği store'dur;
> bizim saydığımız ise doğrulanmış store→reload çifti. Yazıldığı anda bir
> store sadece `roi_stack_store`'dur. Değerler değişmedi (27 test, 1123
> alan).
> **2026-11-09 güncellemesi (kullanıcı):** ayrı bir "stack store" kavramı
> yok: stack şartı spill store şartlarından biri. `roi_stack_store` →
> **`roi_spill_store`**: ROI içinde spill store şartlarını sağlayan bütün
> store'lar, geri okunsun okunmasın. Bunlardan en az bir kez geri okunanlar
> `roi_spill_event`. Store kümeleri: spill store / geri okunmayan spill store
> (`roi_spill_store − roi_spill_event`) / diğer store (`roi_store −
> roi_spill_store`). Oranlar sadeleşti: `spill/roi`, `spill_load/load`,
> `spill_store/store`, `spill_event/store`, `spill_event/spill_store`,
> `spill/mem`. Değerler değişmedi (27 test, 1123 alan).
> Aynı gün kaldırıldı (kullanıcı): `diag_insts_before_roi` (aynı bilgi gem5'in
> ROI öncesi bloğunda var) ve `roi_spill_event_reuse_log2[k]` (raporlarda
> kullanılmıyordu). Kalan tanılar: `diag_store_map_evicted`,
> `roi_<küme>_split_insts`, `diag_load_after_stack_release`,
> `diag_event_after_stack_release`.
> Sayım semantiği değişmedi (25 testin bütün alanları eski ve yeni binary'de
> birebir aynı).
>
> **Karar kaydı, 2026-11-06 (kullanıcı): önce ölç.** Frame yeniden
> kullanımındaki şüpheli eşleşmeler için tanı sayacı eklendi:
> `diag_load_after_stack_release` ve
> `diag_store_first_reload_after_stack_release`. Ana tanım ve sayaçlar
> değişmedi; `sp` sadece stack alanının ömrü için okunuyor; parametre
> `spill_track_stack_release` (varsayılan açık). Testler: tc25 (ölü frame
> okuması bilinen sınırlama olarak sabitli, tanı 1/1), tc26 (yeni stack
> sayfasına ilk store bir kez sayılır). Oran ihmal edilebilirse algoritma
> korunur; önemliyse frame-ömrü kuralı ayrıca değerlendirilir.
>
> **Ölçüm sonucu (2026-11-06, test small-2way, tanı açık):**
>
> | benchmark | şüpheli spill load | / roi_spill_load | şüpheli spill store | / roi_spill_store |
> |---|---|---|---|---|
> | gcc | 22 | %0,0018 | 0 | %0 |
> | imagick | 33 | %0,0008 | 2 | %0,0001 |
> | xalancbmk | 4.358 | %0,0199 | 2.006 | %0,0104 |
> | blender | 277 | %0,0003 | 1 | %0,0000 |
>
> Ana sayaçlar ve `stats.txt` tanı açık/kapalı birebir aynı (27 test,
> imagick ve xalancbmk). Maliyet ölçülemeyecek kadar küçük (imagick +%1,2,
> xalancbmk −%0,4; gürültü düzeyi). Sonuç: ihmal edilebilir, mevcut
> algoritma korunuyor, frame-ömrü kuralı eklenmiyor; tanı kampanyada açık
> kalıyor. Koşular: `logs/validation_diag_20261106/`.

Hazırlanma tarihi 2026-11-04. Satır numaraları o günkü çalışma ağacına göre
verildi (branch `fix/spill-metrics-correctness`, commit `e0a12aa4e3` ve commit
edilmemiş değişiklikler). Kod değişirse satırlar kayar. Bu yüzden her maddede
bir sembol adı da var; `grep -n <sembol>` ile yeniden bulunur. Yollar repo
köküne göredir.

## 0. Bugünkü durum

| | |
|---|---|
| Aktif yol | **A: spill = compiler etiketi** (metric schema 9). Store çalışırken PC'si compiler'ın spill listesinde (`-dP`, `%sfp`) ya da CFI csave listesinde ise etiketlenir. |
| gem5 binary | değişmiyor (`build/RISCV/gem5.opt`) |
| Sayaçlar | **silinmiyor** (2026-11-04 kullanıcı kararı) |
| Xeon kuyruğu | schema 9 ile devam ediyor (full ref + roms train) |
| Raporlar | 2 Kasım kararı: ana sütun spill + csave; sadece compiler spill ek satır |

Bu belgedeki iki plan A'yı değiştirmez. Amaç şu: ileride "şunu yapalım"
dendiğinde neyin, nerede ve hangi sırayla değişeceği hazır olsun.

- **Plan B:** saf adres kuralı (schema 10). Sınıflandırma kalkar, gem5 değişir
  ve her şey yeniden koşulur.
- **Plan C:** gereksiz sayaçların koddan kaldırılması. B ile birlikte ya da tek
  başına yapılabilir.

---

## 1. Plan B: Saf adres kuralı (schema 10)

### 1.1 Amaç ve bedeli

**Amaç:** spill'i compiler bilgisi olmadan, sadece runtime davranışından (adres
ve sıra) tespit etmek. Hedeflenen optimizasyon hardware-only ise, ölçülen şey de
bu tespit mekanizması olmalı.

**Bedel:** spill olmayan stack tekrar kullanımları da spill sayılır: local
array, struct, string buffer ve pointer üzerinden erişilen stack değişkenleri.

Örnek: `mcf.c:162` satırındaki `strcpy(outfile, "mcf.out")` bir `sd a5,0(sp)`
üretir. libc'deki `fopen` bu buffer'ı bir pointer üzerinden okur. B'de bu bir
spill event olur, A'da olmaz.

Mevcut veriden ölçülen fark (test, small-2way, spill load'ların bütün load'lara
oranı):

| benchmark | compiler spill | spill + csave | saf adres kuralı |
|---|---|---|---|
| mcf | %2.11 | %3.87 | %27.03 |
| leela | %1.25 | %15.91 | %81.09 |
| gcc | %2.18 | %34.38 | %41.69 |
| x264 | %13.47 | %18.06 | %30.47 |
| lbm | %27.79 | %27.79 | %27.79 |
| perlbench_makerand | %0.00 | %28.89 | %28.90 |
| cactuBSSN | %51.31 | %51.49 | %76.27 |
| blender | %2.72 | %20.20 | %44.16 |
| omnetpp | %0.19 | %28.51 | %36.45 |

Saf adres kuralı sütunu `stack_load + diag_nonspill_reuse` ile hesaplandı; bu
load sayısı kesindir. mcf'te saf adres kuralının spill dediği 2,193,116,054
load'un %7.82'si compiler spill reload'u, csave eklenince %14.30'u.

### 1.2 Tanım

Kalan şartlar aşağıda. Numaralar 2026-11-04 sohbetindeki S1–S7 / L1–L8
listesiyle aynı.

**Store**

| # | şart | kod |
|---|---|---|
| S1 | instruction bir store (atomic/AMO hariç; AMO için hook yok) | `src/cpu/simple/timing.cc:657`, `:702` |
| S2 | ROI içinde | `src/cpu/simple/spill_detector.cc:316` |
| S3 | adres stack'te (`[stackMin, stackBase)`) | `spill_detector.cc:241`, `:472` |
| S4 | fault olmadan commit edildi | `timing.cc:862` / `:911` |
| ~~S5~~ | ~~PC compiler spill listesinde~~ → **kalkar** | `spill_detector.cc:218` |
| ~~S6~~ | ~~PC CFI csave listesinde~~ → **kalkar** | `spill_detector.cc:220` |
| ~~S7~~ | ~~base register `sp`/`s0`~~ → **kalkar** | `spill_detector.cc:222`, `timing.cc:149` |

**Load**

| # | şart | kod |
|---|---|---|
| L1 | instruction bir load | `timing.cc:568` |
| L2 | ROI içinde | `spill_detector.cc:269` |
| L3 | adres stack'te | `spill_detector.cc:266` |
| L4 | load'un başlangıç adresi, o byte'ı en son yazan store'un `[adres, adres + size)` aralığında | `spill_detector.cc:275`, `:513` |
| L5 | load, store'dan sonra | `spill_detector.cc:452` |
| L6 | commit anında o store hâlâ en yeni | `spill_detector.cc:372` |
| L7 | fault olmadan commit edildi | `timing.cc:911` |
| ~~L8~~ | ~~eşleşen store'un sınıfı ve load'un `sp`/`s0` base register şartı~~ → **kalkar** | `spill_detector.cc:288-292` |

**Spill event** = bir spill store + onun ilk spill load'u.

### 1.3 Açık karar: "spill store" ne demek?

Store'un tag'i ve cache hit/miss sonucu store çalışırken belli olur. Store'un
ileride geri okunup okunmayacağı o anda bilinmez.

| seçenek | içerik | sayaçların kaynağı |
|---|---|---|
| (i) geri okunan stack store'ları | en az bir kez geri okunan store'lar | sadece detector (`diag_paired_*`). gem5 bunu store anında bilemez. |
| (ii) bütün stack store'ları | S1–S4'ü sağlayan her store; local array yazmaları dahil | gem5 `spillStoreHits/Misses` + detector `spill_store_*` |

B'de iki tally de üretilir. Karar, hangisinin ana tablo olacağıdır.

Bugünkü A verisinde iki seçenek arasındaki fark (mcf, compiler spill):

| | bütün store'lar | geri okunanlar |
|---|---|---|
| store sayısı | 214,228,672 | 91,410,910 |
| L1D miss rate | %8.28 | %15.10 |

### 1.4 Kod değişiklikleri

**Detector** (`src/cpu/simple/spill_detector.{hh,cc}`)

| yer | sembol | değişiklik |
|---|---|---|
| `.cc:67` | `METRIC_SCHEMA` | 9 → 10 |
| `.hh:63-65` | `StackClass`, `NumStackClasses` | tek sınıf (Spill / None), `NumStackClasses = 1` |
| `.cc:70-71`, `:81-88` | `CLASS_PREFIX`, `className` | sadece `"spill"` |
| `.cc:217-222` | `classifyStore` | S1–S4'ü sağlayan her store Spill olur; PC map ve base register'a bakılmaz |
| `.cc:249` | `classifyStore` çağrısı | imza değişir (`sp_fp_relative` gitmez) |
| `.cc:288-292`, `.hh:177` | L8 kuralı, `predicted_nonspill_reuse` | eşleşen her store için `cls = Spill`; alan kalkar |
| `.cc:397-413`, `.hh:246`, `.hh:250-251` | `roi_spill_reload_unmapped`, `roi_nonspill_reuse`, `roi_spill_load_pc_other_store` | kalkar |
| `.hh:208-216`, `.cc:158` | `pc_map_path`, `spill_store_pcs`, `spill_load_pcs`, `csave_store_pcs`, `hasPcMap`, `configurePcMap` | kalkar, ya da tanı amaçlı kalır (açık karar 3) |
| `.cc:679-685` | `classification`, `stack_pc_map`, `map_*` metadata satırları | `classification : pure_address` |
| `.cc:687-707` | DEFINITIONS metni | yeni tanım (1.2) |
| `.cc:714-721` | `writeClassBlock` × 4 (stack + 3 sınıf) | tek `spill` bloğu |
| `.cc:722-729` | üç tanı satırı | kalkar |
| `.cc:768-772` | GLOBAL `total_stack_event`, `total_<c>_event` | tek `total_spill_event` (ya da Plan C ile tamamen kalkar) |

**CPU** (`src/cpu/simple/`)

| yer | sembol | değişiklik |
|---|---|---|
| `timing.cc:128-140` | `stackClassFlag` | sadece `SPILL_LOAD` / `SPILL_STORE` |
| `timing.cc:142-160` | `isSpFpRelativeMemInst` | kalkar (tanı istenirse kalır, açık karar 3) |
| `timing.cc:201` | `configurePcMap(p.stack_pc_map)` | kalkar |
| `timing.cc:568-570`, `:657-659` | `onLoadInstruction` / `onStoreInstruction` çağrıları | `sp_fp_rel` argümanı gider |
| `BaseTimingSimpleCPU.py:55-63` | `stack_pc_map` param | kalkar, ya da "yok sayılır" notu |

**Request ve cache** (`src/mem/`)

| yer | sembol | değişiklik |
|---|---|---|
| `request.hh:276-280` | `CSAVE_LOAD/STORE`, `STACK_OTHER_LOAD/STORE` | kalkar |
| `request.hh:1059-1069` | `isCsave*`, `isStackOther*`, `isStackTagged` | sadece spill flag'leri |
| `cache/base.hh:1220-1246`, `cache/base.cc:2435-2450` | `csave*`, `stackOther*` stat'ları | kalkar |
| `cache/base.hh:1476-1487` | `countStackAccess` dalları | sadece spill dalları |
| eviction sayaçları | (bkz. 2.3, madde 17) | B'de "spill" her stack erişimi anlamına gelir; Plan C ile kaldırılmaları önerilir |

`scripts/build_stack_pc_map.py` B'de de **silinmez.** Offline referans
(ground truth) olarak kalır; B'nin sonuçları compiler listesiyle bununla
karşılaştırılır.

### 1.5 Testler (`tests/spill_test/run_tests.py`)

| yer | değişiklik |
|---|---|
| `:48` | sınıf listesi (`spill` / `csave` / `other_stack`) → tek sınıf |
| `:80-82` | beklenen tanı sıfırları kalkar |
| `:120-205` `CASES` | beklenen değerler: |
| | `tc1_callee_save`: csave → spill |
| | `tc2`, `tc3`, `tc5`–`tc7`, `tc9`, `tc10`, `tc11`, `tc21`: other → spill |
| | `tc8_address_base`: bugün negatif (`diag_nonspill_reuse=1`), B'de **pozitif** (1 spill event) |
| | `tc4b`, `tc4c`: `diag_nonspill_reuse=1` → spill |
| | `tc14_stack_pc_map`: map testi; kaldırılır ya da "map yok sayılıyor" testine çevrilir |
| | `tc19_addressing_forms`: base register varyantlarının hepsi pozitif olur |
| | `tc10_negative_pairs`: sadece base register yüzünden negatif olan çift varsa pozitife döner; tek tek kontrol edilmeli |
| `:435-464` | `stack_*` toplam kontrolleri (umbrella) tek sınıfta gereksiz |
| yeni test | pointer ile stack'e yazma, başka register ile okuma (`addi t0,sp,16; sd a0,0(t0)` → `ld a1,16(sp)`): pozitif olmalı |

Kabul şartı: bütün testler geçer.

### 1.6 Script ve dokümanlar

| yer | değişiklik |
|---|---|
| `cache_scripts/cache_status.py:231` | `CURRENT_SCHEMA = 9` → 10 |
| `cache_scripts/cache_status.py:504` (`counts`), `:579` (`cache_misses`) | spill + csave toplama mantığı → tek sınıf |
| `scripts/spill_report.py:31`, `:34-35` | `SCHEMA`, `CLASSES` |
| `scripts/spill_report.py:220-285` | sınıf döngüleri, gem5 = detector eşitlik kontrolleri |
| `scripts/spill_report.py:340-430` | csave / other tablo sütunları |
| `scripts/spec_spill_runner.sh:2`, `:691`, `:766`, `:887` | schema 9 kontrolleri |
| `scripts/spec_spill_runner.sh:856`, `cache_scripts/simpoint.sh:382`, `cache_scripts/smoke_test.sh:47` | `stack_pc_map` argümanı |
| `cache_scripts/export_results.py:35-46` | `ROI_FIELDS` |
| `cache_scripts/benchmark_reports.py:39-40`, `:139` | csave / other_stack satırları |
| `cache_scripts/simpoint_combine.py:125-141` | rate satırları ve `total_<c>_event` yeniden yazımı |

**Ayrı binary için ek işler:**
- `scripts/build_gem5_riscv.sh:63-73` sadece `build/RISCV` derliyor; hedef
  dizin parametresi gerekir.
- `cache_scripts/run_on_host.sh:34` içinde `GEM5` yolu sabit.
- `scripts/launch_spill_batch.sh:48` içindeki `pgrep 'build/RISCV/gem5.opt'`
  yeni binary'yi görmez; slot sayımı bozulur.
- `scripts/spec_spill_runner.sh:9` binary'yi zaten `GEM5_BIN` env ile seçebiliyor.

**Dokümanlar:** `SPILL_STUDY.md`, `scripts/README.md`,
`scripts/SPEC_SPILL_RUNNER.md`, `tests/spill_test/README.md`,
`general_reports/definitions/spill_definition.tex`.

### 1.7 Build ve koşu planı

1. **Ayrı build dizini:** `build/RISCV_SCHEMA10/gem5.opt`.
   - `build/RISCV/gem5.opt` **asla** değişmez. Xeon aynı diski
     (`/cta/users`) kullanıyor; değişirse kuyruktaki koşular yeni binary ile
     başlar.
   - Herhangi bir rebuild'den önce eski binary hard-link ile yedeklenir.
2. Testler (1.5).
3. Doğrulama koşusu: mcf test small-2way (1.8).
4. Sıra: test (5 config) → SimPoint ref → train → full ref.
5. Xeon kuyruğu: açık karar 4.
6. Schema 9 sonuçları silinmez; status ve report script'leri sonuçları
   schema'ya göre ayırır.

**Maliyet (tahmini):**

| set | CPU süresi | en uzun koşu |
|---|---|---|
| test | ~92 CPU-gün | x264 ~7 gün |
| train | ~450+ CPU-gün | roms ~17–20 gün |
| SimPoint ref | ~30 CPU-gün | |
| full ref (15 benchmark × 5 config) | | ~16 gün (wall) |
| **Toplam, xeon 45 slot** | | **~3–4 hafta (wall)** |

SimPoint checkpoint'leri (129 GB) geçerli kalır; yeniden üretilmez.

### 1.8 Doğrulama

Aynı workload ve aynı config ile schema 9 çıktısına karşı kontrol edilir:

| kontrol | beklenen | mcf test small-2way |
|---|---|---|
| yeni `spill_load` | = eski `stack_load + diag_nonspill_reuse` (**tam eşitlik**) | 314,417,813 + 1,878,698,241 = 2,193,116,054 |
| `roi_total_insts`, `roi_load`, `roi_store` | eskiyle birebir aynı | 24,426,982,047 / 8,113,038,194 / 1,300,581,564 |
| gem5 standart cache stat'ları (`demandAccesses/Misses`, `l2.demandHits/Misses`, `writebacks`) | eskiyle birebir aynı (tag timing'i değiştirmez, `spill_bypass_alloc = False`) | `dcache.demandAccesses` = 9,413,619,758 |
| yeni `spill_store` | ≥ eski `stack_store` | ≥ 386,415,784 |
| yeni `spill_event` | ≥ eski `stack_event` | ≥ 234,360,896 |
| `diag_store_map_evicted` | 0 (sınıfsız store'lar zaten tabloya yazılıyordu, tablo boyutu değişmez) | 0 |
| gem5 `spill*Hits/Misses` | detector'deki karşılıklarına eşit | |

### 1.9 Tezde yazılacak sınırlamalar

- B "register spill" değil, "stack store → reload" trafiğini ölçer. Bir üst
  sınır olarak sunulmalı.
- Compiler listesiyle (A) karşılaştırma tablosu verilmeli (1.1'deki tablo).

---

## 2. Plan C: Gereksiz sayaçların koddan kaldırılması

### 2.1 Kurallar

- **Şu an yapılmıyor:** A devam ediyor ve sayaçlar kalıyor.
- Bu bir binary değişikliği. Ayrı build dizini ve yeni bir schema numarası
  gerekir, çünkü çıktı formatı değişir ve script'ler schema'yı kontrol ediyor.
  B ile birlikte yapılırsa aynı schema 10 kullanılır.
- Sayaç kaldırmak diğer sayaçların değerini değiştirmez. C tek başına
  yapılırsa yeniden koşu bilimsel olarak gerekmez. Ama kalan bütün alanlar aynı
  workload'un schema 9 çıktısıyla birebir aynı olmalı (2.4).
- Okuyan script ve testler aynı değişiklikte güncellenir. Script'ler eski
  çıktılardaki fazla satırları yok saymaya devam etmeli ki schema 9 sonuçları
  okunabilir kalsın.
- **Öneri:** B yapılacaksa C onunla birlikte yapılsın (tek rebuild, tek test
  turu).

Karar sütunundaki ifadeler:
- **kaldır:** her durumda kaldırılabilir.
- **sadece B ile:** A'da gerekli, B'de kalkar.
- **koşullu:** bir karara bağlı.
- **kalsın:** kaldırılmaz.

### 2.2 Detector sayaçları (`riscv_spill_stats.txt`)

`<c>` = `stack`, `spill`, `csave`, `other_stack`. `<yan>` = `store`, `load`.
Dosyalar `src/cpu/simple/spill_detector.{hh,cc}`.

| # | sayaç | tanım yeri | yazıldığı yer | okuyanlar | karar | neden |
|---|---|---|---|---|---|---|
| 1 | `<c>_event_rate`, `<c>_inst_rate` | – (yazarken hesaplanıyor) | `.cc:629-634` (`writeClassBlock`) | `cache_scripts/simpoint_combine.py:137-141` (yeniden hesaplıyor) | **kaldır** | oranları script'ler kendisi hesaplıyor |
| 2 | `<c>_<yan>_l1_accesses` | `.hh:132` `CacheTally::l1_accesses` | `.cc:637` | `scripts/spill_report.py:251-252` (eşitlik kontrolü), `tests/spill_test/run_tests.py:151-157` | **kaldır** | = hits + misses |
| 3 | `total_<c>_insts` | – | `.cc:623` | `simpoint_combine.py:140`, `run_tests.py:62`, `:461` | **kaldır** | = store + load |
| 4 | `<c>_store_unpaired` | – | `.cc:626-627` | `cache_scripts/export_results.py:36`, `spill_report.py:231`, `:253`, `run_tests.py:63`, `:456` | **kaldır** | = store − event |
| 5 | `repeat_<c>_load` | `.hh:150` `ClassCounters::repeat_load` | `.cc:628` | `export_results.py:36`, `spill_report.py:230`, `run_tests.py:61`, `:454` | **kaldır** | = load − event |
| 6 | `diag_store_map_live`, `diag_store_map_peak` | `.hh:264` `store_map_high_water` | `.cc:730-731` | yok | **kaldır** (düşük öncelik) | sadece bilgi amaçlı |
| 7 | GLOBAL `total_stack_event`, `total_<c>_event` | `.hh:222` `total_events` | `.cc:768-772` | `simpoint_combine.py:125-127` | **kaldır** | tek ROI'de ROI değeriyle aynı |
| 8 | `diag_paired_<c>_store_*` | `.hh:153` `paired_store_cache` | doldurma `.cc:389`, yazma `.cc:650` | `run_tests.py:157-159`, `:464` | **koşullu** | B'de "spill store = geri okunanlar" seçilirse ana tablo olur. "Geri okunanlar" ek analizi istenirse en az spill sınıfınınki kalmalı (gem5 bu sayıyı üretemez). Diğer sınıflarınki kaldırılabilir. |
| 9 | `<c>_<yan>_split_insts`, `<c>_<yan>_extra_fragments` | `.hh:137-138` | sayma `.cc:104-105`, yazma `.cc:642-644` | `run_tests.py:153-158` (`tc11_split_line`) | **kalsın** (test için), rapora girmesin | cache line'a bölünen erişim kontrolü |
| 10 | `<c>_reuse_log2[k]` | `.hh:156` `reuse_hist` | `.cc:733-745` | `run_tests.py:193`, `:209`, `:258`; `spill_report.py:73` bu satırları atlıyor | **kalsın** (pasif) | ileride spill buffer kapasite analizi için |
| 11 | `diag_store_map_evicted` | `.hh:263` `evicted_stores` | `.cc:732` | `export_results.py:45`, `spill_report.py:258`, `:281` | **kalsın** | sessiz kayıt kaybını yakalar |
| 12 | `csave_*` ve `other_stack_*` blokları (sayım + cache) | `.hh:242` `roi_class[]` | `.cc:716-721` | `export_results.py:37-39`, `cache_scripts/benchmark_reports.py:39-40`, `spill_report.py` | **sadece B ile** | A'da csave spill tanımının parçası; other_stack saf adres önizlemesinde kullanılıyor |
| 13 | `diag_nonspill_reuse`, `diag_spill_reload_unmapped`, `diag_spill_load_pc_other_store` | `.hh:246`, `.hh:250-251` | `.cc:722-729` | `export_results.py:44-45`, `spill_report.py:257-268`, `run_tests.py:80-82` | **sadece B ile** | A'da map tutarlılığı ve saf adres önizlemesi için gerekli |
| 14 | `map_spill_store_pcs`, `map_spill_load_pcs`, `map_csave_store_pcs` | `.hh:210-212` | `.cc:683-685` | yok | **sadece B ile** | A'da map'in yüklendiğinin kanıtı |

### 2.3 gem5 cache sayaçları (`stats.txt`, her cache için ayrı)

| # | sayaç / param | yer | okuyanlar | karar | neden |
|---|---|---|---|---|---|
| 15 | `csaveLoadHits/Misses`, `csaveStoreHits/Misses` | stat `src/mem/cache/base.hh:1239-1242`; kayıt `base.cc:2435-2442`; sayma `base.hh:1476-1481`; flag `src/mem/request.hh:276-277`, `:1059-1060`; `timing.cc:133-134` | `spill_report.py:34`, `:269-279` (detector = gem5 kontrolü), `run_tests.py:48` | **sadece B ile** | A'da spill + csave tanımının parçası |
| 16 | `stackOtherLoadHits/Misses`, `stackOtherStoreHits/Misses` | `base.hh:1243-1246`, `base.cc:2443-2450`, `base.hh:1482-1487`; flag `request.hh:279-280`, `:1061-1062`; `timing.cc:135-136` | aynı | **koşullu** | A'da raporda kullanılmıyor, kaldırılabilir. Ama o zaman detector'deki other_stack cache değerlerinin gem5 kontrolü de gider. B'de zaten kalkar. |
| 17 | 8 eviction sayacı (liste aşağıda) | aşağıda | aşağıda | **kaldır** | raporda yok; iki bilinen hata var; her cache'te 1M girişe kadar büyüyen bir ledger tutuyor |
| 18 | `spill_bypass_alloc` (param, sayaç değil) | `src/mem/cache/Cache.py:172-184`; üye `base.hh:403-408`; kullanım `base.hh:504-511` (`allocOnFill`); `base.cc:94` | yok | **kaldır** | hiç kullanılmamış bir deney |

**Madde 17'nin ayrıntısı:**
- **Sayaçlar:** `spillLoadEvictedBySpill`, `spillLoadEvictedByNonSpill`,
  `spillStoreEvictedBySpill`, `spillStoreEvictedByNonSpill`,
  `nonSpillLoadEvictedBySpill`, `nonSpillLoadEvictedByNonSpill`,
  `nonSpillStoreEvictedBySpill`, `nonSpillStoreEvictedByNonSpill`.
- **Kodun yeri:**
  - stat tanımları `base.hh:1248-1300`
  - ledger, `recordEviction` ve `attributeMiss` bildirimleri `base.hh:410-458`
  - çağrı `base.hh:1436-1448` (`incMissCount`)
  - yakalama `base.cc:1712-1735` (`allocateBlock`)
  - gövdeler `base.cc:1750-1812`
  - kayıt `base.cc:2451-2474`
- **Okuyanlar:**
  - `cache_scripts/cache_status.py:389-420` (`EVICT`, `evictions`,
    `pollution`, `unattributed`)
  - `cache_status.py:721-760` `show_cache_tables`; bu fonksiyon hiç
    çağrılmıyor (`:830-831`)
  - `run_tests.py:124-141` ve `tests/spill_test/tc4a…tc4h` (8 test dizini)
- **Bilinen hatalar:**
  - L2'de store `ReadExReq` olarak gelir ve load kutusuna düşer.
  - Ledger ROI'den bağımsız tutuluyor.

**Kaldırılmayacaklar** (iki planda da):
- `roi_total_insts`, `roi_load`, `roi_store`; `entry_total_insts` (SimPoint
  hizalaması için); GLOBAL `total_insts`, `total_load`, `total_store`.
- `spill_store`, `spill_load`, `spill_event` ve spill L1/L2 hit/miss; hem
  detector'deki karşılıkları hem gem5 `spill*Hits/Misses`.
- `countStackAccess` ve `recordStackCacheOutcome` (`base.hh:1464-1491`,
  `request.hh:1072`): cache sonucunu detector'e taşıyan yol.
- `src/mem/cache/tags/fa_lru.cc` (`tagsInit` bug fix) ve `src/mem/physical.cc`
  (checkpoint restore'da bellek tasarrufu). Bunlar sayaç değil.

### 2.4 Plan C'nin doğrulaması

- Bütün testler geçer: eviction testleri silinir, `tc11_split_line` kalır.
- Aynı workload'da kalan bütün alanlar schema 9 çıktısıyla birebir aynıdır;
  gem5 standart stat'ları da birebir aynıdır.
- `spill_report.py`, `cache_status.py` ve `export_results.py` hem eski hem
  yeni çıktıyı okuyabilir.

---

## 3. Açık kararlar

Hangisi seçilirse plan ona göre güncellenir.

1. **B yapılacak mı?** Bugünkü cevap: hayır, A ile devam.
2. **B'de "spill store":** geri okunanlar mı, bütün stack store'ları mı (1.3)?
3. **B'de tanı sayaçları:**
   - compiler listesi tanısı: map verilirse, B'nin bulduklarının kaçının
     compiler spill olduğunu sayar; A ve B aynı koşudan çıkar.
   - base register tanısı.
   - hiçbiri.
4. **Xeon kuyruğu** (B başlarsa):
   - yeni binary hazır olunca durdur (önerilen)
   - full ref bitsin
   - hemen durdur
5. **C:** B ile birlikte mi, ayrı mı, hiç mi?
6. **Plan dışı, writeback trafiği:** dirty line writeback'leri bugün spill'e
   atanmıyor (mcf ROI'de 246,388,373 writeback var). Tez L1 ötesindeki trafik
   hakkında iddia kuracaksa bunun için bir sayaç gerekir; bu da gem5
   değişikliği ve yeniden koşu demektir.

## 4. Önerilen sıra (onay verilirse)

1. 3. bölümdeki kararlar verilir.
2. Ayrı build dizini kurulur, kod değişiklikleri (B ve/veya C) yapılır.
3. Testler.
4. mcf test small-2way doğrulaması (1.8 ve 2.4).
5. test → SimPoint ref → train → full ref.
6. Raporlar ve dokümanlar güncellenir.

Her adımın sonunda kullanıcıya rapor verilir. Uzun ve pahalı koşulardan önce
ayrıca onay alınır.

---

## 5. Onay kuralı

**Bu README yürürlükte değildir.** Kullanıcının (bkaya) açık onayı olmadan bu
belgedeki hiçbir adım uygulanmaz. Bunlara kod değişikliği, build, test, koşu
başlatma veya durdurma ve xeon kuyruğuna dokunmak dahildir.

**Saf Adres Planı (Plan B) için kullanıcıdan mutlaka onay alınmalıdır.**
"Bu belgeyi uygula" gibi genel bir ifade yetmez. Şunlar ayrı ayrı ve açıkça
onaylanmalı:
- hangi plan uygulanacak (B, C veya ikisi);
- "spill store"un anlamı (1.3);
- tanı sayaçları (açık karar 3);
- xeon kuyruğunun ne olacağı (açık karar 4).

Claude veya başka bir agent bu belgeyi okuduğunda kendiliğinden işe
başlamamalı; önce kullanıcıya sormalı ve onayını beklemelidir.
