# ADR 035 — Branch Instruction-Level Cocotb Tests (test_branch)

**Status:** Accepted
**Date:** 2026-06-12
**Depends on:** ADR 034 (instruction-level test pattern)

---

## Context

ADR 034 added the first instruction-level cocotb test file
(`test_alu_rv32i.py`) using the "one instruction per test" pattern:
reset, set inputs, load one instruction at PC=0, step, assert the
destination register, assert no other register was modified. The
pattern is generic and reusable; this ADR adds the second file
(`test_branch.py`) for the six RV32I branch instructions.

Branches are a different class from ALU operations:

- **No register writeback.** BEQ/BNE/BLT/BGE/BLTU/BGEU do not write
  to any register. The `rd` field in the encoding is unused by the
  spec; the DUT's control_unit sets `ru_wr=0` for `OP_BRANCH`.
- **PC is the observable.** A branch's effect is to update the PC
  to either `pc_plus4=4` (fall through) or `alu_res=PC+imm` (taken).
- **Two-state assertion.** Unlike ALU tests that check a 32-bit
  destination value, branch tests check that the PC is one of two
  values: 4 (fall through) or `imm` (taken). The asymmetry (4 vs
  `imm`) is the test's primary diagnostic — if the wrong branch
  direction is taken, the assertion fires with "PC: expected
  0x00000100, got 0x00000004" (or vice versa).

The 20 tests in `test_branch.py` cover the six branch instructions
across taken/not-taken scenarios, including the corner cases where
signed and unsigned comparisons disagree (e.g., BLT vs BLTU on
negative operands).

---

## Decision

### Test structure

The helper `_setup_and_execute_branch` is the branch-specific
version of ADR 034's `_setup_and_execute`:

```python
async def _setup_and_execute_branch(dut, instruction, initial_regs, expected_pc):
    await start_clock(dut)
    await _reset(dut, hold_cycles=2)
    # Set regs[0]=0 (DUT bug) and the input registers
    for reg, value in initial_regs.items():
        dut.u_rf.regs[reg].value = value
    dut.u_imem.mem[0].value = instruction
    await Timer(2, unit="ns")
    await _step(dut)
    # Assert PC
    actual_pc = int(dut.u_pc.pc.value)
    assert actual_pc == expected_pc
    # Assert no register was written (branches do not writeback)
    for i in range(1, 32):
        if i in initial_regs: continue
        assert int(dut.u_rf.regs[i].value) == 0
```

The encoder `encode_b(funct3, rs1, rs2, imm)` packs the 13-bit
sign-extended branch offset into the B-type instruction word. The
bit layout is:

```
bit 31     = imm[12]   (sign)
bits 30:25 = imm[10:5]
bit  7     = imm[11]
bits 11:8  = imm[4:1]
bit  0     = implicit 0
```

Python's arithmetic right shift and final `& 0x3F` (etc.) work
correctly for both positive and negative `imm`: a negative `imm`
like `-8` has all-ones in the high bits after the shift, and the
mask drops the high bits to extract the field correctly.

### Test coverage (20 tests)

| Branch | Tests | Key cases |
|--------|-------|-----------|
| BEQ    | 4     | equal taken, different not taken, x0/x0 always taken (canonical unconditional branch), max values taken |
| BNE    | 2     | different taken, equal not taken |
| BLT    | 4     | signed -1 < 0 taken (catches unsigned-comparison bug), equal not taken, signed greater not taken, negative < positive taken |
| BGE    | 3     | signed greater taken, equal taken, signed less not taken |
| BLTU   | 3     | unsigned 0 < 0xFFFFFFFF taken, signed-negative treated as huge positive (1 < -1 unsigned taken), -1 < 1 unsigned not taken |
| BGEU   | 3     | unsigned 0xFFFFFFFF > 0 taken, equal taken, 1 >= 0xFFFFFFFF not taken |
| Misc   | 1     | backward branch with negative offset (imm = -8, PC = 0xFFFFFFF8) |

The negative-imm test is the most interesting: it verifies that
the DUT's `imm_gen` correctly sign-extends a 13-bit negative branch
offset to a 32-bit value, then the PC module adds it to PC=0
without truncation, yielding 0xFFFFFFF8.

### What the test does NOT check

- **Branch delay slots.** RISC-V has no branch delay slot; the
  architecture guarantees that the instruction at `pc_plus4` is
  not executed if the branch is taken. The single-cycle DUT
  implements this implicitly: on a taken branch, the PC is
  updated to `alu_res` on the same clock edge, so the next
  instruction fetched is the branch target, not `pc_plus4`.
  Multi-cycle pipelined implementations would need delay-slot
  tests, but the single-cycle DUT does not.

