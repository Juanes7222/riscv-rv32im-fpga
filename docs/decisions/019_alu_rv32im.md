# ADR 019 — ALU RV32IM: Interface, MULHSU, and Division Strategy

**Status:** Accepted (updated 2026-05-02 — RTL revised for Quartus synthesis compatibility)  
**Date:** 2026-05-02

## Context

The ALU must implement the full RV32IM integer instruction set: ten base RV32I
operations, four multiply operations (M extension), and four divide/remainder
operations (M extension). The design decisions that require formal justification
are: the module interface (ports and types), the implementation strategy for
MULHSU, and the implementation strategy for DIV/DIVU/REM/REMU.

## Decisions

**1. The module interface includes `clk`, `rst_n`, and `div_busy`.**  
All port signals are declared as `logic`. The output `alu_res` is valid
combinationally for all non-division operations and presents the latched
`div_result` while division is in progress.

**2. MULHSU is implemented using 33-bit sign/zero extension.**  
Both operands are extended to 33 bits before multiplication: `a` is
sign-extended, `b` is zero-extended. Both 33-bit intermediates are declared
`signed`. The 66-bit product is computed in fully signed arithmetic; the result
is `product[63:32]`.

**3. DIV/DIVU/REM/REMU are implemented as a radix-2 restoring divisor with
fixed 32-cycle latency** (see [ADR 008](008_m_extension_implementation.md)).
The combinational `/` and `%` operators are not used for synthesis.

**4. Intermediate signals used by the FSM (`sub_res`, `raw_quot`, `raw_rem`)
are declared at module scope** and driven by a dedicated `always_comb` block.

## Rationale

**`clk`, `rst_n`, `div_busy`:**  
The radix-2 restoring divisor is a sequential state machine that requires a
clock and reset. `div_busy` is the stall signal consumed by `pc_unit`
(single-cycle) and the hazard unit (pipeline). Without it, neither
microarchitecture can hold state while the division completes.

**MULHSU 33-bit approach:**  
In SystemVerilog, a binary expression involving one `signed` and one `unsigned`
operand is evaluated as unsigned, the signed operand is reinterpreted as
unsigned. A direct `$signed(a) * b` expression therefore produces the wrong
result when `a` is negative. The 33-bit approach sidesteps this: by making
both operands 33-bit `signed` (with `b`'s MSB permanently 0), the entire
multiplication is in signed arithmetic and the compiler correctly
sign-extends `a`. The 66-bit product `[63:32]` is the correct MULHSU result
for all operand combinations (see [ADR 009](009_mulhsu_33bit_extension.md)).

**Radix-2 restoring division:**  
A combinational divider synthesized from `/` or `%` in Quartus produces a
carry-chain structure approximately 32 levels deep, reducing Fmax to 20–30 MHz
on Cyclone V. This would make the measured Fmax a function of divider depth
rather than of the IF→ID→EX→MEM→WB datapath, which is the architectural
variable under comparison (see [ADR 008](008_m_extension_implementation.md)).

**Module-scope intermediate signals:**  
Quartus Prime has inconsistent support for variables declared inside
`begin...end` branches of `always_ff` blocks when those branches are not
explicitly named. `sub_res`, `raw_quot`, and `raw_rem` are intermediate values
computed combinationally and sampled by the FSM on the next clock edge. Moving
them to module scope and driving them from a dedicated `always_comb` block
produces identical simulation and synthesis behavior while avoiding the
Quartus inference issue. Icarus Verilog and ModelSim simulate both forms
equivalently.

## Normative RTL Specification

See [alu_rv32im.sv](../../rtl/shared/alu_rv32im.sv)

## Result Mux Timing Correctness

When `div_busy` is high, `alu_res = div_result`. During `DIV_RUNNING`,
`div_result` holds a stale value — this is safe because `pc_unit` holds the
PC while `div_busy == 1`, so no instruction retires and no register write
occurs. `div_result` receives its final value on the clock edge that
transitions the FSM from `DIV_DONE` to `DIV_IDLE`. On that same edge,
`div_busy` de-asserts. The combinational path `div_state != DIV_IDLE` goes
low, and `alu_res` presents the correct `div_result` in the same cycle that
`pc_unit` resumes advancing. The timing is correct without any additional
pipeline stage.

## Consequences

- Effective CPI for normal division: **34** (1 issue + 32 RUNNING + 1 DONE).
  This supersedes the CPI = 33 figure in earlier documents; `single_cycle.md`
  must be updated accordingly.
- Division corner cases (by-zero, signed overflow) are resolved in `DIV_IDLE`
  without asserting `div_busy`. Effective CPI for these cases is 1.
- `div_busy` is permanently `0` for all non-division operations. No stall
  penalty is imposed on RV32I or multiply instructions.
- All FSM registers are reset to zero, consistent with [ADR 016](016_register_file_reset_zero.md).
  This prevents X-propagation in the first cocotb simulation iteration.
- The `inside {}` operator in `DIV_IDLE` requires Quartus Prime 18.1 or later.
  If an earlier version is used, it must be replaced with four explicit
  equality comparisons connected by `||`.
- Quartus will infer DSP blocks for `mul_ss`, `mul_uu`, and `mul_su`. The
  exact count depends on place-and-route and is reported in
  `results/single_cycle/` after the first synthesis replica.
