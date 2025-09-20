# Using Docker x86 Containers for Cross-Platform Builds

## Starting a Container
To start an x86 Ubuntu container for building or running x86 binaries:
```sh
docker run --rm -it --platform linux/amd64 -v $(pwd):/workspace -w /workspace ubuntu:24.04 bash
```

## Stopping the Container
Inside the container terminal, type:
```sh
exit
# or
Ctrl + D
```

## Listing Running Containers
```sh
docker ps
```

## Listing All Containers (Running and Stopped)
```sh
docker ps -a
```

## Stopping a Background Container
```sh
docker stop <container_id>
```

## Removing Unused Containers
```sh
docker rm <container_id>
```

## Removing Unused Images
```sh
docker image prune
```

> Note: If you use the first command above to start your container, it will be automatically removed when you exit (because of the `--rm` flag).

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
gcc -o fair_comparison/x86_build/matrix_spill_x86 fair_comparison/x86_build/matrix_spill.c
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
