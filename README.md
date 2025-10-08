# gem5 Register Spill Detection on Apple Silicon 
## 📖 **Quick Summary**

This repository implements **register spill detection** in the gem5 simulator, optimized for development on **Apple Silicon (M3) Macs**. The workflow uses Docker for cross-compilation and native macOS for simulation execution.

**Key Points:**
- ✅ **Compile test programs**: In Docker (x86-64 Linux environment)
- ✅ **Run gem5 simulations**: On Mac M (via Rosetta 2 translation)
- ✅ **Analyze results**: Python dashboards and statistics on Mac
- ✅ **Why**: Ensures binary compatibility while maintaining fast iteration cycles

---

## 🎯 **Development Approach & Architecture Logic**

This repository demonstrates a **cross-platform development workflow** for gem5 simulation on Apple Silicon (M3) Macs. The approach separates binary compilation and simulation execution across different environments to achieve optimal compatibility and performance.

### 📊 **Architecture Overview**

```
┌─────────────────────────────────────────────────────────────────┐
│  DOCKER CONTAINER (x86-64 Linux Environment)                    │
│  Purpose: Cross-compile test programs                           │
│  ┌───────────────────────────────────────────────────┐         │
│  │  Input:  test.c (C source code)                   │         │
│  │  Tool:   x86_64-elf-gcc / x86_64-linux-musl-gcc   │         │
│  │  Output: test_program (ELF 64-bit x86-64 binary)  │         │
│  └───────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                            ↓ (binary artifact)
┌─────────────────────────────────────────────────────────────────┐
│  MACOS (Apple Silicon M chipset - ARM64 Architecture)                  │
│  Purpose: Run gem5 simulations                                  │
│  ┌───────────────────────────────────────────────────┐         │
│  │  gem5.opt (x86-64 ELF binary)                     │         │
│  │       ↓ (via Rosetta 2 translation)               │         │
│  │  Simulates x86-64 test_program instructions       │         │
│  │       ↓                                            │         │
│  │  Generates: stats.txt, spill_stats.txt, etc.      │         │
│  └───────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

### 🔧 **Why This Approach?**

| Challenge | Solution | Rationale |
|-----------|----------|-----------|
| **Binary Format Mismatch** | Apple M chipset produces ARM64 macOS binaries, but gem5 X86 needs x86-64 Linux ELF binaries | Use Docker with `--platform linux/amd64` for cross-compilation |
| **gem5 Execution** | gem5.opt is an x86-64 binary, but M chipset is ARM64 | macOS Rosetta 2 automatically translates x86-64 → ARM64 |
| **Performance** | Running everything in Docker (emulation) is slow | Compile in Docker, simulate on native Mac (Rosetta 2 is faster than full emulation) |
| **Reproducibility** | Different developers have different host systems | Docker ensures consistent compilation environment |

### ⚡ **Key Insights**

1. **gem5 is a simulator, not an executor**: gem5 doesn't execute binaries natively—it simulates them instruction-by-instruction. The host architecture (ARM64 vs x86-64) doesn't affect simulation accuracy.

2. **Rosetta 2 Translation**: macOS automatically translates x86-64 gem5 binary to ARM64 at runtime. This introduces minimal overhead for simulation workloads.

3. **Separation of Concerns**: 
   - **Docker**: Handles cross-compilation (one-time per test program)
   - **Mac**: Handles simulation execution (iterative testing and analysis)

4. **Scientific Validity**: The simulated architecture (x86-64) is determined by the gem5 build (`build/X86/gem5.opt`) and test binary format, NOT by the host machine architecture.

---

## 🚀 **Quick Start Guide**

### **Step 1: Compile Test Programs in Docker**

Start an x86-64 Linux container:
```sh
docker run --rm -it --platform linux/amd64 \
  -v $(pwd):/workspace -w /workspace ubuntu:24.04 bash
```

Inside Docker, install build tools and compile:
```sh
# Install dependencies
apt-get update && apt-get install -y build-essential gcc-multilib

# Compile your test program
gcc -static -o test_program test.c

# Verify binary format
file test_program
# Expected: ELF 64-bit LSB executable, x86-64, version 1 (GNU/Linux)

