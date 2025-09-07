# Hello World gem5 Simulation

## Files:

### 🎯 **Essential Files:**
- **`hello_world.c`** - Your C source code
- **`hello_world_x86_static`** - Compiled X86-64 binary for gem5
- **`sim.py`** - Main gem5 simulation script
- **`view_operations.py`** - Script to view operation statistics

## Usage:

### 1. Compile C programs:
```bash
x86_64-linux-musl-gcc -static -o program_name source.c
```

### 2. Run simulation:
```bash
build/X86/gem5.fast hello_world/sim.py
```

### 3. View operation counts:
```bash
python3 hello_world/view_operations.py
```

## Quick Stats:
- **Instructions**: 1,496
- **Operations**: 3,280 (including micro-ops)
- **L1D Reads**: 308
- **L1D Writes**: 237
- **L1I Reads**: 1,839
