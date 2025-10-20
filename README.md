# gem5 Spill Test — Dev Environment Setup

This guide explains how to prepare a clean development environment on macOS (Apple Silicon) to work with **gem5** and RISC-V/x86/ARM binaries.  
The goal here is to:

- Create and activate a local Python virtualenv (`.venv`)  
- Build a reusable Docker image (amd64)  
- Run a container with your repo mounted at `/workspace`  
- Prepare the environment before running any gem5 or compiler steps  

---

## 🧩 0) Prerequisites

- macOS with Docker Desktop installed  
- Python 3.10+ available on host (for virtualenv)  
- A terminal (zsh or bash)

---

## 🐍 1) Clone and Set Up Python Virtual Environment

```bash
# Clone your repo
git clone <YOUR_REPO_URL> gem5
cd gem5

# Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# (Optional) Install requirements
# pip install -r requirements.txt
```

> 💡 Each time you open a new terminal, re-activate it with:
> ```bash
> source .venv/bin/activate
> ```

---

## 🐳 2) Create Dockerfile for Universal gem5 Toolchain

Create a file at `docker/dockerfile.dev` with this content:

```Dockerfile
# ---------------------------------------------------------
# Universal gem5 build environment for x86, ARM, RISC-V
# ---------------------------------------------------------
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y     build-essential scons python3 python3-pip git wget vim nano     gcc g++     gcc-aarch64-linux-gnu g++-aarch64-linux-gnu     gcc-arm-linux-gnueabi g++-arm-linux-gnueabi     gcc-riscv64-linux-gnu g++-riscv64-linux-gnu     qemu-user qemu-user-static     binutils-riscv64-linux-gnu     libprotobuf-dev protobuf-compiler libgoogle-perftools-dev     libpng-dev libcapstone-dev     && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
```

This installs **cross-compilers** for RISC-V, ARM (both 32-bit and 64-bit), and all necessary dependencies for gem5 builds.

---

## 🏗️ 3) Build the Docker Image (amd64)

Run the following from the **repo root** (where the `docker/` folder lives):

```bash
docker buildx build --platform linux/amd64   -t gem5-universal:latest   -f docker/dockerfile.dev .
```

> You only need to build this once.  
> Rebuild if you modify the Dockerfile.

---

## 🚀 4) Run the Container and Mount Your Workspace

Start the container and mount your current repo at `/workspace`:

```bash
docker run --rm -it   --platform linux/amd64   -v "$(pwd)":/workspace   gem5-universal:latest bash
```

You’ll now be inside the container, working at `/workspace` which is your **host repo**.  
All file changes inside the container will appear on your Mac.

---

## 🔍 5) Quick Checks Inside the Container

```bash
# Check where you are
pwd
ls -la

# Confirm cross-compilers exist
riscv64-linux-gnu-gcc --version
aarch64-linux-gnu-gcc --version
x86_64-linux-gnu-gcc --version || echo "(x86 cross compiler may not be installed; that's okay)"
```

If `file` is missing:
```bash
apt-get update && apt-get install -y file
```

---

## 📦 6) What You Have Now

✅ A reproducible **Docker image** with compilers  
✅ A **mounted workspace** under `/workspace`  
✅ A **local Python venv** on host for analysis tools  

> You’re ready to build and run your gem5 workloads.

---

## 🧱 7) (Optional) Build a RISC-V ELF from Assembly

Inside the Docker container:

```bash
# Compile gem5 m5ops for RISC-V (only if your code calls m5_work_* ops)
riscv64-linux-gnu-gcc -c   -I/workspace/include   /workspace/util/m5/src/abi/riscv/m5op.S   -o m5op.o

# Assemble your pure assembly test
riscv64-linux-gnu-gcc -nostartfiles -static   -I/workspace/include   /workspace/benchmarks/builds/test/verify/riscv/pure_asm_spill.S m5op.o   -o /workspace/benchmarks/builds/test/verify/riscv/pure_asm_spill.elf
```

> 💡 If your `.S` file doesn’t call `m5_work_begin` / `m5_work_end`,  
> you can skip linking `m5op.o`.

---

## 🧩 8) (Optional) Build gem5 for RISC-V

Still inside the container:

```bash
cd /workspace/gem5
scons build/RISCV/gem5.opt -j12

# (Optional) Also build for x86

scons build/X86/gem5.opt -j12
```

Run your custom test:

```bash
/workspace/gem5/build/RISCV/gem5.opt   /workspace/benchmarks/builds/test/verify/riscv/run_riscv_spill_test.py
```

---

## 📊 9) Analyze Results (Host-side)

Back on macOS (outside Docker):

```bash
source .venv/bin/activate
python3 benchmarks/analytics/advanced_spill_analysis.py m5out
```

The analyzer automatically detects your ISA from `config.json` and loads the corresponding spill stats file (e.g. `riscv_spill_stats.txt` or `x86_spill_stats.txt`).

Report output:
```
m5out/analysis_report.txt
```

---

## 🧠 10) Common Issues

| Issue | Cause / Fix |
|-------|--------------|
| `m5ops.h` not found | Add `-I/workspace/include` include path |
| “Unknown operating system” | Normal for SE mode |
| “Interrupt controller missing” | For RISC-V SE, ensure `system.cpu.createInterruptController()` is called |
| “File not found on host” | Ensure you started Docker with `-v "$(pwd)":/workspace` |
| “stats.txt empty” | The simulation didn’t reach m5_work_end or terminate cleanly |

## 🚧 11) Why do we need m5op.o?

The reason is so simple, we gotta create the m5op.o file for RISC-V if your assembly or C code uses any of the special gem5 "m5" pseudo-instructions (like m5_work_begin, m5_work_end, m5_exit, etc). These are used for simulation control, region-of-interest marking, or stats dumping inside gem5.

The file m5op.o is the compiled object file from m5op.S, which contains the RISC-V implementations of these pseudo-instructions.
When you link your test binary (like pure_asm_spill.elf), if your code calls any m5_* function, the linker needs the actual implementation, which is provided by m5op.o.
If you do not use any m5_* calls in your assembly, you can skip linking m5op.o.

---

## ⚡ 12) Quick One-Liners

```bash
# Activate host venv
source .venv/bin/activate

# Build Docker image
docker buildx build --platform linux/amd64 -t gem5-universal:latest -f docker/dockerfile.dev .

# Run container
docker run --rm -it --platform linux/amd64 -v "$(pwd)":/workspace gem5-universal:latest bash
```

---

## 🧭 Summary

You can now:
1. Activate your virtualenv (`.venv`)  
2. Launch Docker (`gem5-universal:latest`)  
3. Work seamlessly inside `/workspace`  
4. Build gem5 or assemble binaries  
5. Run simulations and analyze spill stats automatically  

That’s your **clean, reproducible base environment** for gem5 development 🎯
