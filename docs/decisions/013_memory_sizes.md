# ADR 013 - Instruction and Data Memory Sizes

**Status:** Accepted  
**Date:** 2026-04-24  

## Context

Both instruction memory and data memory are parameterized with a `DEPTH`
value that determines the number of 32-bit words they hold. This value must
be large enough to accommodate the largest program in the verification and
benchmarking suite (CoreMark), while remaining within the M10K embedded memory
budget of the Cyclone V 5CSEMA5F31C6.

## Decision

| Memory | Parameter | Words (synthesis / simulation) | Byte size | M10K usage (approx., synthesis) |
|--------|-----------|--------------------------------|-----------|---------------------------------|
| `instruction_memory` | `IMEM_DEPTH` | 4 096 / 16 384 | 16 KB / 64 KB | ~13 M10K blocks |
| `data_memory` | `DMEM_DEPTH` | 1 024 / 8 192 | 4 KB / 32 KB | ~4 M10K blocks |

The synthesis depths (4 096 words of instructions and 1 024 words of data) are
the smallest that hold CoreMark's image (ADR 046, ADR 047). The simulation
depths (16 384 and 8 192 words) exercise the full address-decoding logic in
CI. The word index of both memories is derived from the depth parameter,
`addr[$clog2(DEPTH)+1:2]`, so a simulation run at a larger depth exercises the
same decoder as the hardware (ADR 047).

## Rationale

**CoreMark binary size (RV32IM bare-metal, -O2):**  
A CoreMark binary compiled for RV32IM with no OS support (newlib-nano,
`-march=rv32im -mabi=ilp32`) produces a text segment of approximately 15–25 KB
and a data/BSS segment of approximately 2–5 KB. A stack of 4–8 KB is
additionally required in data memory. The synthesis depths provide comfortable
margins above these requirements within the 4 KB data window (ADR 047).

**riscv-tests individual test sizes:**    
Each individual riscv-tests binary is under 4 KB. The synthesis instruction
memory fits any individual test with no concern.

**M10K budget:**  
The Cyclone V 5CSEMA5F31C6 has 4 450 Kbits of embedded memory = ~556 KB total
across all M10K blocks. The two memories at synthesis depth use well under 10%
of the total, leaving substantial capacity for the pipelined implementation
and the visualization module. This does not trigger the synthesis overflow
suspension criterion.

## Consequences

- The linker script must fit `.text` + `.rodata` within the instruction
  memory depth and `.data` + `.bss` + stack within the 4 KB data window
  (ADR 047).
- `IMEM_DEPTH` can be doubled to 8192 (32 KB) without affecting any other
  design decision; `DEPTH` is a module parameter and the index width follows
  it automatically.
- Both depths are powers of two, which simplifies address decoding and ensures
  clean M10K inference in Quartus.
