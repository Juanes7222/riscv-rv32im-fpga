# ADR 034 — Instruction-Level Cocotb Test Layer (test_alu_rv32i)

**Status:** Accepted
**Date:** 2026-06-12
**Depends on:** ADR 029 (cocotb directory structure), ADR 032 (single_cycle cpi_one test layer), ADR 033 (rv32mi test layer + CSR extension)

---

## Context

The cocotb test suite at `verification/cocotb/common/` previously
covered three layers of correctness checks:

- **riscv-tests rv32ui** (37 ELFs) — ISA conformance for the
  base integer instructions. Each ELF runs to completion, the cocotb
  monitor detects the `tohost` write, the test passes or fails
  based on the written value. Coarse-grained: a failure on
  `xor.elf` says "test 23 failed" but not which operand pair.
- **riscv-tests rv32um** (8 ELFs) — same, for M-extension.
- **riscv-tests rv32mi** (15 ELFs) — same, for M-mode interrupt
  and CSR (added in ADR 033).

These three layers prove the DUT implements the spec correctly at
the program level. They do *not* prove that each individual
instruction produces the right result for the specific operand
combinations that the program happens to exercise.


> ```
> verification/cocotb/
>   common/        — instruction-level tests valid for both architectures
> ```

The "instruction-level tests" are cocotb tests that exercise one
instruction at a time, asserting the destination register holds
the expected value AND that no other register was modified. This
is the standard "unit test for a CPU instruction" pattern:

  1. Reset the DUT.
  2. Set the input register state to known values.
  3. Load a single instruction at PC=0.
  4. Step the clock once.
  5. Read the destination register, compare to the expected value
     (computed from the ISA spec).
  6. Verify that all other registers are unchanged.

This layer complements the riscv-tests layer:

- **riscv-tests layer**: "Does the program pass?"
  Fine granularity: per-binary. Diagnostic: weak (one failed
  TESTNUM for the whole binary).
- **instruction-level layer**: "Does this one instruction
  produce the right result for this one operand pair?" Fine
  granularity: per-test. Diagnostic: strong (one failing test
  name and docstring point to the exact scenario).

Both layers are needed for thesis Objective 1: the riscv-tests
prove the DUT passes real programs; the instruction-level tests
prove the DUT produces the right bit-level result for each
operation.

This ADR adds the first instruction-level test file
(`test_alu_rv32i.py`) covering the RV32I ALU operations:
ADD, ADDI, SUB, AND, OR, XOR, SLL, SRL, SRA, SLT, SLTU, LUI,
AUIPC. 27 tests. The pattern is reusable for branches
(`test_branch.py`), loads/stores (`test_load_store.py`), and
jumps (`test_jump.py`); those are out of scope for this ADR but
the test infrastructure is in place.

---

## Decision

### The test pattern

A cocotb test:

```python
@cocotb.test()
async def test_add_positive_operands(dut):
    a, b = 0x12345678, 0x9ABCDEF0
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x0, 1),  # ADD x1, x2, x3
        initial_regs={2: a, 3: b},
        dest_reg=1,
        expected_value=(a + b) & 0xFFFFFFFF,
    )
```

The `_setup_and_execute` helper (in the same file, ~30 lines):

1. `await start_clock(dut)` — start the cocotb Clock (needed for
   the cocotb framework to know about the clock signal).
2. `await _reset(dut, hold_cycles=2)` — assert `rst_n=0`,
   step 2 clock cycles (the DUT resets all regs to 0 and PC to
   0), deassert `rst_n` to 1.
3. Set `dut.u_rf.regs[k] = initial_value` for each input register.
   Also set `dut.u_rf.regs[0] = 0` explicitly (the DUT's reset
   loop is `for (i=1; i<32; i++)`, so `regs[0]` is never
   initialised).
4. Set `dut.u_imem.mem[0] = instruction` to load the test
   instruction at PC=0.
5. `await Timer(2, unit="ns")` — let the simulator apply the
   deposits before the next clock edge.
6. `await _step(dut)` — toggle `clk` for one full period (10 ns).
   The DUT fetches the instruction at PC=0, executes it, writes
   the result to `dest_reg`.
7. Assert `dut.u_rf.regs[dest_reg].value == expected_value`.
8. For every other register (except those in `initial_regs` and
   except `regs[0]` which is excluded), assert `regs[i] == 0`.
   This catches accidental writes.

### Why the manual clock driver

The cocotb 2.0 `Clock` + `RisingEdge` pattern is unreliable for
instruction-level tests:

- The cocotb `Clock` coroutine toggles `clk` in the background.
  The cocotb 2.0 `signal.value = v` is a *deposit*: the new value
  is scheduled but not applied to the simulator until the next
  event. If the Clock toggles `clk` before the deposit is applied,
  the DUT samples the OLD (un-deposited) value at the rising
  edge. Symptom: `regs[dest] == 0` after the test, mysteriously.

