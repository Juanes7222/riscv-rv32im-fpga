# ADR 016 — Register File: All Registers Reset to Zero

**Status:** Accepted  
**Date:** 2026-05-02

## Context

On power-up or reset, the flip-flop array backing the register file has an
undefined initial state unless explicitly initialized. The RISC-V ISA
specification defines that x0 is always zero but places no requirement on the
initial values of x1–x31. Two implementation options exist:

1. Reset only x0 to zero; leave x1–x31 without reset logic.
2. Reset all 32 registers to zero on de-assertion of `rst_n`.

## Decision

**All registers (x0–x31) are reset to zero** on the active-low edge of
`rst_n`. This is implemented via the `if (!rst_n)` branch in the write
`always_ff` block (see ADR 014 implementation contract).

## Rationale

**1. Prevents X-propagation in simulation.**  
In Icarus Verilog (used as the cocotb simulator), flip-flops without explicit
reset logic initialize to `x` (unknown). Any instruction that reads an
uninitialized register propagates `x` through the ALU, control signals, and
memory address lines. The first riscv-tests binary begins executing before any
register has been written by the program, so even a single uninitialized
register can corrupt the entire test result — producing a failing simulation
that is indistinguishable from a real RTL bug. Resetting all registers to zero
eliminates this class of false failures entirely.

**2. Consistent with the reset behavior expected by riscv-tests.**  
The riscv-tests suite assumes a clean architectural state at the start of each
test. While the spec does not mandate zero-initialized registers, the test
programs are written under the assumption that no register contains a
left-over value from a previous test. Running tests in sequence without a full
reset between them could produce inter-test contamination if registers are not
zeroed.

**3. Negligible hardware cost.**  
Adding reset logic to 31 flip-flops (x1–x31) costs 31 additional FF reset
connections in the Cyclone V routing. This has no measurable effect on Fmax,
LUT count, or FF count reported in the synthesis results.

**4. Simplifies cocotb testbench initialization.**  
With all registers zeroed at reset, the testbench can assert and de-assert
`rst_n` at the start of each test and immediately begin driving stimulus
without needing to pre-initialize register values via force/deposit commands.
This keeps the testbench code simpler and the test setup deterministic.

## Consequences

- After de-assertion of `rst_n`, the processor starts with x0–x31 all equal
  to `32'h0000_0000`.
- This does not affect the architectural correctness of any RV32IM program,
  since the ISA makes no guarantee about initial register values and all
  well-written programs initialize registers before using them.
- The `for` loop in the reset branch of `register_file.sv` iterates from 1
  to 31 (not 0 to 31) because x0 is never written, making its reset
  connection redundant. This is a minor code clarity choice with no functional
  consequence.
- `ModelSim` and Icarus Verilog both simulate the reset branch identically.
  No simulator-specific workarounds are needed.
