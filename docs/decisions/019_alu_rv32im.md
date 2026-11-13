# ADR 019 - ALU RV32IM: Interface, MULHSU, and Division Strategy

**Status:** Accepted (updated 2026-06-12 - division FSM corrected per ADR 031)  
**Date:** 2026-05-02
**Superseded in part by:** [ADR 031](031_m_extension_test_failures_and_fsm_correction.md) - the division FSM, the `div_done` timing table, the `div_busy` formula, the combinational `next_quotient` / `next_partial` signals, and the corner-case CPI (now 2, not 1) are all governed by ADR 031. **Updated 2026-11-12:** the interface also has `hold` (ADR 044) and `alu_sum` (ADR 050). The combinational multiplier, the MULHSU 33-bit approach and the radix-2 restoring algorithm description remain as stated here.

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
pulse that fires on the `DIV_DONE --> DIV_IDLE` transition and is used by
`top_single_cycle` to gate the register file write enable (see
[ADR 023](023_wr_en_gated.md)).

**2. MULHSU is implemented using 33-bit sign/zero extension.**  
Both operands are extended to 33 bits: `a` sign-extended, `b` zero-extended.
Both 33-bit intermediates are `signed`. Product is `[63:32]` of the 66-bit result.

**3. DIV/DIVU/REM/REMU are implemented as a radix-2 restoring divisor with
fixed 32-cycle latency.** Effective CPI = 34 for a normal division and 2 for
the division-by-zero / signed-overflow corner cases (ADR 031).

**4. All combinational logic uses `always_comb`. All sequential logic uses
`always_ff`.** Consistent with [ADR 010](010_systemverilog_style.md).

**5. Intermediate signals are declared at module scope.** `sub_res`,
`next_quotient` and `next_partial` are driven by a dedicated `always_comb`
block to avoid Quartus inference issues with locally declared variables inside
`always_ff` branches, and to make the post-update quotient and remainder
available in the same cycle (ADR 031). The older `raw_quot` / `raw_rem`
signals no longer exist.

## Rationale

**`div_done` port:**  
Without `div_done`, `top_single_cycle` cannot distinguish the single correct
write cycle (DONE state, result valid) from the 32 incorrect write cycles
(RUNNING state, result not yet valid). `div_busy` remains high during both
RUNNING and DONE, so it cannot gate the write alone. `div_done` is a
registered 1-cycle pulse aligned with the cycle that `div_result` holds the
correct final value - the exact write window needed by the register file.
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
reducing Fmax to 20–30 MHz - making it a function of divider depth rather
than the IF-->WB datapath under comparison. See [ADR 008](008_m_extension_implementation.md).**Module-scope intermediate signals:**
Quartus Prime has inconsistent support for variables declared inside
`begin...end` branches of `always_ff`. Moving `sub_res`, `next_quotient` and
`next_partial` to module scope and driving them from `always_comb` produces
identical behavior while avoiding the inference issue.

## Normative RTL Specification

See [alu_rv32im.sv](../../rtl/shared/alu_rv32im.sv)

## div_done Timing and Effective CPI

Both are governed by [ADR 031](031_m_extension_test_failures_and_fsm_correction.md)
and are summarised here for the reader:

- `div_done` is a registered output that is set on entry to `DIV_DONE`, so it is
  high on the writeback cycle together with the final `div_result`.
- A normal division takes 1 fetch cycle + 32 `DIV_RUNNING` cycles + 1
  `DIV_DONE` writeback cycle: **CPI = 34**.
- Division by zero and signed overflow go `IDLE --> DONE --> IDLE`: **CPI = 2**.
  The original revision of this ADR claimed 1; ADR 031 corrected it.
- All other instructions retire in one cycle: **CPI = 1**.

## Consequences

- `shared_modules.md` must reflect the `div_done`, `hold` and `alu_sum` ports.
- `top_single_cycle.sv` uses `div_done` for `wr_en_gated` (ADR 023).
- All FSM registers reset to zero, consistent with [ADR 016](016_register_file_reset_zero.md).
- `div_done` resets to `1'b0` and is safe to use from the first clock cycle.
- Quartus infers DSP blocks for `mul_ss`, `mul_uu` and `mul_su`.
