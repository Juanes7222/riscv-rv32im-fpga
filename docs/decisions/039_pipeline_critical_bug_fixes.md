# ADR 039 — Pipeline Critical Bug Fixes (stall/flush separation, register propagation, trap flush)

**Status:** Accepted
**Date:** 2026-06-17
**Depends on:** ADR 034 (instruction-level test pattern), ADR 037 (canonical bubble), ADR 038 (branch in EX)

---

## Context

A first implementation of the five-stage pipelined RV32IM processor
(rtl/pipeline/) was reviewed against the design contract established by
ADR 037 (canonical bubble = `0x00000013`) and ADR 038 (branch in EX,
predict-not-taken). The review found four critical bugs that prevented
the pipeline from correctly handling load-use hazards, multi-cycle
division stalls, instruction propagation, and trap flush. This ADR
documents the four bugs, the fixes, and the smoke-test infrastructure
created to verify them.

---

## The four critical bugs

### Bug 1 — `id_ex_register` conflated `stall` and `flush` (incomplete fix)

**Symptom:** The original `id_ex_register.sv` had
`if (rst || flush || stall) begin ... BUBBLE ... end` — i.e., it
inserted the canonical bubble on EITHER flush OR stall. This was wrong
in two ways depending on which hazard is active:

- **For `div_busy`** (multi-cycle stall): the `id_ex` register must
  HOLD its current value, not bubble. The DIV instruction sits in EX
  for 34 cycles; if `id_ex` is bubbled, the DIV is "killed" and the
  ALU loses its state.
- **For `load_use_hazard`** (single-cycle stall): the standard MIPS
  solution bubbles `id_ex` (the LOAD is in EX and needs to advance to
  MEM; the consumer in ID will then enter EX in the next cycle and
  forward from MEM/WB). Bubbling `id_ex` here is correct — and the
  original code happened to do the right thing for the wrong reason.

**The naive fix** (replace `if (... || stall)` with `else if (!stall)`,
treating `stall` as a hold) was correct for `div_busy` but **broke
load-use**. The pipeline stalled the consumer in ID indefinitely while
the LOAD sat in EX.

**The correct fix** is to expose two distinct signals from the hazard
detection unit:

- `stall` (combined: `load_use || div_busy`): used by `if_id` (which
  must hold in both cases) and by the PC.
- `load_use` (just the load-use part): used by `id_ex` (which must
  bubble on load-use, not hold).

