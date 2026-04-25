# ADR 012 — Reset Vector: 0x00000000

**Status:** Accepted  
**Date:** 2026-04-24

## Context

When the processor comes out of reset, the PC must be loaded with a defined
address — the reset vector — from which it begins fetching instructions. The
choice of reset vector determines where the linker must place the entry point
of every program that runs on the processor, including the riscv-tests suite
and CoreMark.

## Decision

The reset vector is **`0x00000000`**. On de-assertion of `rst_n`, the PC
register is loaded with `32'h0000_0000`.

## Rationale

1. **Matches the Harvard instruction memory base address.** The instruction
   memory occupies word addresses `[0 .. IMEM_DEPTH-1]`, corresponding to
   byte addresses `0x00000000` through `4*IMEM_DEPTH - 1`. A reset vector of
   `0x00000000` maps directly to the first word of instruction memory without
   any address translation.

2. **Consistent with the Harris & Harris (2021) reference implementation.**
   That design uses `0x00000000` as the reset vector for the same reason.

3. **Simplifies the linker configuration for riscv-tests.** The riscv-tests
   suite provides a default linker script that places `.text.init` at
   `0x80000000` for Linux-capable cores. For bare-metal FPGA implementations,
   a custom linker script is required regardless. Setting the reset vector to
   `0x00000000` is simpler to configure than a non-zero base.

## Consequences

- `pc_unit.sv` resets to `32'h0000_0000` on the active-low edge of `rst_n`.
- All programs compiled for this processor must be linked with
  `--text-segment=0x00000000` (or equivalent). The linker script is documented
  in `docs/reproduction/environment_setup.md`.
- The riscv-tests suite requires a custom linker script (provided in
  `verification/riscv-tests/`) that overrides the default base address.
- `ecall`/`tohost` termination convention: riscv-tests signal completion by
  writing a result code to a `tohost` symbol. The cocotb testbench monitors
  the data memory write address for a write to `tohost` (defined in the linker
  script) to determine pass/fail. This does not require `ecall` to be
  implemented.