# Exit Docker
exit
```

### **Step 2: Run gem5 Simulation on Mac**

Back in your Mac terminal:
```sh
# Run simulation with compiled binary
./build/X86/gem5.opt configs/example/se.py -c test_program

# Output will be in m5out/ directory
ls m5out/
# stats.txt, config.ini, spill_stats.txt (if using register spill detection)
```

---

## 🐳 **Docker Container Management**

### Starting a Container
```sh
docker run --rm -it --platform linux/amd64 \
  -v $(pwd):/workspace -w /workspace ubuntu:24.04 bash
```

### Stopping the Container
```sh
exit  # or Ctrl + D
```

### Managing Containers
```sh
# List running containers
docker ps

# List all containers (including stopped)
docker ps -a

# Stop a running container
docker stop <container_id>

# Remove a container
docker rm <container_id>

# Clean up unused images
docker image prune
```

> **Note**: Using the `--rm` flag automatically removes the container when you exit.

---

## 🔨 **Automated Build Script**

For convenience, use the provided `run_x86_docker.sh` script that automates the Docker workflow:

```sh
./run_x86_docker.sh
```

This script will:
1. Start an x86-64 Ubuntu 24.04 container
2. Install all gem5 build dependencies
3. Build gem5 X86 (if not already built)
4. Drop you into an interactive shell for compiling test programs

### Example Workflow with Automated Script
```sh
# Start Docker environment
./run_x86_docker.sh

# Inside Docker container, compile your programs
gcc -static -o matrix_test fair_comparison/x86_build/matrix_spill.c

# Exit Docker
exit

# Run simulation on Mac
./build/X86/gem5.opt --outdir=m5out_matrix \
  configs/example/se.py -c matrix_test --cpu-type=TimingSimpleCPU
```

---

## 📋 **Development Workflow Summary**

| Task | Environment | Command Example |
|------|-------------|-----------------|
| **Compile test programs** | 🐳 Docker (x86-64) | `gcc -static -o test test.c` |
| **Build gem5** | 🐳 Docker or 💻 Mac | `scons build/X86/gem5.opt -j8` |
| **Run simulations** | 💻 Mac (via Rosetta 2) | `./build/X86/gem5.opt configs/...` |
| **Analyze results** | 💻 Mac | `python3 spill_web_dashboard.py` |

### Performance Considerations
- **Building in Docker**: Slower due to emulation, but ensures reproducibility
- **Building on Mac**: Faster (Rosetta 2 is efficient), but less reproducible
- **Simulating on Mac**: Recommended - faster iterative testing
- **Simulating in Docker**: Slower, but useful for exact reproducibility

---

## 🔍 **Technical Details**

### Binary Format Requirements

**Test Programs for gem5 X86 Simulation:**
```sh
# Correct format (created in Docker)
file test_program
# Output: ELF 64-bit LSB executable, x86-64, version 1 (GNU/Linux), statically linked

# Incorrect format (native Mac compilation)
file test_program_mac
# Output: Mach-O 64-bit executable arm64
# ❌ This will NOT work with gem5 X86!
```

### gem5 Binary Architecture
```sh
# Check gem5 binary format
file build/X86/gem5.opt
# Output: ELF 64-bit LSB pie executable, x86-64, version 1 (GNU/Linux), 
#         dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2

# This x86-64 binary runs on M chipset Mac via Rosetta 2
```

### Cross-Compilation Toolchains

Available in Docker container:
- **gcc**: Standard GNU compiler for x86-64 Linux
- **gcc-multilib**: Supports 32-bit and 64-bit compilation
- **x86_64-elf-gcc**: Bare-metal x86-64 compiler (for minimal binaries)
- **x86_64-linux-musl-gcc**: Statically linked Linux binaries (can be installed)

### Why Static Linking?
```sh
# Static linking embeds all libraries in the binary
gcc -static -o test test.c

# This is required because:
# 1. gem5 SE mode has limited syscall support
# 2. No dynamic linker available in simulated environment
# 3. Ensures all dependencies are self-contained
```

---

## 🐛 **Troubleshooting**

### Problem: "Exec format error" or "cannot execute binary file"
**Cause**: Binary compiled on Mac (ARM64) instead of in Docker (x86-64)

**Solution**: Always compile test programs inside Docker container
```sh
# Wrong ❌
gcc -o test test.c  # On Mac - creates ARM64 binary

