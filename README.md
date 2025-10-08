# gem5 Register Spill Detection on Apple Silicon 

## 📖 Quick Summary

This repository implements **register spill detection** in the gem5 simulator, optimized for development on **Apple Silico## Example Build Command
The updated build command for running the `hello_folks_x86` program is as follows:

```bash
build/X86/gem5.opt configs/deprecated/example/se.py \
  --cpu-type=TimingSimpleCPU \
  --caches \
  -c benchmarks/builds/hello_build/hello_folks_x86
```

**Key Points:**
- ✅ Compile test programs in Docker (x86-64 Linux environment)
- ✅ Run gem5 simulations on macOS (via Rosetta 2)
- ✅ Analyze results with Python dashboards
- ✅ Ensures binary compatibility with fast iteration cycles

**Architecture:** Docker (compile) → macOS (simulate) → Analysis

---

## � Docker Setup - Current Workflow

### Starting Docker Container
```sh
docker run --rm -it --platform linux/amd64 \
  -v $(pwd):/workspace -w /workspace ubuntu:24.04 bash
```

### Inside Docker: Install Dependencies
```sh
apt-get update && apt-get install -y \
  build-essential gcc-multilib file python3 python3-pip scons \
  m4 zlib1g-dev libprotobuf-dev protobuf-compiler \
  libgoogle-perftools-dev libboost-all-dev pkg-config
```

### Build gem5 (Inside Docker)
```sh
scons build/X86/gem5.opt -j$(nproc)
```

### Build m5 Library (Inside Docker)
```sh
cd util/m5
scons build/x86/out/libm5.a -j$(nproc)
cd ../..
```

### Compile Test Program (Inside Docker)
```sh
gcc -static -I include -L util/m5/build/x86/out \
  -o benchmarks/builds/hello_build/hello_folks_x86 \
  benchmarks/builds/hello_build/hello_folks.c -lm5
```

### Exit Docker
```sh
exit
```

---

## 🚀 Running Simulations (On macOS)

### Basic Simulation
```sh
./build/X86/gem5.opt configs/example/se.py \
  --cpu-type=TimingSimpleCPU \
  --caches \
  -c benchmarks/builds/hello_build/hello_folks_x86
```

### View Results
```sh
# Check spill statistics
cat m5out/x86_spill_stats.txt

# Check general stats
cat m5out/stats.txt
```

---

## � Project Structure

```
gem5/
├── benchmarks/               # Test programs and analysis
│   ├── builds/              # Compiled binaries
│   │   ├── hello_build/     # Simple test program
│   │   ├── x86_build/       # X86 binaries
│   │   └── riscv_build/     # RISC-V binaries
│   └── analytics/           # Analysis scripts and results
├── build/X86/               # gem5 X86 build
│   └── gem5.opt            # gem5 simulator binary
├── m5out/                   # Simulation output
│   ├── stats.txt           # General statistics
│   └── x86_spill_stats.txt # Spill detection results
└── util/m5/                 # m5 utility library

```

---

## 📚 Documentation

- **[REGISTER_SPILL_README.md](REGISTER_SPILL_README.md)** - Register spill detection details
- **[benchmarks/README.md](benchmarks/README.md)** - Benchmark programs and usage
- **[DOCKER_REQUIREMENTS.md](DOCKER_REQUIREMENTS.md)** - Docker setup requirements
- **Official gem5**: <http://www.gem5.org/documentation>

---

# The gem5 Simulator

This is the repository for the gem5 simulator. It contains the full source code
for the simulator and all tests and regressions.

The gem5 simulator is a modular platform for computer-system architecture
research, encompassing system-level architecture as well as processor
microarchitecture.

**Main Website**: <http://www.gem5.org>
**Documentation**: <http://www.gem5.org/documentation>
**Getting Started**: <http://www.gem5.org/documentation/learning_gem5/introduction>

## Building gem5

To build gem5, you will need: g++ or clang, Python, SCons, zlib, m4, and protobuf.
See <http://www.gem5.org/documentation/general_docs/building> for details.

```sh
scons build/X86/gem5.opt -j$(nproc)
```

## Testing Status

