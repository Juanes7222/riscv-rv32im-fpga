# ADR 040 - Pipeline Forwarding Hazard Detection (MEM-RAW and WB-RAW)

**Status:** Superseded by commit `06260fc` (WB-to-ID forwarding)
**Date:** 2026-06-17
**Superseded on:** 2026-06-19
**Depends on:** ADR 039 (pipeline critical bug fixes)

**This ADR documents the original forwarding hazard detection and its
limitations. The limitation was resolved in commit `06260fc` by replacing
the WB-RAW stall with WB-to-ID forwarding and restricting MEM-RAW stalls
to load instructions only. See the "Current state" section at the end.**

---

## Context

ADR 039 fixed four critical bugs in the pipeline (id_ex stall/flush
separation, EX/MEM and MEM/WB stall inputs, wb_instruction
propagation, trap flush scope). After those fixes, the 4 smoke tests
in `verification/cocotb/pipeline/test_pipeline_smoke.py` pass.

Running the riscv-tests against the pipeline revealed additional
failures. Debugging a specific failure (add.S TEST 8, which computes
`x14 = 0 + 0x7fff` with x11=0 loaded by `addi x11,x0,0` and x12=0x7fff
loaded by `lui`+`addi`) revealed a forwarding race condition that
affects any RAW hazard where the producer is in MEM or WB when the
consumer is in ID.

This ADR documents the additional hazard detection logic added to
the pipeline (MEM-RAW and WB-RAW stalls) and the corresponding changes
to the top-level wiring. It also documents what the smoke tests
covered, what still fails in the riscv-tests, and what additional
debugging is needed.

---

## The forwarding race condition

The pipeline's register file is read in the ID stage, and the
combinational read happens at the **beginning** of the clock cycle
(before the non-blocking write at the rising edge is applied). The
standard MIPS pipeline handles this by:

1. Reading the register file in ID (this is what we do).
2. Forwarding from EX/MEM and MEM/WB to the EX stage's ALU (this is
   what we do).
3. The producer in MEM/WB writes the register file at the END of
   the time step (when the producer transitions from MEM to WB).
4. The consumer in ID, when it captures `id_rs1_data` / `id_rs2_data`
   at the next rising edge, sees the NEW value (because the write
   was applied at the END of the previous time step).

The race condition occurs when:

- At cycle T, the producer is in MEM (about to transition to WB at
  the rising edge T-->T+1).
- The consumer is in ID at cycle T (about to transition to ID/EX at
  the rising edge T-->T+1).
- The consumer's rs1 or rs2 matches the producer's rd.

At the rising edge T-->T+1:

- The ID/EX register captures `id_rs1_data` / `id_rs2_data` for the
  consumer. The combinational read of the register file happens
  BEFORE the producer's write is applied (because the write is at
  the END of the time step, the read is at the BEGINNING).
- The producer transitions to MEM/WB, and its write to the register
  file is applied at the END of the time step T-->T+1.

So at cycle T+1, the consumer's `id_rs1_data` / `id_rs2_data`
captures the OLD value (before the write), and the producer's write
becomes visible at cycle T+2 (for the next read).

The forwarding unit (EX/MEM and MEM/WB --> EX ALU) doesn't help here
because:

- At cycle T+1, the producer is in MEM/WB (just transitioned from
  MEM). The forwarding unit sees the producer in MEM/WB.
- The consumer is in ID/EX (just transitioned from ID). The
  forwarding unit forwards to the EX stage's ALU, but the consumer
  is in ID/EX, not EX. So the forwarding doesn't apply.

The fix: **stall the consumer in ID/IF for 1 cycle** when the
producer in MEM has a matching rd (MEM-RAW hazard). After the stall,
the consumer's `id_rs1_data` / `id_rs2_data` are captured at the
NEXT rising edge, when the producer's write is visible in the
register file.

The same problem occurs for the producer in WB (about to write
the register file at the END of the time step). This is the
WB-RAW hazard. The original fix was to stall the consumer in ID/IF
for 1 more cycle, but this caused the deadlock described in ADR 041.

**Current solution (commit `06260fc`):** Instead of stalling, a
combinational WB-to-ID forwarding mux selects `wb_rd_data` directly
when the consumer in ID reads the same register that WB is about to
write. This eliminates the WB-RAW stall entirely and avoids the
circular dependency that caused the ADR 041 deadlock.

---

## The fix

### Hazard detection unit (current design)

`rtl/pipeline/hazard_detection.sv` detects two RAW hazard types:

1. **Load-use** (1-cycle stall): EX is a load and its rd matches
   ID's rs1/rs2. The `load_use` output is asserted; ID/EX is
   bubbled (via the `flush` input to `id_ex_register`).

2. **MEM-RAW** (1-cycle stall): A load in MEM whose rd matches
   ID's rs1/rs2. The producer in MEM is about to write (in MEM/WB
   at the next cycle); the consumer in ID needs to wait one cycle
   so the write is visible.

   **Important:** MEM-RAW is restricted to load instructions only
   (`mem_ru_data_wr_src == WB_MEM`). ALU instructions in MEM are
   excluded because forwarding from EX/MEM to EX resolves them
   without stalling. Without this guard, a back-to-back sequence
   like AUIPC→ADDI that writes and reads the same register would
   assert stall forever --- each copy of the instruction entering
   MEM keeps triggering the stall against the stalled copy in ID,
   causing a permanent deadlock.