# Correct ✅
docker run --rm -it --platform linux/amd64 \
  -v $(pwd):/workspace -w /workspace ubuntu:24.04 bash
gcc -static -o test test.c  # Inside Docker - creates x86-64 binary
```

### Problem: "gem5.opt: command not found"
**Cause**: gem5 not built yet

**Solution**: Build gem5 first
```sh
# In Docker or on Mac
scons build/X86/gem5.opt -j$(sysctl -n hw.ncpu)
```

### Problem: Docker container is slow
**Cause**: Full x86-64 emulation on ARM64 architecture

**Solutions**:
1. **Build gem5 once in Docker**, then copy to Mac
2. **Compile test programs in Docker** (necessary)
3. **Run simulations on Mac** (faster with Rosetta 2)

### Problem: "Fatal: Cannot find test binary"
**Cause**: Wrong path or binary not accessible from gem5

**Solution**: Use absolute paths or ensure binary is in workspace
```sh
# Relative path (from gem5 root)
./build/X86/gem5.opt configs/example/se.py -c ./fair_comparison/x86_build/test

# Absolute path
./build/X86/gem5.opt configs/example/se.py -c /workspace/test
```

### Problem: Simulation runs but no spill detection
**Cause**: Using AtomicSimpleCPU instead of TimingSimpleCPU

**Solution**: Specify CPU type
```sh
./build/X86/gem5.opt configs/example/se.py \
  -c test_program --cpu-type=TimingSimpleCPU