[![Daily Tests](https://github.com/gem5/gem5/actions/workflows/daily-tests.yaml/badge.svg?branch=develop)](https://github.com/gem5/gem5/actions/workflows/daily-tests.yaml)
[![Weekly Tests](https://github.com/gem5/gem5/actions/workflows/weekly-tests.yaml/badge.svg?branch=develop)](https://github.com/gem5/gem5/actions/workflows/weekly-tests.yaml)

## Getting Help

- **GitHub Discussions**: <https://github.com/orgs/gem5/discussions>
- **GitHub Issues**: <https://github.com/gem5/gem5/issues>
- **Slack**: <https://www.gem5.org/join-slack>
- **Mailing Lists**: <https://www.gem5.org/mailing_lists>

## Contributing

See <https://www.gem5.org/contributing> and [CONTRIBUTING.md](CONTRIBUTING.md) for details.


# Simulating x86 Binaries on ARM Macs Using Docker

To automate the process of building and simulating x86 binaries (such as matrix_spill.c) on an ARM-based Mac, follow these steps:

## Step-by-Step Bash Workflow

1. Save the following script as `run_x86_docker.sh` in your project root directory.
2. Make it executable:
	```sh
	chmod +x run_x86_docker.sh
	```
3. Run the script:
	```sh
	./run_x86_docker.sh
	```

### Script Content
```sh
#!/bin/bash
docker run --rm -it --platform linux/amd64 \
  -v "$(pwd)":/workspace -w /workspace ubuntu:24.04 bash -c "\
	 apt-get update && \
	 apt-get install -y build-essential gcc-multilib file python3 python3-pip scons m4 zlib1g-dev libprotobuf-dev protobuf-compiler libgoogle-perftools-dev libboost-all-dev pkg-config && \
	 scons build/X86/gem5.opt -j\$(nproc)
	 bash\
"
```

This script will:
- Start an x86 Ubuntu container
- Install all required dependencies
- Build gem5 and your x86 binary
- Run the simulation
- Drop you into a bash shell for further inspection (so you can check stats.txt, spill_stats.txt, etc.)

You can modify the script for other C files or simulation options as needed.

## Updated Build Command

```bash
build/X86/gem5.opt configs/deprecated/example/se.py \
  --cpu-type=TimingSimpleCPU \
  --caches \
  -c <path_to_your_x86_binary>
```

## Example Build Command
The updated build command for running the `hello_folks_x86` program is as follows:

```bash
build/X86/gem5.opt configs/deprecated/example/se.py \
  --cpu-type=TimingSimpleCPU \
  --caches \
  -c benchmarks/builds/hello_build/hello_folks_x86
```

Make sure to use this command to ensure proper simulation with the spill detector enabled.

## Step-by-Step Guide to Run an x86 Simulation on Docker

### 1. Open Docker
Start an x86 Ubuntu container for building or running x86 binaries:
```bash
docker run --rm -it --platform linux/amd64 -v $(pwd):/workspace -w /workspace ubuntu:24.04 bash
```

### 2. Install Dependencies
Inside the container, install the required dependencies:
```bash
apt-get update && \
apt-get install -y build-essential gcc-multilib file python3 python3-pip scons m4 zlib1g-dev libprotobuf-dev protobuf-compiler libgoogle-perftools-dev libboost-all-dev pkg-config
```

### 3. Build gem5
Build the gem5 simulator for the x86 architecture:
```bash
scons build/X86/gem5.opt -j$(nproc)
```

### 4. Create the Binary File
Compile the C file to create the binary for simulation:
```bash
gcc -o <binary file> <.c file> 
```

For example:
```bash
gcc -o benchmarks/builds/hello_build/hello_folks_x86 benchmarks/builds/hello_build/hello_folks.c
```

### 5. Run the Simulation
Run the gem5 simulation with the compiled binary:
```bash
build/X86/gem5.opt configs/deprecated/example/se.py \
  --cpu-type=TimingSimpleCPU \
  --caches \
  -c benchmarks/builds/x86_build/matrix_spill_x86
```

### 6. Check the Output Files
After the simulation completes, check the output files:
```bash
ls -la m5out/spill_stats.txt
cat m5out/spill_stats.txt | head -20
```

This step-by-step guide ensures that you can successfully run an x86 simulation on Docker.