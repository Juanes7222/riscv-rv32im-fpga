# ADR 016 - Register File: Architectural Reset State

**Status:** Accepted (rewritten 2026-11-12 to match the implemented reset)
**Date:** 2026-05-02
**Depends on:** [ADR 015](015_register_file_ff_array.md)

## Context

On power-up or reset, the flip-flop array backing the register file has an
undefined initial state unless explicitly initialized. The RISC-V ISA defines
that x0 always reads as zero but places no requirement on x1–x31.

## Decision

- **x1–x31 are reset to zero** on the active-low reset edge, through the
  `if (!rst_n)` branch of the write `always_ff` block (ADR 015).
- **x0 has no reset and no storage semantics.** Writes to `rd_addr == 0` are
  discarded at the write gate and both read ports force `32'b0` when the
  address is 0 (ADR 015), so the architectural value of x0 is constant zero
  regardless of the internal `regs[0]` contents. The reset loop therefore
  starts at index 1.

`regs[0]` is a declaration placeholder for address uniformity. In simulation
its storage stays `X`; that value is visible only through a hierarchical
reference to the array, never through a program or a port.

## Rationale

**1. Prevents X-propagation in simulation.**
In Icarus Verilog, flip-flops without explicit reset initialize to `x`. Any
instruction that reads an uninitialized x1–x31 propagates `x` through the ALU,
control signals and memory addresses, which produces a failure that is
indistinguishable from an RTL bug. Resetting x1–x31 removes that class of false
failures.

**2. x0 needs no reset because its value is defined by the read path.**
Forcing the read output to zero is the formally correct interpretation of the
ISA (ADR 015) and makes resetting the storage redundant. It also costs 32 fewer
reset connections.

**3. Consistent with the riscv-tests boot flow.**
The `env/p/` boot code initializes every register it uses, but the tests assume
a clean architectural state. Zeroing x1–x31 at reset makes run-to-run behaviour
deterministic without relying on that initialization order.

**4. Negligible hardware cost.**
Thirty-one reset connections have no measurable effect on Fmax, LUT count or FF
count.

## Consequences

- After de-assertion of `rst_n`, x1–x31 are `32'h0000_0000` and every read of
  x0 returns `32'h0000_0000`.
- A cocotb test that reads `dut.u_rf.regs[0]` directly sees `X` until it
  deposits a value. `test_alu_rv32i.py` initializes it explicitly for that
  reason (ADR 034). This is an observability detail of the simulation, not an
  architectural bug, and it does not require an RTL change.
- If a future implementation stores x0 or adds a debug port that exposes it,
  the debug path must force it to zero, as `dbg_regs` already does in
  `register_file.sv`.
- This does not affect the architectural correctness of any RV32IM program,
  because the ISA guarantees x0 = 0 and makes no promise about the initial
  values of x1–x31.
- ModelSim and Icarus Verilog simulate the reset branch identically; no
  simulator-specific workarounds are needed.