```

---

## 📚 **Additional Resources**

### Project-Specific Documentation
- **[REGISTER_SPILL_README.md](REGISTER_SPILL_README.md)** - Register spill detection system
- **[SETUP_SUMMARY.md](SETUP_SUMMARY.md)** - Initial setup and configuration guide
- **[fair_comparison/README.md](fair_comparison/README.md)** - Architecture comparison tests

### gem5 Official Documentation
- **Main Website**: <http://www.gem5.org>
- **Documentation**: <http://www.gem5.org/documentation>
- **Learning gem5**: <http://www.gem5.org/documentation/learning_gem5/introduction>
- **Building gem5**: <http://www.gem5.org/documentation/general_docs/building>

---

# The gem5 Simulator
This is the repository for the gem5 simulator. It contains the full source code
for the simulator and all tests and regressions.

The gem5 simulator is a modular platform for computer-system architecture
research, encompassing system-level architecture as well as processor
microarchitecture. It is primarily used to evaluate new hardware designs,
system software changes, and compile-time and run-time system optimizations.

The main website can be found at <http://www.gem5.org>.

## Testing status

**Note**: These regard tests run on the develop branch of gem5:
<https://github.com/gem5/gem5/tree/develop>.

[![Daily Tests](https://github.com/gem5/gem5/actions/workflows/daily-tests.yaml/badge.svg?branch=develop)](https://github.com/gem5/gem5/actions/workflows/daily-tests.yaml)
[![Weekly Tests](https://github.com/gem5/gem5/actions/workflows/weekly-tests.yaml/badge.svg?branch=develop)](https://github.com/gem5/gem5/actions/workflows/weekly-tests.yaml)
[![Compiler Tests](https://github.com/gem5/gem5/actions/workflows/compiler-tests.yaml/badge.svg?branch=develop)](https://github.com/gem5/gem5/actions/workflows/compiler-tests.yaml)

## Getting started

A good starting point is <http://www.gem5.org/about>, and for
more information about building the simulator and getting started
please see <http://www.gem5.org/documentation> and
<http://www.gem5.org/documentation/learning_gem5/introduction>.

## Building gem5

To build gem5, you will need the following software: g++ or clang,
Python (gem5 links in the Python interpreter), SCons, zlib, m4, and lastly
protobuf if you want trace capture and playback support. Please see
<http://www.gem5.org/documentation/general_docs/building> for more details
concerning the minimum versions of these tools.

Once you have all dependencies resolved, execute
`scons build/ALL/gem5.opt` to build an optimized version of the gem5 binary
(`gem5.opt`) containing all gem5 ISAs. If you only wish to compile gem5 to
include a single ISA, you can replace `ALL` with the name of the ISA. Valid
options include `ARM`, `NULL`, `MIPS`, `POWER`, `RISCV`, `SPARC`, and `X86`
The complete list of options can be found in the build_opts directory.

See https://www.gem5.org/documentation/general_docs/building for more
information on building gem5.

## The Source Tree

The main source tree includes these subdirectories:

* build_opts: pre-made default configurations for gem5
* build_tools: tools used internally by gem5's build process.
* configs: example simulation configuration scripts
* ext: less-common external packages needed to build gem5
* include: include files for use in other programs
* site_scons: modular components of the build system
* src: source code of the gem5 simulator. The C++ source, Python wrappers, and Python standard library are found in this directory.
* system: source for some optional system software for simulated systems
* tests: regression tests
* util: useful utility programs and files

## gem5 Resources

To run full-system simulations, you may need compiled system firmware, kernel
binaries and one or more disk images, depending on gem5's configuration and
what type of workload you're trying to run. Many of these resources can be
obtained from <https://resources.gem5.org>.

More information on gem5 Resources can be found at
<https://www.gem5.org/documentation/general_docs/gem5_resources/>.

## Getting Help, Reporting bugs, and Requesting Features

We provide a variety of channels for users and developers to get help, report
bugs, requests features, or engage in community discussions. Below
are a few of the most common we recommend using.

* **GitHub Discussions**: A GitHub Discussions page. This can be used to start
discussions or ask questions. Available at
<https://github.com/orgs/gem5/discussions>.
* **GitHub Issues**: A GitHub Issues page for reporting bugs or requesting
features. Available at <https://github.com/gem5/gem5/issues>.
* **Jira Issue Tracker**: A Jira Issue Tracker for reporting bugs or requesting
features. Available at <https://gem5.atlassian.net/>.
* **Slack**: A Slack server with a variety of channels for the gem5 community
to engage in a variety of discussions. Please visit
<https://www.gem5.org/join-slack> to join.
* **gem5-users@gem5.org**: A mailing list for users of gem5 to ask questions
or start discussions. To join the mailing list please visit
<https://www.gem5.org/mailing_lists>.
* **gem5-dev@gem5.org**: A mailing list for developers of gem5 to ask questions
or start discussions. To join the mailing list please visit
<https://www.gem5.org/mailing_lists>.

## Contributing to gem5

We hope you enjoy using gem5. When appropriate we advise sharing your
contributions to the project. <https://www.gem5.org/contributing> can help you
get started. Additional information can be found in the CONTRIBUTING.md file.


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
  -c fair_comparison/hello_build/hello_folks_x86
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
gcc -o fair_comparison/hello_folks_x86 fair_comparison/hello_folks.c
```

### 5. Run the Simulation
Run the gem5 simulation with the compiled binary:
```bash
build/X86/gem5.opt configs/deprecated/example/se.py \
  --cpu-type=TimingSimpleCPU \
  --caches \
  -c fair_comparison/x86_build/matrix_spill_x86
```

### 6. Check the Output Files
After the simulation completes, check the output files:
```bash
ls -la m5out/spill_stats.txt
cat m5out/spill_stats.txt | head -20
```

This step-by-step guide ensures that you can successfully run an x86 simulation on Docker.

---

## Testing Register Spill Detection with a Simple "Hello World" Program

This section demonstrates how to compile and simulate a simple C program with gem5's register spill detection feature using ROI (Region of Interest) markers.

### Example Program: `hello_folks.c`

Located in `fair_comparison/hello_build/hello_folks.c`:

```c
#include <stdio.h>
#include <gem5/m5ops.h>

int main() {
    // ROI START: Region of Interest for spill detection
    m5_work_begin(0, 0);
    printf("hello f0lks!\n");
    m5_work_end(0, 0);
    // ROI END: Region of Interest for spill detection
    return 0;
}
```

### Prerequisites

1. **Docker installed** on your system
2. **gem5 source code** cloned to your machine
3. **Terminal access** to the gem5 project root directory

### Step 1: Navigate to the Project Root

```bash
cd /path/to/gem5
```

### Step 2: Build and Run Using the Automated Script

The easiest way is to use the provided `hello_build.sh` script:

