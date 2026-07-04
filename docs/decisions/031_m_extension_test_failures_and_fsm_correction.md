# ADR 031 - M-Extension Test Failures and Division FSM Correction

**Status:** Accepted
**Date:** 2026-06-12
**Depends on:** ADR 008 (M extension), ADR 019 (alu_rv32im), ADR 023 (wr_en_gated), ADR 029 (cocotb directory structure)
**Supersedes:** the div_done timing tables in ADR 019 and ADR 023; the division FSM description in ADR 008.

---

## Context

Running the cocotb `test_rv32m_*` suite against the single-cycle design produced
eight failures - every M-extension test failed - while the `test_rv32i_*`
suite passed all 37 RV32I tests in the expected number of cycles. The first
test in the M suite to fail was always `test_rv32m_mul`, with sim time
~5 ns; all subsequent tests showed sim time 0 ns.

Investigation revealed three independent bugs:

1. **`test_rv32m.py` did not call `start_clock(dut)`.** The cocotb scheduler
   cancels the `Clock` coroutine between tests in the same `make` invocation.
   `test_rv32i.py` explicitly starts the clock, but `test_rv32m.py` did not.
   With no clock running, `apply_reset`'s `await RisingEdge(dut.clk)` blocked
   forever. The first test was killed by cocotb's per-test timeout at the
   first `FallingEdge` (5 ns), and the simulator was already dead for the
   remaining seven tests (0 ns signature).

2. **The division FSM's writeback cycle was misaligned with `div_done_r`.**
   `div_done_r` is registered, so the cycle on which `div_state == DIV_DONE`
   and the result is finally visible at `alu_res` saw `div_done_r = 0`. The
   writeback only fired on the next cycle - when `div_state` had already
   returned to `DIV_IDLE`, the PC had advanced, and `rd_addr` belonged to
   the *next* instruction. The fast paths (div-by-zero, signed overflow)
   suffered the same defect: they set the result and `div_done_r` in
   `DIV_IDLE` itself, then stayed in `DIV_IDLE`, so `div_busy = 0` and the
   PC advanced immediately. In both cases the result was either lost or
   written to the wrong register.

3. **The LSB of the quotient was lost on the last division iteration.**
   In the original `DIV_RUNNING` case, the `if (div_count == 5'd31)` branch
   latched the result and transitioned to `DIV_DONE` *without* performing
   the non-blocking update of `div_quotient` and `div_partial`. The
   quotient's bit 0 is produced on iteration 31, so the latched result was
   off by a factor of 2 for every DIV/DIVU test. `div(20, 6)` returned
   `1` instead of `3`; `rem(20, 6)` returned `0` instead of `2`. Because
   the first arithmetic test in `rv32um-div.S` is exactly
   `TEST_RR_OP(2, div, 3, 20, 6)`, every division-family test failed with
   `TESTNUM=2`.

---

## Decision

Three coordinated fixes, one per root cause.

### Fix 1 - `verification/cocotb/common/test_rv32m.py`: mirror the RV32I test setup

`test_rv32m.py` now imports `start_clock` and `reset_and_reload_memories`,
calls `await start_clock(dut)` before loading memories, and uses
`await reset_and_reload_memories(dut, imem_path, dmem_path)` instead of the
synchronous `reload_memories`. The sequence is now identical to
`test_rv32i.py`:

```python
await start_clock(dut)
imem_path, dmem_path = generate_mem_for_elf(elf)
await reset_and_reload_memories(dut, imem_path, dmem_path)
await apply_reset(dut)
result = await monitor_tohost(dut, elf, max_cycles=max_cycles)
```

`monitor_tohost` now receives `max_cycles` (200 000 for MUL, 500 000 for
DIV), matching the budgets in the test file's existing constants.

### Fix 2 - `rtl/shared/alu_rv32im.sv`: hold the PC on the fetch cycle and on the writeback cycle

The division FSM now has a fourth effective input: the combinational
`is_div_op & ~div_processed` term, ORed into `div_busy`:

```systemverilog
logic div_processed;
assign div_busy = (div_state != DIV_IDLE) || (is_div_op & ~div_processed);
```