- Even when the Clock is not running, `await RisingEdge(dut.clk)`
  races with `signal.value = v` in non-obvious ways. The cocotb
  2.0.1 scheduler is single-threaded across coroutines, so
  the order of operations at the same simulation time is
  scheduler-defined.

The reliable pattern is to drive `clk` manually *inside the test
coroutine*:

```python
async def _step(dut):
    dut.clk.value = 0
    await Timer(5, unit="ns")
    dut.clk.value = 1
    await Timer(5, unit="ns")
```

This is a fully synchronous sequence: the test yields the
simulator exactly once per toggle, and the deposit is guaranteed
to be applied before the next toggle because the cocotb scheduler
processes all pending deposits at each yield point.

The cocotb `Clock` is *also* started (`await start_clock(dut)`)
because the cocotb framework needs to know about the clock signal
to wire up VPI callbacks. The Clock toggles in the background,
but the manual drives "win" because the test coroutine runs
after the Clock coroutine yields on every `Timer`. The two
clocks are in sync (both toggle at 5 ns intervals), and the
test coroutine's manual drives are applied after the Clock
coroutine's drives at each cycle.

The riscv-tests layer (test_rv32i.py, test_rv32m.py,
test_rv32mi.py) does not have this problem because it uses
`monitor_tohost` to wait for a `tohost` write — the cocotb
Clock + RisingEdge pattern works fine for that style of test.

### Why `regs[0]` is excluded from the no-side-effect check

The register file's reset is:

```systemverilog
always_ff @(posedge clk) begin
    if (rst) begin
        for (int i = 1; i < 32; i++) begin
            regs[i] <= 32'b0;
        end
    end else if (wr_en && rd_addr != 5'b0) begin
        regs[rd_addr] <= rd_data;
    end
end
```

The reset loop starts at `i=1`. `regs[0]` is never initialised by
reset, so its internal storage is X (the SystemVerilog `logic`
default). The hardwired read port `rs1_data = (rs1_addr == 5'b0)
? 32'b0 : regs[rs1_addr]` correctly returns 0 for reads of x0,
but the test reads `regs[0]` directly via hierarchy and sees X.

The test explicitly initialises `regs[0] = 0` in the helper
*after* reset, so the "writes to x0 are ignored" assertion works.
The "no other register was modified" loop excludes `regs[0]`
because x0 is not modified by any instruction (writes are
ignored per the ISA spec) — the exclusion is a no-side-effect
loosening, not a check omission.

### Why this file lives in `common/`

Per ADR 029's inventory, `common/` is for "instruction-level
tests valid for both architectures". The tests are semantically
architecture-agnostic: an ADD test verifies the ISA behavior of
ADD, which is the same on single-cycle and pipeline. The tests
do access the DUT's internal hierarchy (`dut.u_rf.regs[k]`,
`dut.u_imem.mem[0]`) which is single-cycle-specific, but the
*test logic* is reusable. When the pipeline is added, the
helpers in this file should be re-targeted to the pipeline's
hierarchy (e.g., a `read_reg(dut, k)` abstraction).

### What is tested

27 tests in `test_alu_rv32i.py`:

| Group     | Tests | Coverage |
|-----------|-------|----------|
| ADD       | 5     | positive, unsigned overflow, signed overflow, zero operand, write-to-x0 ignored |
| SUB       | 3     | positive, negative, zero result |
| Logical   | 6     | AND/OR/XOR with mask, AND/OR with zero, XOR-with-self |
| Shifts    | 5     | SLL by 1, SLL by 31, SRL, SRA sign-extension, SRA -1 |
| Compare   | 4     | SLT signed less-than, SLT signed not-less-than, SLTU unsigned less-than, SLTU unsigned not-less-than |
| Upper-imm | 4     | LUI, LUI zero, LUI max, AUIPC |

The instruction encoders (`encode_r`, `encode_i`, `encode_u`) are
local helpers that construct the 32-bit binary from
funct7/rs2/rs1/funct3/rd/imm12/imm20. The encodings are checked
manually against the RISC-V Unprivileged ISA Spec.

---

## Rationale

### Why this complements (does not replace) the riscv-tests

The riscv-tests layer catches *integration* bugs: a single test
binary exercises ~50-500 instructions across many code paths. If
the program writes 1 to `tohost`, the cocotb test passes. This
proves the DUT as a whole produces the right program-level
behaviour.

The instruction-level layer catches *unit* bugs: a single test
exercises one instruction with one specific pair of operands. The
test asserts the destination register's exact bit pattern. This
proves the DUT produces the right per-instruction result.