- **Prediction / speculation.** The single-cycle DUT has no
  branch predictor; every branch costs one cycle. Pipeline
  branch-predictor tests are out of scope here.

---

## Rationale

### Why 20 tests is the right number

The 6 branch instructions × ~3 scenarios per instruction (taken,
not taken, edge case) = 18-24 tests. The 20 tests cover:

- Each branch's "happy path" (taken and not taken).
- The signed/unsigned divergence cases for BLT, BGE, BLTU, BGEU.
- The x0/x0 always-taken idiom for BEQ (the most common pattern
  for unconditional jumps in RV32I, before JAL is used).
- The negative-offset case to verify sign extension.

A "complete" test suite would have ~50 tests with permutations of
operand values, but the value of additional tests is low: the
branch unit is a 6-way case statement on `funct3`, and each case
is exercised at least once in the 20 tests. The 60 ELFs in
riscv-tests (rv32ui) provide additional random coverage.

### Why a separate test file, not added to test_alu_rv32i.py

AGENTS.md specifies test grouping:

> "Group related tests by instruction or feature in one file:
>  test_alu_rv32i.py, test_branch.py, test_load_store.py,
>  test_hazards.py"

`test_alu_rv32i.py` is for ALU operations (R-type, I-type ALU,
U-type). Branches are a different feature (control flow vs data
flow). Putting them in separate files keeps each file focused:
one tests the ALU, the other tests the branch unit.

### Why the helper is duplicated, not factored into conftest.py

The helpers `_step` and `_reset` are duplicated from
`test_alu_rv32i.py`. The cleanest solution would be to move them
to `conftest.py` (which is already imported by both files via
`from conftest import start_clock`).

The refactor is deferred to a future ADR (likely 036) because:

- `conftest.py` is named after pytest's conftest convention, but
  it is also used by cocotb tests in this project. The semantics
  of putting manual clock drivers in a conftest file is unclear
  and warrants a separate decision.
- The two duplicated helpers are 20 lines each. The duplication
  cost is low, and refactoring introduces the risk of breaking
  the working 107/107 test suite.

The duplication is documented in a comment in `test_branch.py`:
"duplicated from test_alu_rv32i.py; if a third file needs it,
factor into conftest.py."

---

## Test results

Before this ADR: 87/87 tests pass (37 RV32I + 8 RV32M + 15 RV32MI
+ 27 ALU). No branch tests.

After this ADR:

```
common/      : 107/107 PASS
                 37 RV32I + 8 RV32M + 15 RV32MI + 27 ALU + 20 BRANCH
```

All 20 branch tests pass on the first run, with no DUT changes
needed. The 20-branch-test suite took ~0.7 s wall time (36 ns
per test, same as ALU tests).

Diagnostic value: the negative-imm test (imm = -8) and the
signed-negative BLTU test (1 < -1 unsigned = true) are the two
tests that would catch the most likely bugs:

- The negative-imm test catches a bug where the DUT's imm_gen
  zero-extends (instead of sign-extends) the 13-bit branch offset.
- The signed-negative BLTU test catches a bug where the DUT's
  branch unit applies signed comparison to BLTU/BGEU.

Neither bug exists in the current DUT, so both tests pass.

---

## Consequences

- **A new cocotb file `test_branch.py` lives in
  `verification/cocotb/common/`.** The Makefile's
  `COCOTB_TEST_MODULES` now includes both `test_alu_rv32i` and
  `test_branch`.

- **The instruction-level test pattern from ADR 034 is validated
  for a second instruction class.** The same `_step`/`_reset`/
  manual-clock driver works for both ALU and branch tests. The
  only difference is the observable: ALU tests check a register,
  branch tests check the PC.

- **Helpers `_step` and `_reset` are duplicated in two files.**
  A future refactor ADR can move them to `conftest.py`. The
  duplication is acceptable for now because the risk of breaking
  the 107/107 test suite outweighs the small DRY benefit.

- **Pipeline branch tests are out of scope.** When the pipeline
  DUT is added, `test_branch.py` will need a pipeline-specific
  variant that accounts for branch delay, prediction, and
  flushes. The single-cycle tests serve as the ISA-conformance
  baseline; the pipeline tests build on them.

- **The PC signal `dut.u_pc.pc` is now exercised by cocotb
  tests.** It was previously only observed via the LED
  visualization (`assign ledr = pc[9:0]`). The new test is
  the first to assert the full 32-bit PC value via hierarchy.
