# CoreMark Integration for RV32IM FPGA

## Overview

CoreMark is integrated as a git submodule in `programs/coremark/src/` (official
EEMBC repository). The platform port consists of startup code, linker script,
and configuration files that enable bare-metal execution on the RV32IM
microarchitecture without an operating system.

## Directory structure

```
programs/coremark/
├── src/                    # EEMBC CoreMark source (submodule)
├── start.S                 # C runtime startup (stack, BSS clear, tohost)
├── link.ld                 # Harvard memory map linker script
├── core_portme.h           # Platform configuration
├── core_portme.c           # Platform implementation (stubs)
└── Makefile                # Build system
```

## Memory map

CoreMark uses a Harvard architecture: instructions in IMEM, data in DMEM.
The linker sees a single flat address space but sections are placed at
non-overlapping addresses across the two physical memories.

| Section  | Address | Size (FPGA) | Notes                              |
|----------|---------|-------------|------------------------------------|
| .text    | 0x0000  | ~10 KB      | Instructions + read-only data      |
| .rodata  | 0x2350  | ~1.4 KB     | String constants, read-only data   |
| gap      | 0x28F5  |             | Zero-filled (not accessed as code) |
| .tohost  | 0x5000  | 8 bytes     | Test completion signal             |
| gap      | 0x5008  |             | Zero-filled                        |
| .data    | 0x6000  | 12 bytes    | Initialized global data            |
| .bss     | 0x600C  | 20 bytes    | Zero-initialized data              |
| .stack   | 0x7000  | 4 KB        | Stack grows down toward 0x7000     |

**Critical**: `.text` ends at ~0x28F5 (10 KB). `.tohost` at 0x5000 must be
placed AFTER `.text` ends to avoid overlap. The original riscv-tests value of
0x708 is too low for CoreMark's ~9 KB `.text` section.

## Compilation

### FPGA performance run (default)

```bash
make -C programs/coremark
# Uses: ITERATIONS=2000, TOTAL_DATA_SIZE=2000, PERFORMANCE_RUN
# Output: build/coremark/coremark.elf
```

### Simulation validation build

```bash
make -C programs/coremark ITERATIONS=3 TOTAL_DATA_SIZE=120
# Uses: ITERATIONS=3, TOTAL_DATA_SIZE=120
# Completes within ~2M instructions for Icarus simulation
```

### Options

| Variable           | Default | Description                               |
|--------------------|---------|-------------------------------------------|
| `ITERATIONS`       | 2000    | Outer loop count (10 for validation)      |
| `TOTAL_DATA_SIZE`  | 2000    | Stack memory block (bytes)                |
| `RUN_MODE`         | `PERFORMANCE_RUN` | `VALIDATION_RUN` or `PROFILE_RUN` |

## Data size calculation

CoreMark's data size is controlled by the `seed5` calculation, **not** by
`ITERATIONS`. The size is hard-coded in `core_main.c`:

```c
if (seed5 == 0) seed5 = 7;
ee_s32 num_errors = seed5 & 0x7;           // 7 --> bits 0+1+2 --> divisor = 3
ee_s32 size = 2000 / num_errors;           // 2000 / 3 = 666 (blksize)
```

The `blksize` (666 bytes) is passed to `core_list_init` which computes:
```c
ee_u32 per_item = 16 + sizeof(struct list_data_s);  // ≈ 24
ee_u32 elements = (blksize / per_item) - 2;          // 666/24 - 2 ≈ 25
```

The `find_num` loop bound in `core_bench_list` comes from `seed3_volatile`
(0x66 = 102 by default), which drives `find_num` iterations per call.

**Consequence**: Full CoreMark (ITERATIONS=2000) requires >100M instructions.
Even ITERATIONS=3 requires ~1-2M instructions, too slow for Icarus.

## Simulation test

A smoke test verifies CoreMark starts correctly without crashing:

```bash
cd verification/cocotb/pipeline
make TEST=test_coremark_smoke TOPLEVEL=top_pipeline SIM=icarus \
    VALIDATION_ELF=../../../build/coremark/coremark.elf \
    SMOKE_CYCLES=2000
```

Expected results (pipeline, 2000 cycles):
- ~1100 instructions retired
- CPI ≈ 1.76
- First DM write at 0x600c (BSS clear)
- No PC stuck

## FPGA flow

For FPGA, use the `make flash` target with IMEM_DEPTH=16384, DMEM_DEPTH=8192:

```bash
make flash ARCH=pipeline ELF=build/coremark/coremark.elf
```

The program writes 1 to `tohost` (0x5000) upon completion. Performance
counters (`cycle_count`, `instr_retired`) are captured via SignalTap II using
the `perf_counter` module.
