# ADR 014 — Memory Initialization Format: `.mem` via `objcopy -O binary` + Python Script

**Status:** Accepted  
**Date:** 2026-04-25

## Context

`instruction_memory.sv` and `data_memory.sv` must be initialized with program
content for both cocotb functional simulation and Quartus Prime synthesis.
The `riscv32-unknown-elf-gcc` toolchain produces binaries in ELF format.
The SystemVerilog `$readmemh` directive expects a plain-text file where each
line contains one 32-bit word in hexadecimal, optionally preceded by address
markers of the form `@addr`.

Three conversion options were evaluated:

1. `riscv32-unknown-elf-objcopy -O binary` + Python script
2. `riscv32-unknown-elf-objcopy -O verilog --verilog-data-width=4`
3. Intel `.mif` format for synthesis, with `$readmemh` retained for simulation

## Decision

The single memory initialization format for this project is **`.mem`**,
generated via the following pipeline:

ELF → (objcopy -O binary) → .bin → (scripts/elf_to_mem.py) → .mem


`scripts/elf_to_mem.py` reads the `.bin` file as 4-byte little-endian words
and writes one 8-character hexadecimal line per word, with no address markers.
The same `.mem` file is used in both cocotb simulation and Quartus Prime
synthesis. The cocotb Makefile invokes `elf_to_mem.py` automatically as a
prerequisite step before each testbench run.

## Rationale

**Option 2 rejected — toolchain fragility.**  
`--verilog-data-width=4` is not available in all versions of GNU Binutils, and
the output format of `objcopy -O verilog` varies across toolchain versions.
This is incompatible with the reproducibility requirement of the experimental
protocol (minimum five synthesis replicas per treatment, per the project
methodology). A toolchain version change could silently alter the file format
without a detectable error until functional verification fails.

**Option 3 rejected — dual-artifact risk.**  
Maintaining `.mif` for synthesis and `.mem` for simulation introduces the risk
that simulation and hardware load different binaries. This class of
desynchronization is difficult to detect: a testbench may pass while the
synthesized design fails for reasons unrelated to the RTL. For a
single-developer project, the maintenance burden of two parallel converters is
not justified.

**Option 1 selected — full control and consistency.**  
`objcopy -O binary` is stable across all modern versions of GNU Binutils and
is included in the standard RISC-V toolchain. It produces a flat memory image
whose mapping to 32-bit words is deterministic. The Python script is explicit
about byte order (little-endian, conformant with RV32I) and output format,
making it straightforward to audit and debug. Harris & Harris (2021) use
`$readmemh` with `.mem` files in their RV32I reference implementation, which
serves as the structural baseline for this project.

**Quartus Prime infers M10K blocks from `$readmemh` in `initial` blocks.**  
Intel Quartus Prime supports M10K inference for memory arrays initialized with
`$readmemh` when the array is declared as a `logic` type and the `initial`
block contains only that call. This is documented in the Cyclone V Device
Handbook (Intel Corporation, 2016) and requires no additional megafunctions.

## Consequences

- `scripts/elf_to_mem.py` must be version-controlled in the repository
  alongside the RTL source.
- The script accepts three positional arguments: path to the `.bin` file,
  memory depth in words (`DEPTH`), and output `.mem` file path. It generates
  exactly `DEPTH` lines; if the binary is shorter than `DEPTH` words, the
  remaining lines are padded with `00002013` (NOP: `ADDI x0, x0, 0`),
  consistent with the out-of-range behavior defined in ADR 011.
- The Makefile for each cocotb testbench includes a `%.mem` rule that depends
  on the corresponding ELF and invokes the script automatically. Generating the
  `.mem` file is never a manual step.
- If `IMEM_DEPTH` or `DMEM_DEPTH` change (see ADR 013), the `DEPTH` argument
  in the Makefile invocation must be updated accordingly. No RTL change is
  required.
- The same script serves `data_memory` when pre-initializing global data
  (`.data`, `.rodata`, `.bss`) by passing `DMEM_DEPTH = 1024` as the `DEPTH`
  argument.
- Reproducibility is guaranteed: the `.mem` artifact is generated
  deterministically from the same ELF on any machine with the toolchain
  installed, with no manual intervention or format ambiguity.