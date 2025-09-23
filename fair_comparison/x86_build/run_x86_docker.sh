#!/bin/bash
docker run --rm -it --platform linux/amd64 \
  -v "$(pwd)":/workspace -w /workspace ubuntu:24.04 bash -c "
    apt-get update && \
    apt-get install -y build-essential gcc-multilib file python3 python3-pip scons m4 zlib1g-dev libprotobuf-dev protobuf-compiler libgoogle-perftools-dev libboost-all-dev pkg-config && \
    scons build/X86/gem5.opt -j\$(nproc) && \
    gcc -o fair_comparison/x86_build/matrix_spill_x86 fair_comparison/x86_build/matrix_spill.c && \
    build/X86/gem5.opt configs/deprecated/example/se.py -c fair_comparison/x86_build/matrix_spill_x86 && \
    bash
"