The WB-RAW case that existed in the initial design was **removed**
in commit `06260fc`. Instead of stalling, a combinational WB-to-ID
forwarding mux supplies `wb_rd_data` directly to the ID/EX register
when the consumer in ID reads the same register that WB is about to
write. This avoids stalling the pipeline for WB-stage RAW hazards.

The `stall` output is the OR of `load_use_hazard`, `mem_raw_hazard`
and `div_busy`. The `load_use` output is only the load-use signal;
it is used by ID/EX to bubble (not hold) on load-use.

### Top-level wiring (rtl/pipeline/top_pipeline.sv)

The `stall` signal propagates as follows:

- **PC unit** (`pcunit.stall`): holds the PC on any stall.
- **IF/ID register** (`if_id.stall`): holds the IF/ID contents on
  any stall.
- **ID/EX register** (`id_ex.stall`): holds on `div_busy` only (not
  on mem-raw, which only needs the consumer in IF/ID to hold).
- **ID/EX flush**: bubbles on `branch_flush || trap_flush || load_use`
  (mem-raw does not bubble ID/EX, it just holds IF/ID).
- **EX/MEM register** (`ex_mem.stall`): holds on `div_busy` only
  (NOT on mem-raw --- the producer must advance so the hazard
  resolves).
- **MEM/WB register** (`mem_wb.stall`): holds on `div_busy` only
  (same reason as EX/MEM).

Additionally, a **WB-to-ID forwarding mux** (combinational) selects
`wb_rd_data` when `wb_ru_wr && (wb_rd_addr != 5'b0) && (wb_rd_addr ==
id_rs1_addr)` (and similarly for rs2). This provides the WB-stage
result to the ID/EX register without stalling, replacing the
WB-RAW stall that existed in the initial design.

---

## What was tested

### Smoke tests (4 tests, all pass)

- `test_single_add_completes_in_5_cycles`: single ADD retires
  after 5 cycles.
- `test_single_sub_completes_in_5_cycles`: single SUB retires
  after 5 cycles.
- `test_load_use_stall_keeps_load_in_ex`: LW + ADD with
  load-use hazard; the LW's data is correctly forwarded to the
  ADD via MEM/WB after 1 stall cycle.
- `test_wb_instruction_propagates_for_valid_wb`: validates
  bug fix #3 (wb_instruction is not X).

### Debug test (1 test, passes)

- `test_pipeline_debug.test_add_with_lui_x12_no_stalls`:
  reproduces add.S TEST 8 (li x11, 0; lui x12, 8; addi x12, x12, -1;
  add x14, x11, x12). Verifies the MEM-RAW and WB-RAW stalls work
  for a non-load RAW hazard. Pre-fix this test failed; post-fix
  x14 = 0x7fff (correct) at cycle 12.

### riscv-tests (80 tests, all pass after commit `06260fc`)

The fix described in ADR 040 (original WB-RAW stall) was superseded
by commit `06260fc`, which replaced the WB-RAW stall with WB-to-ID
forwarding and restricted MEM-RAW to loads only. After this change,
all pipeline tests pass:

| Suite | Pass | Fail | Notes |
|-------|------|------|-------|
| rv32i | 37   | 0    | All pass after WB-to-ID forwarding fix |
| rv32m | 8    | 0    | All pass |
| rv32mi | 15  | 0    | All pass (EXPECTED_FAIL per ADR 030 remain at 6; EXPECTED_PASS now pass) |
| Smoke | 4    | 0    | Single-cycle and hazard smoke tests |
| Hazards | 7  | 0    | Forwarding, load-use, and RAW hazard tests |
| Control | 4  | 0    | Branch, JAL, JALR tests |
| CPI | 4      | 0    | Performance counter validation |
| **Total** | **80** | **0** | **All pipeline tests pass** |

The original WB-RAW stall (described earlier in this ADR) caused the
deadlock documented in ADR 041. The WB-to-ID forwarding avoids this
deadlock because the consumer receives the correct data immediately
without holding IF/ID, breaking the circular dependency. The MEM-RAW
restriction (loads only) prevents the AUIPC→ADDI infinite stall
scenario.

---

## What is NOT covered (resolved)

The pipeline bugs listed here were fixed after this ADR was written.
All 80 pipeline tests now pass, including the full riscv-tests suite
(37 rv32i, 8 rv32m, 15 rv32mi) and 19 additional cocotb tests
(smoke, debug, hazards, control, CPI). The fix that resolved the
deadlock was WB-to-ID forwarding (commit `06260fc`).

---

## Consequences

- The pipeline correctly handles RAW hazards for loads via
  load-use stall and MEM-RAW stall, and for ALU instructions
  via EX/MEM→EX and MEM/WB→EX forwarding plus WB-to-ID
  forwarding.
- All 80/80 pipeline tests pass (37 rv32i, 8 rv32m, 15 rv32mi,
  4 smoke, 1 debug, 7 hazards, 4 control, 4 CPI).
- All 4 stress tests pass (RAW hazard stress, load-use stress,
  branch stress, M-extension stress).
- The fix was localised to the hazard_detection unit and the
  top-level wiring (adding WB-to-ID forwarding). No changes to
  the pipeline register files or the shared modules.
- The monocycle (top_single_cycle.sv) is unaffected. The 111/111
  monocycle tests continue to pass (no regression).
- The WB-RAW stall from the original design was replaced by
  WB-to-ID forwarding, which avoids the deadlock described
  in ADR 041.