`div_processed` is a one-cycle pulse set when entering `DIV_DONE` and
cleared on the next cycle. It exists for one purpose: to make the held PC
release one cycle *after* the writeback instead of deadlocking. Without
it, `is_div_op` would stay asserted as long as the current instruction
is the DIV, the PC would stay held, and the FSM would be stuck on the
DIV forever. With it, on the cycle after `DIV_DONE`, `is_div_op_eff` is
forced to 0 and the PC is allowed to advance.

The `DIV_IDLE` and `DIV_RUNNING` cases that transition into `DIV_DONE`
must now also set `div_done_r <= 1` on entry (not on exit). The
`DIV_DONE` case only clears `div_done_r` and transitions back to
`DIV_IDLE`. This makes `div_done_r` visible during `DIV_DONE` itself -
the cycle when the writeback must fire.

The `div_by_zero` and `div_overflow` fast paths now transition
`DIV_IDLE --> DIV_DONE` (not stay in `DIV_IDLE`) so that the PC is held
for one extra cycle. The result and `div_done_r` are still set
combinationally in the same `DIV_IDLE` cycle, but the `DIV_DONE` state
keeps `div_busy = 1` and the top-level `wr_en_gated` armed until the
writeback actually fires.

### Fix 3 - `rtl/shared/alu_rv32im.sv`: latch the result on the *next* cycle, using the post-update values

The division FSM's last iteration now performs the non-blocking update of
`div_quotient` and `div_partial` *and* latches the result in the same
cycle. To make this work, the next-state values are computed
combinationally as `next_quotient` and `next_partial`:

```systemverilog
always_comb begin
    if (!sub_res_sign) begin
        next_quotient = {div_quotient[30:0], 1'b1};
        next_partial  = sub_res;
    end else begin
        next_quotient = {div_quotient[30:0], 1'b0};
        next_partial  = {div_partial_word, div_dividend_msb};
    end
end
```

The result-latch case (on `div_count == 5'd31`) uses these combinational
values, not the registered ones:

```systemverilog
DIV_RUNNING: begin
    div_done_r <= 1'b0;
    div_partial  <= next_partial;
    div_quotient <= next_quotient;
    div_dividend <= {div_dividend_low, 1'b0};

    if (div_count == 5'd31) begin
        case (div_op_r)
            ALU_DIV:  div_result <= div_neg_quot ? (~next_quotient + 1) : next_quotient;
            ALU_DIVU: div_result <= next_quotient;
            ALU_REM:  div_result <= div_neg_rem  ? (~next_partial[31:0] + 1) : next_partial[31:0];
            ALU_REMU: div_result <= next_partial[31:0];
            default:  div_result <= 32'b0;
        endcase
        div_state  <= DIV_DONE;
        div_done_r <= 1'b1;
    end else begin
        div_count <= div_count + 5'd1;
    end
end
```

The first sub-block (the update) executes every iteration, including the
last. The second sub-block (the result latch) executes only on the last
iteration, when `div_count == 5'd31`.

---

## Rationale

### Why the new `div_busy` formula

`div_state` alone cannot hold the PC on the cycle the DIV is fetched:
the FSM sees `is_div_op = 1` only at the end of that cycle, when the
non-blocking transition is already scheduled. Making `div_busy` purely
combinational on `is_div_op` would deadlock - the held PC keeps the
current instruction as the DIV, which keeps `is_div_op` asserted, which
keeps the PC held. The new `div_processed` register breaks the cycle:
it is set on entry to `DIV_DONE` and cleared on the next cycle, so for
exactly one cycle after the writeback, `is_div_op_eff` is forced to 0 and
the PC is released. The state-machine FSM logic is unchanged from the
caller's perspective: it still enters `DIV_DONE` once, transitions out
once, and stays in `DIV_DONE` for exactly one cycle.

### Why `div_done_r` is set on entry, not exit, of `DIV_DONE`

The top-level `wr_en_gated = ru_wr & (~is_div | div_done)` needs
`div_done = 1` on the cycle when the DIV is still the current
instruction (i.e. when the PC is held) and `div_result` is the correct
final value. The FSM has two choices:

1. Set `div_done_r <= 1` on the cycle that transitions INTO `DIV_DONE`
   (the last RUNNING cycle for normal division, or the IDLE cycle for
   the fast paths). The result is latched simultaneously. On the next
   cycle, `DIV_DONE` runs and clears `div_done_r`.

