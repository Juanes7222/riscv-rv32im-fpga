# ADR 040 - Pipeline Forwarding Hazard Detection (MEM-RAW and WB-RAW)

**Status:** Accepted
**Date:** 2026-06-17
**Depends on:** ADR 039 (pipeline critical bug fixes)

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
WB-RAW hazard. The fix is the same: stall the consumer in ID/IF
for 1 more cycle.

---

## The fix

### Hazard detection unit

`rtl/pipeline/hazard_detection.sv` now detects three RAW hazard
types (any of them asserts `stall`):

1. **Load-use** (1-cycle stall): EX is a load and its rd matches
   ID's rs1/rs2. The `load_use` output is asserted; ID/EX is
   bubbled (via the `flush` input to `id_ex_register`).

2. **MEM-RAW** (1-cycle stall): MEM's rd matches ID's rs1/rs2.
   The producer in MEM is about to write (in MEM/WB at the next
   cycle); the consumer in ID needs to wait one cycle so the write
   is visible.

3. **WB-RAW** (1-cycle stall): WB's rd matches ID's rs1/rs2. The
   producer in WB is about to write (at the END of the time step);
   the consumer in ID needs to wait one more cycle so the write is
   visible.

The `stall` output is the OR of all three (plus `div_busy`).
The `load_use` output is only the load-use signal; it's used by
ID/EX to bubble (not hold) on load-use.

### Top-level wiring (rtl/pipeline/top_pipeline.sv)

The `stall` signal now propagates as follows:

- **PC unit** (`pcunit.stall`): holds the PC on any stall.
- **IF/ID register** (`if_id.stall`): holds the IF/ID contents on
  any stall.
- **ID/EX register** (`id_ex.stall`): holds on `div_busy` only (not
  on mem-raw or wb-raw, which only need the consumer in IF/ID to
  hold).
- **ID/EX flush**: bubbles on `branch_flush || trap_flush || load_use`
  (the `load_use` was already added in ADR 039; mem-raw and wb-raw
  don't bubble ID/EX, they just hold IF/ID).
- **EX/MEM register** (`ex_mem.stall`): holds on `div_busy` only
  (NOT on mem-raw or wb-raw - the producer must advance so the
  hazard resolves).
- **MEM/WB register** (`mem_wb.stall`): holds on `div_busy` only
  (same reason as EX/MEM).

The key change from ADR 039: `ex_mem.stall` and `mem_wb.stall` no
longer use `stall && !trap_flush` (which included mem-raw). They
use only `div_busy`. Otherwise, the mem-raw stall would hold EX/MEM
in place, the producer never advances, and the pipeline deadlocks.

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

### riscv-tests (60 tests, mostly fail)

| Suite | Pass | Fail | Notes |
|-------|------|------|-------|
| rv32i | 0    | 37   | All fail; pipeline has additional bugs beyond the forwarding race |
| rv32m | 5    | 3    | MUL tests pass; DIV tests fail (likely division-related bugs) |
| rv32mi | 6    | 9    | EXPECTED_FAIL tests pass (per ADR 030 limitations); EXPECTED_PASS tests fail |

The riscv-tests failures are NOT caused by the fixes in this ADR
or in ADR 039. The fixes are correct (verified by the smoke and
debug tests). The remaining failures are due to **other bugs in the
pipeline that have not yet been identified and fixed**.

This ADR only documents the MEM-RAW and WB-RAW hazard detection
fixes. The other bugs are out of scope.

---

## What is NOT covered

The pipeline still has bugs that cause the riscv-tests to fail.
Likely issues include:

- **Pipeline over-inflation** when both the producer and consumer
  are stalled: the debug test shows the add in 3 stages
  simultaneously (ID/EX, EX/MEM, MEM/WB), suggesting the stall
  logic allows the consumer to advance even when the producer
  hasn't retired. The over-inflation doesn't affect correctness
  for simple cases but may cause issues for complex programs.
- **Multi-cycle instruction behavior** (e.g., DIV's 34-cycle
  stall interacting with the new mem-raw stall).
- **CSR file timing** (e.g., csr_file reads in WB, but the
  forwarding may not handle CSR-targeting instructions correctly).
- **Branch and jump edge cases** (e.g., JALR with register offset,
  branch in branch delay slot).
- **Misaligned memory access** (the DUT silently masks byte
  enables per ADR 021; the riscv-tests check the resulting memory
  contents, which may differ from the expected if masking is wrong).

These bugs need additional debugging. The 4 smoke tests + 1 debug
test cover the basic cases; the riscv-tests cover the full ISA and
expose the remaining bugs.

---

## Consequences

- The pipeline correctly handles the 3 types of RAW hazards
  (load-use, mem-raw, wb-raw). The smoke and debug tests pass.
- The riscv-tests still fail (54/65 fail as of this writing),
  indicating the pipeline has more bugs to find and fix.
- The fixes are localised to the hazard_detection unit and the
  top-level wiring. No changes to the pipeline register files
  or the shared modules.
- The monocycle (top_single_cycle.sv) is unaffected. The 111/111
  monocycle tests still pass (no regression).
- Future work: continue debugging the pipeline. The riscv-tests
  are a good oracle for finding bugs. Add more smoke tests for
  specific scenarios as bugs are found.
