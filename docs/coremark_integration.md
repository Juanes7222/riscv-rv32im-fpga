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
The linker sees a single flat address space but the two memories have
independent address decoders, so each one gets its own image
(`scripts/elf_to_mem_split.py`, ADR 047): the executable sections go to the
instruction image at their own addresses, every other allocated section
(including `.rodata`) goes to the data image relative to the base of the data
window.

| Section  | Address | Size (FPGA) | Notes                              |
|----------|---------|-------------|------------------------------------|
| .text    | 0x0000  | ~9 KB       | Instructions (instruction memory)  |
| .tohost  | 0x6000  | 8 bytes     | Test completion signal             |
| .rodata  | 0x6008  | ~1.4 KB     | CRC tables + strings (read as data)|
| .data    | 0x6558  | 12 bytes    | Initialized global data            |
| .bss     | 0x6564  | ~2 KB       | Zero-initialized data + working block |
| .stack   | 0x6D50  | 688 bytes   | Grows down; `__stack_top = 0x7000` |

**Critical**: the whole data image must fit in the 4 KB data memory
(`DMEM_DEPTH = 1024`), and that includes `.rodata`: CoreMark reads its CRC
tables with loads, and the instruction memory cannot be addressed by a load.
The 2 000-byte working block lives in `.bss` because `MEM_METHOD` is
`MEM_STATIC`; with `MEM_STACK` it would sit on the stack for the whole run and
the image would not fit. The linker fails the build if fewer than 512 bytes of
stack are left. `.tohost` is at the base of the window (0x6000), not at the
riscv-tests value of 0x708, so the bitstream must be built with
`TOHOST_ADDR=0x6000` for the on-board counters to freeze.

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
- First DM write at 0x6564 (BSS clear)
- No PC stuck

## FPGA flow

For FPGA, flash the CoreMark build with its own `tohost` address (the memory
depths of the flow are already 4096/1024 words, ADR 047):

```bash
make -C programs/coremark            # ITERATIONS=2000: ~18 s at 50 MHz (pipeline), ~16 s at 40 MHz (single-cycle, ADR 049)
make flash ARCH=single_cycle ELF=build/coremark/coremark.elf TOHOST_ADDR=0x6000
```

`make flash` regenerates both images from the ELF and applies `TOHOST_ADDR` to
the project before compiling. The program writes 1 to `tohost` (0x6000) upon
completion. Performance counters (`cycle_count`, `instr_retired`) are captured
via SignalTap II using the `perf_counter` module, or read from the VGA console,
whose counters freeze at that write.
