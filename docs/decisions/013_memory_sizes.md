# ADR 013 — Instruction and Data Memory Sizes

**Status:** Accepted  
**Date:** 2026-04-24

## Context

Both instruction memory and data memory are parameterized with a `DEPTH`
value that determines the number of 32-bit words they hold. This value must
be large enough to accommodate the largest program in the verification and
benchmarking suite (CoreMark), while remaining within the M10K embedded memory
budget of the Cyclone V 5CSEMA5F31C6.

## Decision

| Memory | Parameter | Words | Byte size | M10K usage (approx.) |
|--------|-----------|-------|-----------|----------------------|
| `instruction_memory` | `IMEM_DEPTH = 16384` | 16 384 | 64 KB | ~5 M10K blocks |
| `data_memory` | `DMEM_DEPTH = 8192` | 8 192 | 32 KB | ~3 M10K blocks |

Total: approximately **8 M10K blocks** out of the 308 available on the
Cyclone V 5CSEMA5F31C6.

## Rationale

**CoreMark binary size (RV32IM bare-metal, -O2):**  
A CoreMark binary compiled for RV32IM with no OS support (newlib-nano,
`-march=rv32im -mabi=ilp32`) produces a text segment of approximately 15–25 KB
and a data/BSS segment of approximately 2–5 KB. A stack of 4–8 KB is
additionally required in data memory. The 64 KB instruction memory and 32 KB
data memory provide comfortable margins above these requirements.

**riscv-tests individual test sizes:**  
Each individual riscv-tests binary is under 4 KB. The 64 KB instruction memory
fits any individual test with no concern.

**M10K budget:**  
The Cyclone V 5CSEMA5F31C6 has 4 450 Kbits of embedded memory = ~556 KB total
across all M10K blocks. The 96 KB used by the two memories represents ~17% of
the total, leaving substantial capacity for the pipelined implementation and
the visualization module. This does not trigger the synthesis overflow
suspension criterion.

**Address bus width:**  
- Instruction memory: `IMEM_DEPTH = 16384` → word address requires 14 bits
  → byte address range `0x00000000 – 0x0000FFFF` (16-bit address space).
  The PC presents a 32-bit address; the instruction memory uses `addr[15:2]`
  internally and ignores `addr[1:0]` (always zero for aligned instructions)
  and `addr[31:16]` (out-of-range accesses are undefined behavior).
- Data memory: `DMEM_DEPTH = 8192` → word address requires 13 bits → byte
  address range `0x00000000 – 0x00007FFF`. The data memory uses `addr[14:2]`
  internally.

## Consequences

- The linker script must fit `.text` + `.rodata` within 64 KB and `.data` +
  `.bss` + stack within 32 KB.
- If CoreMark with full iterations does not fit, `IMEM_DEPTH` can be doubled
  to 32768 (128 KB, ~10 M10K blocks) without affecting any other design
  decision. This does not require an ADR revision; `DEPTH` is a module
  parameter.
- Both depths are powers of two, which simplifies address decoding and ensures
  clean M10K inference in Quartus.
