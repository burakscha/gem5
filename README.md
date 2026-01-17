# gem5 Development Environment & RISC-V Simulation Guide

This guide provides step-by-step instructions to set up a development environment for **gem5** on macOS (Apple Silicon) and simulate RISC-V binaries.

---

## Table of Contents

1. [Prerequisites](#-prerequisites)
2. [Host Setup (Python Virtual Environment)](#-host-setup-python-virtual-environment)
3. [Docker Setup](#-docker-setup)
4. [Building gem5 for RISC-V](#-building-gem5-for-risc-v)
5. [Compiling Your RISC-V Binary](#-compiling-your-risc-v-binary)
6. [Running the Simulation](#-running-the-simulation)
7. [Checking Results](#-checking-results)
8. [Quick Reference](#-quick-reference)
9. [Troubleshooting](#-troubleshooting)

---

## 🧩 Prerequisites

- **macOS** with Docker Desktop installed (Apple Silicon or Intel)
- **Python 3.10+** on host
- Terminal (zsh or bash)

---

## 🐍 Host Setup (Python Virtual Environment)

The virtual environment is optional but recommended for analysis scripts.

```bash
# Navigate to your gem5 directory
cd /path/to/gem5

# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# (Optional) Install dependencies
# pip install -r requirements.txt
```

> 💡 **Tip**: Run `source .venv/bin/activate` each time you open a new terminal.

---

## 🐳 Docker Setup

### Option A: Use the Provided Script (Recommended)

```bash
cd /path/to/gem5
./docker/run_docker.sh
```

This script automatically:
1. Builds the `gem5-universal:latest` Docker image
2. Starts a container with your repo mounted at `/workspace`

### Option B: Manual Docker Commands

**Step 1: Build the Docker image** (only once)

```bash
docker buildx build --platform linux/amd64 \
  -t gem5-universal:latest \
  -f docker/dockerfile.dev .
```

**Step 2: Run the container**

```bash
docker run --rm -it \
  --platform linux/amd64 \
  -v "$(pwd)":/workspace \
  gem5-universal:latest bash
```

You are now inside the container at `/workspace` (your gem5 repo).

---

## 🔨 Building gem5 for RISC-V

**Inside the Docker container:**

```bash
cd /workspace

# Build gem5 for RISC-V (takes 30-60 minutes on first build)
scons build/RISCV/gem5.opt -j8

# (Optional) Build for other architectures
# scons build/X86/gem5.opt -j8
# scons build/ARM/gem5.opt -j8
```

> ⚠️ **Note**: The first build takes a long time. Subsequent builds are faster.

---

## 📦 Compiling Your RISC-V Binary

You can compile **C programs** or **Assembly files** inside the Docker container.

### From C Code

```bash
# Replace <your_file.c> and <output_name> with your actual paths
riscv64-linux-gnu-gcc -O0 -static <your_file.c> -o <output_name>.riscv

# Example:
# riscv64-linux-gnu-gcc -O0 -static tests/spill_test/spill_test.c -o tests/spill_test/spill_test.riscv
```

**Flags explained:**
- `-O0`: Disable optimizations (useful for testing, shows more spills)
- `-static`: Static linking (required for SE mode simulation)

### From Assembly (.S file)

```bash
# Assemble
riscv64-linux-gnu-as -o <output>.o <your_file>.S

# Link
riscv64-linux-gnu-ld -o <output>.riscv <output>.o

# Example:
# riscv64-linux-gnu-as -o test.o my_test.S
# riscv64-linux-gnu-ld -o test.riscv test.o
```

---

## ▶️ Running the Simulation

**Inside the Docker container:**

```bash
./build/RISCV/gem5.opt configs/deprecated/example/se.py \
  --cmd=<path_to_your_binary>.riscv \
  --cpu-type=TimingSimpleCPU \
  --caches
```

**Example:**

```bash
./build/RISCV/gem5.opt configs/deprecated/example/se.py \
  --cmd=tests/spill_test/spill_test.riscv \
  --cpu-type=TimingSimpleCPU \
  --caches
```

**Options:**
- `--cpu-type=TimingSimpleCPU`: Required for spill detection
- `--caches`: Enable cache simulation
- `--cmd=<binary>`: Path to your RISC-V executable

---

## 📊 Checking Results

After simulation, results are saved in the `m5out/` directory:

| File | Description |
|------|-------------|
| `stats.txt` | Detailed simulation statistics |
| `riscv_spill_stats.txt` | Register spill detection log |
| `config.json` | Simulation configuration |

**Quick commands:**

```bash
# View spill log
cat m5out/riscv_spill_stats.txt

# Count detected spills
grep "^SPILL" m5out/riscv_spill_stats.txt | wc -l

# View key stats
grep -E "numLoadInsts|numStoreInsts|simInsts" m5out/stats.txt
```

**Spill log format:**
```
SPILL,store_pc,load_pc,address,store_tick,load_tick,tick_diff,store_inst_count,load_inst_count
```

---

## ⚡ Quick Reference

### Complete Workflow (Copy-Paste Ready)

```bash
# 1. Start Docker container
./docker/run_docker.sh

# 2. (Inside container) Build gem5 - only needed once
cd /workspace
scons build/RISCV/gem5.opt -j8

# 3. Compile your code
riscv64-linux-gnu-gcc -O0 -static your_code.c -o your_code.riscv

# 4. Run simulation
./build/RISCV/gem5.opt configs/deprecated/example/se.py \
  --cmd=your_code.riscv \
  --cpu-type=TimingSimpleCPU --caches

# 5. Check results
cat m5out/riscv_spill_stats.txt
```

### Useful Docker Commands

```bash
# Build image
docker buildx build --platform linux/amd64 -t gem5-universal:latest -f docker/dockerfile.dev .

# Run container
docker run --rm -it --platform linux/amd64 -v "$(pwd)":/workspace gem5-universal:latest bash

# Check available compilers
riscv64-linux-gnu-gcc --version
aarch64-linux-gnu-gcc --version
```

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `se.py: script has been deprecated` | Use `configs/deprecated/example/se.py` instead of `configs/example/se.py` |
| Docker image build fails | Ensure Docker Desktop is running and has enough disk space |
| `command not found: riscv64-linux-gnu-gcc` | You're on the host, not inside Docker. Run `./docker/run_docker.sh` first |
| Simulation hangs | Add `--caches` flag or check your binary for infinite loops |
| `m5out/riscv_spill_stats.txt` empty | Ensure you're using `--cpu-type=TimingSimpleCPU` |
| Protobuf version error on host | Use Docker instead of building gem5 directly on macOS |

---

## 📁 Project Structure

```
gem5/
├── docker/
│   ├── dockerfile.dev      # Docker build configuration
│   └── run_docker.sh       # One-click Docker launcher
├── build/
│   └── RISCV/gem5.opt      # Compiled gem5 binary
├── src/cpu/simple/
│   ├── spill_detector.hh   # Spill detection header
│   ├── spill_detector.cc   # Spill detection implementation
│   └── timing.cc           # CPU model with spill hooks
├── tests/spill_test/       # Example test files
│   ├── spill_test.c        # C test program
│   ├── spill_exact.S       # Assembly test (controlled spills)
│   └── README.md           # Test documentation
└── m5out/                  # Simulation output directory
    ├── stats.txt           # Statistics
    └── riscv_spill_stats.txt  # Spill log
```

---

## 📚 Additional Resources

- [gem5 Documentation](https://www.gem5.org/documentation/)
- [RISC-V ISA Manual](https://riscv.org/technical/specifications/)
- [gem5 Docker Images](https://www.gem5.org/documentation/general_docs/building#docker)

---

**Happy Simulating! 🚀**
