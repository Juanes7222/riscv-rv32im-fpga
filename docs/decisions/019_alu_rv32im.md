# ADR 019 — ALU RV32IM: Interface, MULHSU, and Division Strategy

**Status:** Accepted (updated 2026-05-02 — div_done port added; Quartus synthesis correction)  
**Date:** 2026-05-02

## Context

The ALU must implement the full RV32IM integer instruction set: ten base RV32I
operations, four multiply operations (M extension), and four divide/remainder
operations (M extension). Three design decisions require formal justification:
the module interface (ports and types), the MULHSU implementation strategy, and
the division implementation strategy.

## Decisions

**1. The module interface includes `clk`, `rst_n`, `div_busy`, and `div_done`.**  
All port signals are declared as `logic`. `div_busy` is the stall signal for
the PC unit and the pipeline hazard unit. `div_done` is a registered 1-cycle
pulse that fires on the `DIV_DONE → DIV_IDLE` transition and is used by
`top_single_cycle` to gate the register file write enable (see
[ADR 023](023_wr_en_gated.md)).

**2. MULHSU is implemented using 33-bit sign/zero extension.**  
Both operands are extended to 33 bits: `a` sign-extended, `b` zero-extended.
Both 33-bit intermediates are `signed`. Product is `[63:32]` of the 66-bit result.

**3. DIV/DIVU/REM/REMU are implemented as a radix-2 restoring divisor with
fixed 32-cycle latency.** Effective CPI = 34 (see [ADR 008](008_m_extension_implementation.md)).

**4. All combinational logic uses `always_comb`. All sequential logic uses
`always_ff`.** Consistent with [ADR 010](010_systemverilog_style.md).

**5. Intermediate signals `sub_res`, `raw_quot`, `raw_rem` are declared at
module scope** and driven by a dedicated `always_comb` block to avoid Quartus
inference issues with locally declared variables inside `always_ff` branches.

## Rationale

**`div_done` port:**  
Without `div_done`, `top_single_cycle` cannot distinguish the single correct
write cycle (DONE state, result valid) from the 32 incorrect write cycles
(RUNNING state, result not yet valid). `div_busy` remains high during both
RUNNING and DONE, so it cannot gate the write alone. `div_done` is a
registered 1-cycle pulse aligned with the cycle that `div_result` holds the
correct final value — the exact write window needed by the register file.
See [ADR 023](023_wr_en_gated.md) for the complete timing analysis.

**`clk`, `rst_n`, `div_busy`:**  
The radix-2 restoring divisor is a sequential state machine that requires a
clock and reset. `div_busy` is the stall signal consumed by `pc_unit`
(single-cycle) and the hazard unit (pipeline).

**MULHSU 33-bit approach:**  
In SystemVerilog, a binary expression with one `signed` and one `unsigned`
operand is evaluated unsigned. `$signed(a) * b` produces the wrong result
when `a` is negative. The 33-bit approach forces fully signed arithmetic
with `b[32] = 0`. See [ADR 009](009_mulhsu_33bit_extension.md).

**Radix-2 restoring division:**  
A combinational `/` synthesized by Quartus produces a ~32-level carry chain,
reducing Fmax to 20–30 MHz — making it a function of divider depth rather
than the IF→WB datapath under comparison. See [ADR 008](008_m_extension_implementation.md).

**Module-scope intermediate signals:**  
Quartus Prime has inconsistent support for variables declared inside
`begin...end` branches of `always_ff`. Moving `sub_res`, `raw_quot`, and
`raw_rem` to module scope and driving them from `always_comb` produces
identical behavior while avoiding the inference issue.

## Normative RTL Specification

See [alu_rv32im.md](../../rtl/shared/alu_rv32im.sv)

## div_done Timing

`div_done` is a registered output (FF). It pulses high for exactly one clock
cycle in two cases:
1. **Normal division (CPI = 34):** fires on the DONE cycle — the same cycle
   that `div_result` receives its correct final value and `div_state` returns
   to IDLE.
2. **Corner cases (CPI = 1):** fires on the IDLE cycle itself, immediately
   after the result is set combinationally.

In both cases, `div_done` is asserted in the same cycle that `div_result` is
correct and `div_busy` is either still high (normal) or never asserted (corner
case). `top_single_cycle` uses `div_done` as the write enable gate (see
[ADR 023](023_wr_en_gated.md)).

## Effective CPI

| Case | Cycles | CPI |
|------|--------|-----|
| Normal division (DIV/DIVU/REM/REMU) | 1 issue + 32 RUNNING + 1 DONE | **34** |
| Corner case (div-by-zero, signed overflow) | 1 (resolved in IDLE) | **1** |
| All other instructions | 1 | **1** |

## Consequences

- `shared_modules.md` must reflect the `div_done` port addition.
- `top_single_cycle.sv` uses `div_done` for `wr_en_gated` (ADR 023).
- All FSM registers reset to zero, consistent with [ADR 015](015_register_file_reset_zero.md).
- `div_done` resets to `1'b0` and is safe to use from the first clock cycle.
- The `inside {}` operator requires Quartus Prime 18.1+, consistent with this
  project's toolchain constraint.
- Quartus will infer DSP blocks for `mul_ss`, `mul_uu`, and `mul_su`.