A bug that the riscv-tests layer would miss: if `SRA` on a
negative operand is implemented as `SRL` (zero-extension instead
of sign-extension), most test binaries happen to use small
positive operands, so the `tohost` write is correct, and the
riscv-tests pass. The instruction-level layer catches this
because `test_sra_arithmetic_shift_sign_extends` uses a
negative operand and asserts the sign-extended result.

A bug that the instruction-level layer would miss: a bug in
the PC update logic, or in the branch prediction, or in the
pipeline flush on a taken branch. These bugs only manifest
when multiple instructions are executed in sequence. The
riscv-tests layer catches them.

Both layers are needed.

### Why 27 tests is the right first batch

The RV32I base has 47 instructions. A "complete" instruction-
level test suite would have ~100 tests (2-3 scenarios per
instruction). 27 tests cover the most important ALU operations
(arithmetic, logical, shifts, comparisons, upper-immediate)
with 2-5 scenarios per operation.

Out of scope for this ADR but follow-up files:
- `test_branch.py` — BEQ/BNE/BLT/BGE/BLTU/BGEU.
- `test_jump.py` — JAL/JALR.
- `test_load_store.py` — LB/LH/LW/LBU/LHU/SB/SH/SW.
- `test_alu_rv32m.py` — MUL/MULH/MULHSU/MULHU/DIV/DIVU/REM/REMU
  (would need a different test pattern: DIV takes 34 cycles,
  so the test must step the clock 34 times after writing the
  instruction).

These follow the same pattern. ~30 tests each.

### Why the `regs[0]` quirk is documented (not fixed in RTL)

The DUT's reset loop is `for (i=1; i<32; i++)`, not `for (i=0;
i<32; i++)`. This is a minor RTL bug — the riscv-tests `env/p/`
boot code uses `INIT_XREG` to initialise all 32 registers, and
that works because the boot code writes each register explicitly
(via `li xN, 0`). The riscv-tests pass.

For the instruction-level tests, `regs[0]` is observable. The
test initialises `regs[0] = 0` explicitly in the helper, so the
assertion works. Fixing the DUT's reset loop to start at `i=0`
is a 1-character change to `register_file.sv` but is out of
scope for this ADR; it would be a separate "minor RTL bugfix"
decision.

---

## Test results

Before this ADR: 60/60 tests pass in `common/` (45 riscv-tests
+ 15 RV32MI), 45/45 in `single_cycle/` (cpi_one). No
instruction-level tests existed.

After this ADR:

```
common/      : 87/87 PASS
                 37 RV32I + 8 RV32M + 15 RV32MI + 27 ALU
single_cycle/: 45/45 PASS  (cpi_one, unchanged)
```

All 27 instruction-level tests pass. Sim time per test: 36 ns
(2 reset cycles + 1 execute cycle, each 10 ns, plus 6 ns of
`Timer(2, unit="ns")` settle). Total wall time for 27 tests:
~0.5 s. No regression in the existing 60 common tests or 45
cpi_one tests.

The instruction-level tests' diagnostic value was demonstrated
during development: when the first test failed with "x1: expected
0xACF13568, got 0x00000000", the failure pointed to exactly one
operation (ADD positive operands) at exactly one operand pair
(0x12345678 + 0x9ABCDEF0), which is the level of detail the
riscv-tests layer cannot provide.

---

## Consequences

- **A new cocotb file `test_alu_rv32i.py` lives in
  `verification/cocotb/common/`.** The Makefile's
  `COCOTB_TEST_MODULES` includes `test_alu_rv32i`. The
  instruction-level test infrastructure is reusable for branch,
  jump, load/store, and M-extension tests.

- **The cocotb `Clock` + `RisingEdge` pattern is documented
  as unreliable for instruction-level tests** (in the file's
  docstring). The reliable pattern is the manual clock driver
  in `_step`/`_reset`/`_setup_and_execute`. Future test files
  in this style should follow the same pattern.

- **`regs[0]` is explicitly initialised in the helper.** The DUT
  has a minor RTL bug (reset loop starts at `i=1`), but it is
  out of scope for this ADR to fix. Fixing the RTL is a 1-line
  change (`for (int i = 1; i < 32; i++)` → `for (int i = 0; i < 32; i++)`).
  When that fix is applied, the `dut.u_rf.regs[0].value = 0`
  line in the helper can be removed.

- **Follow-up test files** (`test_branch.py`, `test_jump.py`,
  `test_load_store.py`, `test_alu_rv32m.py`) are now
  straightforward to add. They share the same pattern.

- **Reference model impact is unchanged.** The reference model
  (when it exists) does not need to model the cocotb test
  pattern. It models the DUT's behavior; the cocotb tests
  compare the DUT against the ISA spec. The reference model
  enables a *different* style of test (instruction-by-instruction
  golden comparison) which is independent of this layer.

- **No synthesis impact.** The new file is Python only.