2. Set `div_done_r <= 1` on the cycle when `DIV_DONE` runs, latching
   the result in the same cycle. On the next cycle, `div_done_r` is
   still 1, but `div_state` has already returned to `DIV_IDLE`.

Option 1 is what this ADR adopts. Option 2 is what the pre-fix code
attempted, and it is why every division writeback was off by one cycle.
With option 1, on the `DIV_DONE` cycle, `div_state = DIV_DONE`,
`div_busy = 1`, `div_done_r = 1`, and `div_result` already holds the
correct value (latched one cycle earlier). The writeback fires
correctly.

### Why a combinational `next_quotient` / `next_partial`

The quotient's bit 0 is produced on iteration 31. In a non-blocking
FSM, the value `div_quotient` will *have* after the clock edge is
`{div_quotient[30:0], 1'b1}` or `{div_quotient[30:0], 1'b0}` depending
on `sub_res_sign`. Inside the same cycle, those values are not yet
visible in `div_quotient` - they are visible only at the *next* rising
edge. The cleanest way to make them available to the result-latch case
*in the same cycle* is to compute them combinationally from the current
state and `sub_res_sign`. This is what `next_quotient` and
`next_partial` do.

An alternative is to keep the result in `DIV_DONE` (after the FSM has
left `DIV_RUNNING`) and to combine `div_quotient` and the saved
`sub_res_sign` from the last RUNNING cycle. This was rejected: it
would require an extra register to save `sub_res_sign`, would add a
cycle of latency in some cases, and would couple `DIV_DONE` to
`DIV_RUNNING` in a way that makes the corner-case fast paths (which
skip `DIV_RUNNING` entirely) inconsistent.

### Why the corner-case fast paths now use `DIV_DONE`

The original design held the corner-case result in `DIV_IDLE` for CPI
= 1, with `div_done_r` set the same cycle. The top-level
`wr_en_gated` would have fired correctly *if* `div_done` had been 1
during the `DIV_IDLE` cycle. The bug was that the PC also advanced
during that cycle (because `div_busy = 0`), so the next instruction
became the current instruction and overwrote the result before it was
written. Routing the fast paths through `DIV_DONE` is a one-cycle
penalty (CPI = 2 instead of 1) but it is the only way to make the
writeback land on a cycle when `rd_addr` is still the DIV's
destination register. The alternative - gating the PC with a pure
combinational `is_div_op` without `div_processed` - deadlocks, as
discussed above.

---

## Cycle-by-cycle analysis after the fix

### Normal division (CPI = 34)

| Cycle | `div_state`   | `is_div` | `is_div_op_eff` | `div_done_r` | `div_busy` | `wr_en_gated` | PC   | Action                              |
|-------|---------------|----------|------------------|--------------|------------|----------------|------|-------------------------------------|
| 1     | IDLE-->RUNNING  | 1        | 1                | 0            | 1          | 0              | held | FSM starts, latch operands          |
| 2–32  | RUNNING       | 1        | 1                | 0            | 1          | 0              | held | 31 iterations, quotient/partial update |
| 33    | RUNNING-->DONE  | 1        | 1                | **0 --> 1**    | 1          | 0              | held | Last iteration: latch `div_result`, set `div_done_r` |
| 34    | DONE-->IDLE     | 1        | 1                | **1**        | 1          | **1**          | held | **Writeback.** `div_done_r=1`, `div_result` is correct, `wr_en_gated=1` --> register file writes |
| 35    | IDLE          | 1        | **0** (div_processed=1) | 0       | **0**      | 0              | **adv** | PC releases. `div_processed` clears at the next edge. |
| 36+   | IDLE          | 0 (next instr) | 0          | 0            | 0          | `ru_wr`        | adv  | Normal operation                    |

The quotient's LSB is included because the result is latched from
`next_quotient` (which includes the new bit 0) on cycle 33, not from
the registered `div_quotient`.

### Div-by-zero / signed overflow (CPI = 2)