```bash
cd fair_comparison/hello_build
chmod +x hello_build.sh
./hello_build.sh
```

This script will:
- Clean previous build artifacts
- Start a Docker container (Ubuntu 24.04, x86_64 architecture)
- Install all required dependencies
- Build the m5 utility library
- Compile `hello_folks.c` with ROI markers
- Build gem5 simulator
- Run the simulation with spill detection enabled
- Display spill statistics

### Step 3: Manual Build Process (Alternative)

If you prefer to run commands manually:

#### 3.1. Start a Docker Container

```bash
docker run --rm -it --platform linux/amd64 \
  -v "$(pwd)":/workspace -w /workspace \
  ubuntu:24.04 bash
```

#### 3.2. Install Dependencies (Inside Container)

```bash
apt-get update && apt-get install -y \
  build-essential gcc-multilib file python3 python3-pip scons \
  m4 zlib1g-dev libprotobuf-dev protobuf-compiler \
  libgoogle-perftools-dev libboost-all-dev pkg-config \
  gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf openjdk-11-jdk
```

#### 3.3. Build the m5 Utility Library

```bash
cd util/m5
rm -rf build
scons build/x86/out/libm5.a -j8
cd ../..
```

#### 3.4. Compile the Test Program

```bash
gcc -I include -L util/m5/build/x86/out \
  -o fair_comparison/hello_build/hello_folks_x86 \
  fair_comparison/hello_build/hello_folks.c \
  -lm5 -static
```

Explanation:
- `-I include`: Include gem5's header files (for `m5ops.h`)
- `-L util/m5/build/x86/out`: Link directory for `libm5.a`
- `-lm5`: Link with the m5 library
- `-static`: Create a statically linked binary

#### 3.5. Build gem5 (if not already built)

```bash
scons build/X86/gem5.opt -j8
```

#### 3.6. Create Output Directory

```bash
mkdir -p m5out/fs
```

#### 3.7. Run the Simulation

```bash
build/X86/gem5.opt configs/deprecated/example/se.py \
  --cpu-type=TimingSimpleCPU \
  --caches \
  -c fair_comparison/hello_build/hello_folks_x86
```

### Step 4: Check the Results

#### View Spill Detection Results

```bash
# Check if spill stats file exists
ls -lh m5out/x86_spill_stats.txt

# Count total spills detected
grep -c "^SPILL" m5out/x86_spill_stats.txt

# View first 20 lines
head -20 m5out/x86_spill_stats.txt
```

#### View gem5 Statistics

```bash
# View general simulation statistics
head -50 m5out/stats.txt
```

### Expected Output

The simulation should produce:
- **Console output**: "hello f0lks!"
- **Spill statistics**: `m5out/x86_spill_stats.txt` (CSV format)
  - **With ROI markers**: ~164 spill events (only analyzing printf region)
  - **Without ROI markers**: ~9,500+ spill events (entire program including startup/cleanup)
- **gem5 statistics**: `m5out/stats.txt` (general simulation statistics including instruction counts, cycles, etc.)
- **Configuration**: `m5out/config.ini` and `m5out/config.json` (simulation configuration details)

### Understanding the Spill Stats Format

The `x86_spill_stats.txt` file contains CSV entries like:

```
SPILL,store_pc,load_pc,memory_address,store_tick,load_tick,tick_diff,store_inst_count,load_inst_count
SPILL,47b2f0,47c8cb,7fffffffed48,246771000,246778000,7000,205812,205817
```

Where:
- `store_pc`: Program counter of the store instruction (hex)
- `load_pc`: Program counter of the load instruction (hex)
- `memory_address`: Memory address where spill occurred (hex)
- `store_tick`: Simulation tick when store happened
- `load_tick`: Simulation tick when load happened
- `tick_diff`: Time difference between store and load
- `store_inst_count`: Total instructions executed at store time
- `load_inst_count`: Total instructions executed at load time

### ROI (Region of Interest) Markers Explained

The `m5_work_begin()` and `m5_work_end()` functions define a **Region of Interest** for spill detection:

```c
m5_work_begin(0, 0);  // Start spill detection
// Your code here
m5_work_end(0, 0);    // Stop spill detection
```

