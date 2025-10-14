# Docker Requirements for gem5 Development

This document lists all the required packages and tools for building and running gem5 simulations in Docker.

## Base Image
- **Ubuntu 22.04 LTS** (linux/amd64 platform)

## Build Tools
- `build-essential` - Essential compilation tools (gcc, g++, make)
- `python3` - Python 3 interpreter for gem5 build system
- `python3-pip` - Python package installer
- `scons` - Software construction tool (gem5 build system)
- `git` - Version control system

## Libraries & Dependencies
- `zlib1g-dev` - Compression library (development files)
- `libprotobuf-dev` - Protocol Buffers library (development files)
- `protobuf-compiler` - Protocol Buffers compiler
- `libgoogle-perftools-dev` - Google Performance Tools
- `libboost-all-dev` - Boost C++ libraries
- `pkg-config` - Helper tool for compiling
- `wget` - File downloader
- `ca-certificates` - Common CA certificates

## Cross-Compilers (Multi-Architecture Support)
- `gcc-riscv64-linux-gnu` - RISC-V 64-bit C compiler
- `g++-riscv64-linux-gnu` - RISC-V 64-bit C++ compiler
- `gcc-aarch64-linux-gnu` - ARM 64-bit C compiler
- `g++-aarch64-linux-gnu` - ARM 64-bit C++ compiler

## Supported Architectures
With the installed cross-compilers, gem5 can be built for:
- **X86_64** (native)
- **RISC-V** (via riscv64-linux-gnu-gcc)
- **ARM/AArch64** (via aarch64-linux-gnu-gcc)

## Building the Docker Image

```bash
docker build -f Dockerfile_x86.dev -t gem5-dev:amd64 .
```

## Running the Docker Container

```bash
# From gem5 root directory
docker run -it --rm -v $(pwd):/gem5 -w /gem5 gem5-dev:amd64
```

## Building gem5 Inside Docker

### X86
```bash
scons build/X86/gem5.opt -j$(nproc)
```

### RISC-V
```bash
scons build/RISCV/gem5.opt -j$(nproc)
```

### ARM
```bash
scons build/ARM/gem5.opt -j$(nproc)
```

## Building m5 Utility Libraries

### X86
```bash
cd /gem5/util/m5
scons build/x86/out/libm5.a
```

### RISC-V
```bash
cd /gem5/util/m5
scons build/riscv/out/libm5.a
```

### ARM
```bash
cd /gem5/util/m5
scons build/arm64/out/libm5.a
```

## Compiling Test Programs

### X86
```bash
gcc -static -O2 -I/gem5/include -o program_x86 program.c /gem5/util/m5/build/x86/out/libm5.a -lm
```

### RISC-V
```bash
riscv64-linux-gnu-gcc -static -O2 -I/gem5/include -o program_riscv program.c /gem5/util/m5/build/riscv/out/libm5.a -lm
```

### ARM
```bash
aarch64-linux-gnu-gcc -static -O2 -I/gem5/include -o program_arm program.c /gem5/util/m5/build/arm64/out/libm5.a -lm
```

## Notes

- The Docker image uses `--platform=linux/amd64` to ensure x86_64 compatibility
- On Apple Silicon (M1/M2/M3), Docker will automatically use Rosetta 2 emulation
- All cross-compilers are pre-installed for multi-architecture development
- The container runs as root by default for easier package management

## Troubleshooting

### Missing Cross-Compiler
If you encounter "command not found" for a cross-compiler, verify it's installed:
```bash
apt-get update
apt-get install -y gcc-riscv64-linux-gnu g++-riscv64-linux-gnu
```

### Permission Issues
If you have permission issues with mounted volumes, ensure the host directory is accessible:
```bash
chmod -R 755 /path/to/gem5
```

### Out of Disk Space
Clean up unused Docker resources:
```bash
docker system prune -a
```

---

**Last Updated**: October 8, 2025  
**Docker Image**: gem5-dev:amd64  
**Base OS**: Ubuntu 22.04 LTS
