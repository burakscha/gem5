#!/bin/bash
# gem5 RISC-V Simulator Build Script
# gem5 itself runs on x86-64, simulates RISC-V
#
# Kullanım:
#   bash build_gem5_riscv.sh           # artımlı build (değişen dosyalar)
#   bash build_gem5_riscv.sh --clean   # build/RISCV silinir, sıfırdan build
#
# Bu makinede sistem gcc'si YOK (/usr/bin/gcc kaldırılmış); derleyici olarak
# gem5_env conda ortamındaki x86_64-conda-linux-gnu-gcc/g++ kullanılır.
# scons'un config testleri "gcc" adında bir binary ve zlib yollarını
# bulabilsin diye toolchain-shim/ altında wrapper scriptler oluşturulur:
#   - girdi dosyalı çağrılara -I$ENV/include ve -L$ENV/lib -rpath eklerler
#   - --version/--verbose gibi girdisiz çağrılara flag eklemezler
#     (yoksa gcc "no input files" hatasıyla çıkar ve scons config bozulur)

set -euo pipefail
cd "$(dirname "$0")"

GEM5ENV=/cta/users/bkaya/miniconda3/envs/gem5_env
SHIM="$(pwd)/toolchain-shim"

# ── 1. Wrapper'ları (yeniden) oluştur ────────────────────────────────────
mkdir -p "$SHIM"
for pair in gcc:x86_64-conda-linux-gnu-gcc g++:x86_64-conda-linux-gnu-g++; do
    name=${pair%%:*}; real=${pair#*:}
    # ÖNCE sil: mevcut dosya bir symlink ise üzerine yazmak linkin
    # hedefini (conda'daki gerçek derleyiciyi!) bozar.
    rm -f "$SHIM/$name"
    cat > "$SHIM/$name" <<WRAP
#!/bin/sh
E=$GEM5ENV
link=0
for a in "\$@"; do
  case "\$a" in
    -*) ;;
    *) link=1; break;;
  esac
done
if [ \$link -eq 1 ]; then
  exec \$E/bin/$real -I\$E/include "\$@" -L\$E/lib -Wl,-rpath,\$E/lib
else
  exec \$E/bin/$real "\$@"
fi
WRAP
    chmod +x "$SHIM/$name"
done
rm -f "$SHIM/cc" "$SHIM/c++"
cp "$SHIM/gcc" "$SHIM/cc"
cp "$SHIM/g++" "$SHIM/c++"

echo "✅ Derleyici: $("$SHIM/gcc" --version | head -1)"

# ── 2. Temiz build istendiyse build dizinini sil ─────────────────────────
if [[ "${1:-}" == "--clean" ]]; then
    echo "🧹 build/RISCV siliniyor (temiz build)..."
    rm -rf build/RISCV
fi

# ── 3. Build ─────────────────────────────────────────────────────────────
echo "🔨 gem5 derleniyor..."
PATH="$SHIM:$GEM5ENV/bin:$PATH" scons build/RISCV/gem5.opt -j12 \
    CC="$SHIM/gcc" \
    CXX="$SHIM/g++" \
    PYTHON_CONFIG="$GEM5ENV/bin/python3-config"

if [[ ! -s build/RISCV/gem5.opt || ! -x build/RISCV/gem5.opt ]]; then
    echo "❌ Build hedefi eksik, boş veya çalıştırılabilir değil" >&2
    exit 1
fi

echo "✅ Build tamam: build/RISCV/gem5.opt"