**How ROI Works:**
- Spill detector only tracks memory operations between `m5_work_begin` and `m5_work_end`
- Code outside the ROI (startup, cleanup, library initialization) is ignored
- This dramatically reduces noise in spill detection results

**Impact on Results:**
- **Without ROI**: Entire program analyzed → 9,527 spills detected (includes startup, libc init, etc.)
- **With ROI**: Only `printf` analyzed → 164 spills detected (98.3% reduction)

**Use Cases:**
- Benchmarking specific functions
- Identifying hotspots in large applications
- Comparing different algorithm implementations
- Isolating application code from library/system code

### Troubleshooting

**Problem**: `gem5/m5ops.h: No such file or directory`  
**Solution**: Ensure you use `-I include` flag when compiling

**Problem**: `undefined reference to m5_work_begin`  
**Solution**: Make sure you link with `-lm5` and the library path is correct

**Problem**: `x86_spill_stats.txt` not found  
**Solution**: Check that gem5 was built with the spill detector enabled. The file should be in `m5out/x86_spill_stats.txt`

**Problem**: No spills detected in simple programs  
**Solution**: Simple programs like "hello world" may not trigger register spilling. Try more complex programs with heavy computation or many local variables.

### Next Steps

- Try more complex programs (e.g., `matrix_spill.c`)
- Analyze spill patterns using visualization tools
- Compare spill behavior across different optimization levels (`-O0`, `-O1`, `-O2`, `-O3`)
- Experiment with different compiler flags

---

## Understanding Static Linking and libm5.a

This section explains two important concepts used in gem5 simulation: static linking and the m5 utility library.

### What is Static Linking? (`-static` flag)

When compiling programs for gem5 simulation, we use the `-static` flag. This is **NOT** related to static program analysis—it's a linking strategy.

#### Dynamic vs Static Linking

| **Dynamic Linking** (Default) | **Static Linking** (`-static`) |
|-------------------------------|-------------------------------|
| Library code NOT included in binary | Library code IS included in binary |
| Requires `.so` files at runtime | All code embedded in executable |
| Smaller binary size (~16 KB) | Larger binary size (~767 KB) |
| Depends on system libraries | Self-contained, independent |

#### Example Comparison

```bash
# Dynamic linking (default)
gcc -o hello_dynamic hello.c -lm5
ls -lh hello_dynamic
# Output: 16KB

# Static linking
gcc -o hello_static hello.c -lm5 -static
ls -lh hello_static
# Output: 767KB  ← Much larger!
```

#### Why Use `-static` for gem5?

Static linking is **essential** for gem5 simulation because:

1. **Independence**: gem5 cannot resolve dynamic library dependencies during simulation
2. **Portability**: The binary can run on any compatible architecture without external dependencies
3. **Simplicity**: Avoids dynamic linker issues in the simulated environment

**Without `-static`**, you'll encounter errors like:
```
Error: /lib/x86_64-linux-gnu/libc.so.6: cannot be loaded in simulated environment
```

#### What Gets Statically Linked?

When you compile with `-static`, the following are embedded in your binary:

```bash
gcc -I include -L util/m5/build/x86/out \
  -o hello_folks_x86 hello_folks.c \
  -lm5 -static
```

This includes:
- **libm5.a**: gem5 magic instructions (ROI markers, checkpoints, etc.)
- **libc.a**: Standard C library (printf, malloc, etc.)
- **Other dependencies**: Any libraries your program uses

The resulting binary is self-contained and can be directly simulated by gem5.

### What is libm5.a?

**`libm5.a`** is the gem5 Magic Instructions Library—a static library that provides special functions for controlling gem5 simulation.

#### File Extension Explained

- `.a` = **Archive** format = Static library (Unix/Linux)
- `.so` = **Shared Object** = Dynamic library (not used in gem5)

#### What's Inside libm5.a?

The library contains implementations of gem5's special "magic" instructions:

```c
// Region of Interest (ROI) markers
void m5_work_begin(uint64_t workid, uint64_t threadid);
void m5_work_end(uint64_t workid, uint64_t threadid);

// Checkpoint and statistics control
void m5_checkpoint(uint64_t ns_delay, uint64_t ns_period);
void m5_reset_stats(uint64_t ns_delay, uint64_t ns_period);
void m5_dump_stats(uint64_t ns_delay, uint64_t ns_period);

// Simulation control
void m5_exit(uint64_t ns_delay);
void m5_fail(uint64_t ns_delay, uint64_t code);

// And many more...
```