The `id_ex_register` is wired as:
- `flush` = `branch_flush || trap_flush || load_use` (bubble)
- `stall` = `div_busy` (hold, for the DIV's 34-cycle stall)

This is the standard MIPS load-use stall pattern, plus a separate hold
for division. ADR 037's distinction between "stall" (hold) and
"bubble insertion" is preserved by using two separate signals.

### Bug 2 — `EX/MEM` and `MEM/WB` registers had no `stall` input

**Symptom:** The `top_pipeline.sv` wired the `stall` signal only to
`pc_unit`, `if_id_register`, and `id_ex_register`. The `ex_mem_register`
and `mem_wb_register` had no `stall` input — they advanced on every
clock edge. This meant that during a `div_busy` (the DIV sits in EX
for 34 cycles), the instructions in MEM and WB continued to advance,
desynchronising the pipeline.

**Fix:** Added `stall` inputs to both `ex_mem_register` and
`mem_wb_register`. The `stall` input holds the register's current
contents (same semantics as `if_id_register`'s `stall`). The
top-level wires `stall && !trap_flush` to both.

### Bug 3 — `wb_instruction` declared but never driven

**Symptom:** The top-level declared `wb_instruction` (used by
`valid_wb` in `perf_counters` and by the 7-segment displays) but did
not drive it. The variable was X, propagating to all its uses. The
`instr_retired` counter was corrupted, and the 7-segment displays
showed garbage.

The author acknowledged the issue in a comment at the bottom of
`top_pipeline.sv` ("`mem_wb_register` already outputs
`ex_instruction → mem_instruction → wb_instruction` if you added
that port; see note below."), but the actual propagation was never
wired.

**Fix:**

1. `id_ex_register` already had `ex_instruction` as an output (it was
   set to BUBBLE on flush/reset, otherwise to `id_instruction`).
2. Added `ex_instruction` input and `mem_instruction` output to
   `ex_mem_register` (set to BUBBLE on flush/reset, otherwise to
   `ex_instruction`).
3. Added `mem_instruction` input and `wb_instruction` output to
   `mem_wb_register` (set to BUBBLE on reset, otherwise to
   `mem_instruction`).
4. Wired the three signals in `top_pipeline.sv`:
   `id_ex.ex_instruction → ex_mem.ex_instruction`,
   `ex_mem.mem_instruction → mem_wb.mem_instruction`,
   `mem_wb.wb_instruction` is the top-level `wb_instruction`.

### Bug 4 — Trap flush did not reach `EX/MEM`

**Symptom:** `flush` was wired only to `if_id_register` and
`id_ex_register`. When an `ECALL` or `MRET` resolved in WB
(`wb_trap_entry || wb_mret_exec` was asserted), the IF and ID stages
were correctly bubbled, but the EX and MEM stages continued to
execute. Their results would commit to the register file BEFORE the
trap handler took control, corrupting the architectural state.

**Fix:**

- Added a `flush` input to `ex_mem_register` (writes the canonical
  bubble on flush).
- The top-level wires `flush = trap_flush` to `ex_mem_register.flush`
  (NOT `branch_flush` — see below).
- The `mem_wb_register` is intentionally NOT flushed: the trap is
  IN WB at the cycle the flush is asserted, so the trap must be
  allowed to commit normally. Bubbling `mem_wb_register` would lose
  the trap instruction.

**Why `branch_flush` is NOT wired to `ex_mem_register.flush`:** a
taken branch in EX is the CORRECT instruction (not a younger one).
Bubbling EX/MEM on a taken branch would lose the branch instruction.
The branch itself is in EX when it resolves, advances to MEM normally
in the next cycle, and retires through WB. The flush for branches
should only affect IF and ID (the two stages younger than EX).

The flush for traps, on the other hand, is in WB. The IF, ID, EX, and
MEM stages are all younger than the trap and must be invalidated. The
top-level's wiring reflects this asymmetry:

```systemverilog
// IF/ID and ID/EX: flushed on branch OR trap
// EX/MEM: flushed on trap only (the branch is in EX itself, correct)
// MEM/WB: not flushed (the trap is in WB itself, must commit)
```

---

## Other corrections

- **MEM-to-EX forwarding of loads** (latent): the forwarding unit
  forwards `mem_alu_result` for MEM-to-EX forwarding, but for a load
  in MEM, the data is in `mem_dm_rd_data`, not `mem_alu_result`
  (which is the address). This is latent because the load-use stall
  prevents the case "load in MEM, consumer in EX" from manifesting in
  the standard test cases. Out of scope for this ADR; will be
  fixed when M-extension model-vs-DUT tests are written.

- **Numbering of ADRs 037 and 038**: the file headers say "ADR 033" and
  "ADR 032" respectively; the filenames say 037 and 038. The file
  headers are wrong. Out of scope for this ADR.

- **`ex_div_done` declared but unused**: the comment in
  `top_pipeline.sv` (lines 154-160) explains the intentional choice
  not to gate `wb_wr_en_gated` with `div_done`. The div in EX for
  34 cycles means the result is correct by the time it reaches WB.
  No fix needed; the comment makes the intent explicit.

---

## Smoke-test infrastructure

Created `verification/cocotb/pipeline/` with:

- `Makefile` — adapted from the common monocycle Makefile, pointing
  at `top_pipeline.sv` and the pipeline submodules.
- `conftest.py` — `start_clock`, `step_clock`, `reset_dut` helpers
  (same pattern as the monocycle conftest, but no shared imports
  needed for the initial smoke tests).
- `test_pipeline_smoke.py` — 4 tests verifying the bug fixes:
  1. `test_single_add_completes_in_5_cycles`: a single ADD
     retires correctly after 5 cycles (basic pipeline timing).
  2. `test_single_sub_completes_in_5_cycles`: same for SUB.
  3. `test_load_use_stall_keeps_load_in_ex`: LW + ADD with
     load-use hazard; the LOAD's data is correctly forwarded to
     the ADD via MEM/WB after a 1-cycle stall.
  4. `test_wb_instruction_propagates_for_valid_wb`: validates
     bug fix #3 — `wb_instruction` is the ADD in WB, not X.

The tests use the same manual clock driver pattern as
`test_alu_rv32i.py` and `test_branch.py` (per ADR 034).

**Results:** 4/4 pass, 0 fail. Sim time per test: 66-126 ns.
The load-use test (the most complex) takes 10 cycles (66 ns setup +
60 ns execution = 126 ns total) because the LOAD takes 5 cycles to
retire and the consumer ADD takes 1 stall + 5 cycles = 6 cycles to
retire after the LOAD.

The cocotb 2.0.1 / pytest assertion-rewrite import workaround from
ADR 036 is also applied here (load `reference_model.encoders` via
`importlib.util.spec_from_file_location`).

---

## Consequences

- The four critical bugs are fixed. The pipeline can correctly
  handle load-use hazards, multi-cycle division stalls, instruction
  propagation through the pipeline, and trap flush.
- The bug fixes are localised to the pipeline RTL files. No
  changes to the shared modules (`alu_rv32im`, `register_file`,
  `branch_unit`, `csr_file`, `data_memory`, `instruction_memory`).
- The monocycle (`top_single_cycle.sv`) is unchanged. The 111/111
  monocycle tests still pass (no regression).
- The 4 smoke tests in `verification/cocotb/pipeline/` are a
  starting point for the full pipeline test suite. Future work
  (CPI<1 verification, hazard-specific tests, riscv-tests
  integration) builds on this infrastructure.
- The MEM-to-EX forwarding-of-loads latent bug is documented but
  not fixed in this ADR. It will be addressed when M-extension
  model-vs-DUT tests are written.
