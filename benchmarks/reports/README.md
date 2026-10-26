# Register Spilling — Rapor ve Log Klasörü

Son güncelleme: 2026-08-03

## İçindekiler

- **`combined_spill_report.tex`** — Ana rapor (hocam için tek dosya).
  15 SPEC CPU2017 benchmark'ının orijinal cache konfigürasyonuyla
  (L1D=32kB, L2=256kB) tam sonuçları + yeni eklenen bölüm:
  **"Follow-Up Experiment: Small-Cache Robustness Check (v2 Spill
  Detector)"** (Conclusion'dan hemen önce). Bu yeni bölüm küçük cache
  (L1D=4kB, L2=32kB) + yeni spill tanımıyla (pencere yok + SP/FP
  filtre + çoklu reload) alınan sonuçları ve "DRAM'e taşma beklenenden
  az çıktı, bu bir cache-boyutu artefaktı değil" bulgusunu içeriyor.
  **PDF'e derlemek için bu makinede pdflatex kurulu değil** — Overleaf'e
  yükleyin ya da pdflatex olan bir makinede derleyin.

- **`generate_reports.py`** — Orijinal raporu (Mayıs 2026, eski cache
  config) üreten script. Bu güncellemede DOKUNULMADI — yeni bölüm
  elle `combined_spill_report.tex`'e eklendi (RAW_* dict'leri
  small-cache/v2 verisini henüz modellemiyor).

- **`summary_test_v2.txt` / `summary_train_v2.txt` / `summary_train_sc_v2.txt`**
  `analyze_spill_cache.sh --v2/--train-v2/--train-sc-v2 --detail`
  çıktıları (ham L1/L2/DRAM sayıları, benchmark başına).

- **`summary_*.csv`** — Aynı verinin CSV hali.

- **`logs/`** — Bu aşamaya kadarki üç güncel koşum grubunun ham
  gem5 çıktıları (`stats.txt`, `riscv_spill_stats.txt`, `nohup.log`):
  - `logs/test_v2/<bench>/` — 15 benchmark, test input, v2 spill tanımı (TAMAMLANDI)
  - `logs/train_v2/<bench>/` — 8 benchmark, train input, v2 spill tanımı, normal cache (TAMAMLANDI)
  - `logs/train_sc_v2/<bench>/` — 8 benchmark, train input, v2 spill tanımı, küçük cache
    (xalancbmk, gcc, povray, x264, nab, xz: TAMAMLANDI — mcf, omnetpp: BEKLİYOR,
    ~30-35 saat sürecek tier-2 koşumu henüz başlatılmadı/tamamlanmadı)

## Bekleyen iş

`mcf` ve `omnetpp` için small-cache v2 (train) sonuçları eksik. Başlatmak için:

```bash
cd /cta/users/bkaya/riscv-spec-register-spilling/gem5
nohup bash launch_train_sc_v2.sh --tier2 > tier2.log 2>&1 &
```

Bitince:
```bash
cd /cta/users/bkaya/riscv-spec-register-spilling/gem5/benchmarks
bash analyze_spill_cache.sh --train-sc-v2 --detail
```