#### Building libm5.a

The library is built from source code in the `util/m5` directory:

```bash
# Source files
util/m5/src/abi/x86/m5op.S      # Assembly implementations of magic instructions
util/m5/src/m5_mmap.c           # Memory-mapped operation helpers

# Build command
cd util/m5
scons build/x86/out/libm5.a -j8

# Output
util/m5/build/x86/out/libm5.a   # ← Static library file
```

#### Inspecting libm5.a Contents

You can view the object files inside the library:

```bash
ar -t util/m5/build/x86/out/libm5.a
```

Output:
```
m5op.o          # Magic instruction implementations
m5_mmap.o       # Memory-mapped operations
m5op_addr.o     # Address calculations
```

#### How to Use libm5.a

**Step 1**: Include the header in your C code:
```c
#include <gem5/m5ops.h>  // Provides function declarations
```

**Step 2**: Link with the library during compilation:
```bash
gcc -I include \                      # Header file location
    -L util/m5/build/x86/out \        # Library directory
    -o program program.c \
    -lm5 \                            # Link with libm5.a
    -static                           # Static linking
```

The `-lm5` flag tells the linker to search for `libm5.a` and embed its code into your binary.

### Complete Compilation Flow

```
┌─────────────────────────────────────────┐
│  Source Code: hello_folks.c             │
│  ├── #include <gem5/m5ops.h>           │  ← Header declaration
│  └── m5_work_begin(0, 0);              │  ← Function call
└─────────────────────────────────────────┘
              ↓ Compile & Link
┌─────────────────────────────────────────┐
│  gcc -lm5 -static                       │
│  ├── Links libm5.a                     │  ← m5 magic instructions
│  └── Links libc.a                      │  ← C standard library
└─────────────────────────────────────────┘
              ↓ Result
┌─────────────────────────────────────────┐
│  Binary: hello_folks_x86 (767KB)       │
│  ├── Your program code                 │
│  ├── libm5.a code        ← Embedded!   │
│  ├── libc.a code         ← Embedded!   │
│  └── Self-contained, no external deps  │
└─────────────────────────────────────────┘
              ↓ Execute in gem5
┌─────────────────────────────────────────┐
│  gem5 Simulation                        │
│  ├── m5_work_begin() → Start tracking │
│  ├── Execute user code                 │
│  └── m5_work_end() → Stop tracking    │
└─────────────────────────────────────────┘
```

### Why Not Use Dynamic Libraries (.so)?

In gem5 simulation:
- ✅ **Static libraries (`.a`)**: All code embedded in binary → gem5 can simulate
- ❌ **Dynamic libraries (`.so`)**: Requires dynamic linker → Not available in gem5's simulated environment

### Static Linking vs Static Analysis

**Important**: Do not confuse these concepts!

| Concept | What It Means | Related To |
|---------|--------------|------------|
| **Static Linking** (`-static`) | Embed library code in binary at compile time | Compilation process |
| **Static Analysis** | Analyze program without running it | Program analysis |
| **Dynamic Analysis** | Analyze program by running it (what gem5 does) | Program analysis |

**gem5 performs 100% dynamic analysis** (runtime analysis), even though we use static linking for compilation.

### Verifying Static Linking

You can verify that your binary is statically linked:

```bash
# Check binary type
file hello_folks_x86
# Output: ELF 64-bit LSB executable, x86-64, statically linked

# Check for dynamic dependencies (should be none)
ldd hello_folks_x86
# Output: not a dynamic executable
```

For a dynamically linked binary, `ldd` would show:
```
linux-vdso.so.1 (0x00007ffd...)
libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f...)
```

### Summary

- **`-static`**: Compilation flag that embeds all library code into your binary
- **`libm5.a`**: Static library containing gem5 magic instructions (ROI markers, etc.)
- **Purpose**: Create self-contained binaries that can be simulated by gem5 without external dependencies
- **Trade-off**: Larger binary size (767KB vs 16KB) but essential for gem5 simulation
- **Not related to**: Static program analysis (which analyzes code without running it)