| Cycle | `div_state`  | `is_div` | `is_div_op_eff` | `div_done_r` | `div_busy` | `wr_en_gated` | PC   | Action                              |
|-------|--------------|----------|------------------|--------------|------------|----------------|------|-------------------------------------|
| 1     | IDLE-->DONE    | 1        | 1                | **0 --> 1**    | 1          | 0              | held | Fast-path: latch `div_result`, set `div_done_r` |
| 2     | DONE-->IDLE    | 1        | 1                | **1**        | 1          | **1**          | held | **Writeback.** `div_result` is the corner-case value (0xFFFFFFFF for div-by-zero, 0x80000000 / 0x0 for overflow). |
| 3     | IDLE         | 1        | **0** (div_processed=1) | 0       | **0**      | 0              | **adv** | PC releases. |
| 4+    | IDLE         | 0 (next instr) | 0          | 0            | 0          | `ru_wr`        | adv  | Normal operation                    |

CPI for the corner case is now 2 (one fetch + one writeback) instead
of 1. The original ADR 008 claim of "1 cycle for div-by-zero" is
updated; the consequences section below records this.

---

## Test results

Before the fix: 0/8 RV32M tests pass (test_rv32m_mul killed at 5 ns,
remaining tests 0 ns because the simulator was already dead).

After the fix (45 tests run in `verification/cocotb/common/Makefile`):

```
** test_rv32i.test_rv32i_add        PASS    5185.00 ns
** test_rv32i.test_rv32i_xori       PASS    2605.00 ns
... (all 37 RV32I tests pass in 1000–5700 ns)
** test_rv32m.test_rv32m_mul        PASS    5125.00 ns
** test_rv32m.test_rv32m_mulh       PASS    5125.00 ns
** test_rv32m.test_rv32m_mulhsu     PASS    5125.00 ns
** test_rv32m.test_rv32m_mulhu      PASS    5125.00 ns
** test_rv32m.test_rv32m_div        PASS    3275.00 ns
** test_rv32m.test_rv32m_divu       PASS    3605.00 ns
** test_rv32m.test_rv32m_rem        PASS    3275.00 ns
** test_rv32m.test_rv32m_remu       PASS    3595.00 ns
** TESTS=45 PASS=45 FAIL=0 SKIP=0
```

Per-test sim time is consistent with the assembly size of each binary
(mul.elf has 450 program words; div.elf has 194) and with the CPI model
(MUL family is 1 cycle/instruction; DIV family adds ~33 cycles per
division).

---

## Consequences

- **ADR 008 timing claim updated.** Div-by-zero and signed-overflow CPI
  is now 2, not 1. The total cycle count for a binary that contains
  only corner-case divisions is `2 x (#divisions) + 1 (last writeback)`.
  For a binary that contains one normal division, the count is
  `33 + 1 + (other-instructions)`. This must be reflected in the
  experimental CPI numbers reported in the thesis.

- **ADR 019 supersession.** The `div_done` timing table in ADR 019 is
  replaced by the one above. The `div_busy` formula is now
  `(div_state != DIV_IDLE) || (is_div_op & ~div_processed)`, not
  `(div_state != DIV_IDLE)`. The `div_processed` register is a new
  module-scope declaration. The combinational `next_quotient` and
  `next_partial` are new module-scope declarations in the existing
  `always_comb` block. The result-latch case of `DIV_RUNNING` uses
  `next_quotient` / `next_partial[31:0]`, not `raw_quot` / `raw_rem`.

- **ADR 023 supersession.** The cycle-by-cycle table in ADR 023 must be
  updated. In particular, ADR 023's "Cycle 1 (issue)" row claims
  `div_done = 1` for the corner case; in the new FSM, `div_done = 1`
  fires on the *DIV_DONE* cycle (one cycle after issue), not on the
  IDLE cycle itself. The corner-case CPI is now 2, not 1.

- **No synthesis impact estimate yet.** The new `div_processed` register
  adds one FF; the new combinational `next_quotient` and `next_partial`
  add ~20 LUTs. The change to `div_busy` is a small additional
  expression. Fmax impact is expected to be negligible.

- **Pipeline update required.** When the pipeline implementation
  arrives, it must replicate the same `div_processed` semantics
  (hold the IF/ID register for one cycle after the writeback). The
  hazard unit must consult `div_processed` to decide whether to
  inject a bubble on the cycle following a division's WB.

- **No new cocotb test added.** The fix is verified by the existing
  `test_rv32m_*` suite. A targeted regression test (e.g. one that
  compares the cycle-by-cycle `alu_res` and `wr_en_gated` against a
  Python model) would be valuable but is out of scope for this ADR.
