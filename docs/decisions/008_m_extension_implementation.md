# ADR 008 — Combinational Multiplier, Multi-Cycle Divisor for Extension M

**Status:** Accepted (updated 2026-04-24 to specify divisor algorithm)  
**Date:** 2026-04-24

## Context

The M extension introduces eight operations: MUL, MULH, MULHSU, MULHU, DIV,
DIVU, REM, REMU. These have substantially different hardware costs:

- **Multiplication:** A 32×32 multiplier produces a 64-bit result. On Cyclone
  V, Quartus infers DSP blocks for multiplication, resulting in a manageable
  critical path (typically 2–3 DSP cascade levels).
- **Division:** A combinational 32-bit divider is one of the deepest
  combinational paths possible in FPGA logic. It cannot be mapped to DSP blocks
  and creates a critical path that can reduce Fmax to 20–30 MHz on Cyclone V,
  artificially dominating the performance comparison between single-cycle and
  pipeline.

## Decision

- **MUL, MULH, MULHSU, MULHU:** Implemented as **combinational logic** in the
  ALU. Quartus is expected to infer Cyclone V variable-precision DSP blocks.
- **DIV, DIVU, REM, REMU:** Implemented as a **radix-2 restoring divisor with
  fixed latency of 32 cycles**. The `div_busy` output is asserted for exactly
  32 cycles after the operation is presented at the inputs, then de-asserted
  when the result is valid.

## Divisor Algorithm: Radix-2 Restoring Division

The restoring division algorithm performs one bit of quotient per cycle using
repeated shift-and-compare operations. For 32-bit operands, the algorithm
requires exactly 32 iterations, making the latency deterministic and
independent of operand values.

**Algorithm sketch (for DIVU):**
```
remainder = 0
quotient  = 0
for i = 31 downto 0:
    remainder = {remainder[30:0], dividend[i]}
    if remainder >= divisor:
        remainder = remainder - divisor
        quotient[i] = 1
    else:
        quotient[i] = 0
```

For signed DIV and REM, operands are converted to unsigned, the unsigned
algorithm is applied, and signs are restored according to the RISC-V
specification.

**State machine:**
- `IDLE`: waiting for a DIV/DIVU/REM/REMU opcode. `div_busy = 0`.
- `RUNNING`: executing 32 iterations. `div_busy = 1`. Counter decrements each
  cycle.
- After 32 cycles: result latched into output registers. Transition to `IDLE`.
  `div_busy` de-asserted.

**CPI contribution:**
A DIV instruction causes the PC to stall for 32 cycles. The effective CPI for
a DIV instruction is 33 (1 cycle for the instruction itself + 32 stall cycles).
This must be reported explicitly in the experimental results.

## Rationale

**Why radix-2 restoring:**  
Radix-2 restoring is the simplest correct iterative divider. It has a
well-understood RTL structure, is straightforward to verify against the
RISC-V specification corner cases (division by zero, signed overflow), and
produces deterministic 32-cycle latency that simplifies CPI analysis. Islam
et al. (2020) use a radix-4 SRT divider for RVCoreP-32IM (Artix-7), which
halves the latency but significantly increases RTL complexity — an unnecessary
trade-off for an undergraduate thesis implementation.

**Why fixed latency:**  
Variable-latency division (early termination when quotient bits stabilize)
would complicate CPI measurement and introduce non-determinism in the stall
duration, making it harder to reproduce and report results consistently across
the five synthesis replicas.

## Consequences

- `alu_rv32im.sv` contains a sequential state machine for division. The module
  requires `clk` and `rst_n` ports even though all non-division operations are
  purely combinational.
- The single-cycle processor does not have CPI = 1 for DIV/DIVU/REM/REMU
  instructions. This is documented in `docs/architecture/single_cycle.md`
  (Known Limitations section) and must be clearly stated when reporting
  effective CPI in the experimental results.
- The `div_busy` signal is routed to `pc_unit.sv` (single-cycle) and to the
  hazard unit (pipeline) to implement stalling.
- Division corner cases per RISC-V specification (division by zero, signed
  overflow) are handled before the iterative algorithm begins, returning the
  specified values in 1 cycle with `div_busy` de-asserted immediately.
  This avoids running 32 cycles of unnecessary computation for a known result.
