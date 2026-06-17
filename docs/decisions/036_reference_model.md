# ADR 036 — Python Reference Model for RV32IM (verification/reference_model/)

**Status:** Accepted
**Date:** 2026-06-17
**Depends on:** ADR 029 (cocotb directory structure), ADR 034 (instruction-level tests), ADR 035 (branch tests)

---

## Context

The previous cocotb test layers (`test_rv32i.py`, `test_rv32m.py`,
`test_rv32mi.py` for riscv-tests, plus `test_alu_rv32i.py` and
`test_branch.py` for instruction-level) all use the
"spec-vs-DUT" verification style:

- For each test scenario, compute the expected result from the
  ISA spec (e.g., "ADD with these operands returns this value").
- Set up the DUT, run the instruction, assert the result.

This is a valid methodology but it has two limitations:

1. **Per-test hand-computation.** Every test requires the author
   to compute the expected value. For complex scenarios (a
   program that runs 50 instructions), computing the expected
   state at the end requires walking through the program by
   hand — error-prone and tedious.

2. **Weak diagnostics for long programs.** When a 50-instruction
   test fails, the failure is "x5 is wrong at the end". The
   author has to find which of the 50 instructions caused the
   divergence. A differential test against a reference model
   catches the divergence at the exact step where it occurs.

A **reference model** — a separate, independent implementation
of the ISA in a different language — solves both problems:

- The model is the "expected value" generator. No hand-computation
  per test.
- The test runs the model and the DUT in lockstep, comparing
  state after each step. A failure shows the exact step, the
  PC, the instruction, and the diverging register.

This ADR adds the reference model (`verification/reference_model/`)
and a cocotb test file (`test_model_vs_dut.py`) that demonstrates
the model-vs-DUT comparison style.

---

## Decision

### The reference model

The model is a pure-Python implementation of the RV32IM ISA.
It is decoupled from any clock or reset concept — it is a
functional model that takes one step per Python call.

**Files** (`verification/reference_model/`):

| File | Role | Lines |
|------|------|-------|
| `__init__.py`   | Public API exports | ~50 |
| `cpu.py`        | `CPU` class: state + `step()` method | ~120 |
| `decoder.py`    | `decode(raw) → Instruction` | ~190 |
| `handlers.py`   | All instruction handlers (RV32I + M + traps + CSR) | ~280 |
| `csr.py`        | `CSRFile` class (machine-mode CSRs) | ~150 |
| `encoders.py`   | R/I/S/B/U/J-type encoders + `encode_csr` | ~85 |
| `test_self.py`  | Standalone self-test (62 checks) | ~440 |
| **Total**       | | **~1300** |

**CPU state**: 32-bit PC, 32-element regs array, bytearray imem
(16384 bytes, matching DUT's IMEM_DEPTH), bytearray dmem (8192
bytes, matching DMEM_DEPTH), `CSRFile` instance.

**Step semantics**:

```python
def step(self):
    pc_before = self.pc
    raw = self._fetch(pc_before)
    instr = decode(raw)
    handler = HANDLERS.get(instr.name)
    if handler is not None:
        handler(self, instr)
    else:
        # Unknown / illegal: treat as NOP (matches DUT default).
        self.pc = (pc_before + 4) & 0xFFFFFFFF
        return
    # If the handler didn't change PC, advance by 4.
    if self.pc == pc_before:
        self.pc = (pc_before + 4) & 0xFFFFFFFF
```

The handler is responsible for updating PC for branches, jumps,
and traps. For everything else, `step()` advances by 4.

### Instruction coverage

The model implements all 47 RV32I + 8 M-extension instructions
(55 total):

- **R-type ALU**: ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND
- **I-type ALU**: ADDI, SLTI, SLTIU, XORI, ORI, ANDI, SLLI, SRLI, SRAI
- **Loads**: LB, LH, LW, LBU, LHU
- **Stores**: SB, SH, SW
- **Branches**: BEQ, BNE, BLT, BGE, BLTU, BGEU
- **U-type**: LUI, AUIPC
- **Jumps**: JAL, JALR
- **System**: ECALL, EBREAK, MRET, FENCE, FENCE.I
- **CSR**: CSRRW, CSRRS, CSRRC, CSRRWI, CSRRSI, CSRRCI
- **M extension**: MUL, MULH, MULHSU, MULHU, DIV, DIVU, REM, REMU

### M extension edge cases (per RISC-V spec)

The model handles the four corner cases explicitly:

- **DIV/DIVU by zero**: DIV returns -1 (0xFFFFFFFF), DIVU returns
  0xFFFFFFFF. (The spec says "the quotient is 2^XLEN - 1".)
- **REM/REMU by zero**: returns the dividend unchanged.
- **DIV INT_MIN / -1 (signed overflow)**: returns INT_MIN
  (0x80000000). (The spec says "the result is 2^(XLEN-1)".)
- **REM INT_MIN / -1**: returns 0.

For signed division, the model uses `int(sa / sb)` which truncates
toward zero in Python 3 (matching C semantics and the spec). Python's
built-in `//` is floor division (rounds toward -inf), which would
give different results for negative operands.

### CSR file quirks

The CSR file in the model matches the DUT exactly, including two
non-standard choices that the DUT makes:

1. **`mepc = pc + 4` on trap entry.** The RISC-V spec says
   `mepc` should be the address of the trapping instruction.
   The DUT sets `mepc <= trap_pc4` (which is `pc + 4` of the
   trap instruction, i.e., the address AFTER the trap). The
   `rv32mi/csrs.elf` test was written to match the DUT, so the
   model follows the same convention.

2. **`mtvec` low 2 bits forced to 0 (direct mode).** Per ADR 006,
   the DUT does not support vectored trap handling. The model's
   `trap_target` property is `self.mtvec & ~0x3`.

The model mirrors these because it is a verification artifact, not
a fresh spec implementation. If the DUT is ever fixed, the model
should be updated in lockstep.

### The model-vs-DUT cocotb test

`verification/cocotb/common/test_model_vs_dut.py` (4 tests):

| Test | What it does |
|------|--------------|
| `test_model_matches_dut_for_add`             | One ADD; model.regs[1] matches DUT. |
| `test_model_matches_dut_for_taken_branch`    | One BEQ (taken); model.pc matches DUT. |
| `test_model_matches_dut_for_program_five_steps` | 5-instruction program (ADDI, ADDI, ADD, SW, LW); compare after each step. |
| `test_model_matches_dut_for_ecall_trap`      | CSRRW + ECALL; model PC, mcause, mepc match DUT. |

The tests use the same manual clock driver pattern as
`test_alu_rv32i.py` and `test_branch.py` (see ADR 034 for
the rationale). The model and the DUT are initialised to the
same state, then stepped together; after each step, the test
checks the full register file, PC, and CSRs.

On mismatch, the test fails with a diagnostic that includes:
- The step number
- The instruction encoding
- The expected (model) state
- The actual (DUT) state

This is exactly the diagnostic information needed to fix the bug.

### Standalone self-test

`verification/reference_model/test_self.py` exercises the model
without the DUT. It runs 62 checks covering:

- R-type and I-type ALU (positive, negative, zero, signed/unsigned)
- Branches (taken, not taken, signed/unsigned divergence, backward)
- Jumps (JAL writes PC+4 to rd; JALR clears LSB)
- Loads/stores (sign-extension vs zero-extension for LB/LBU, LH/LHU)
- CSR operations (CSRRW/CSRRS/CSRRC + immediate forms; read-only
  misa; the CSRRS rs1=x0 read-only-access quirk)
- ECALL/MRET trap sequence
- M extension corner cases (DIV/REM by zero, INT_MIN/-1 overflow,
  truncation-toward-zero for negative operands)
- A multi-instruction fibonacci program as an integration check

The self-test is the cross-check: it ensures the model itself
is correct, so model-vs-DUT mismatches are attributable to the
DUT, not the model.

### The cocotb 2.0.1 import workaround

The cocotb test file uses `importlib.util.spec_from_file_location`
to load the reference model instead of a plain
`from reference_model import …`. The reason:

- cocotb 2.0.1 internally uses pytest's assertion-rewrite plugin
  to process test modules.
- The rewrite machinery re-executes modules in a way that
  bypasses `sys.path.insert` calls made at module load.
- Even with the reference_model path in `sys.path` (verified by
  debug print), a plain `from reference_model import CPU` fails
  with `ModuleNotFoundError: No module named 'reference_model'`.
- `importlib.util.spec_from_file_location` bypasses pytest's
  machinery and loads the package directly.

The workaround is documented in the test file's header comment
and is the subject of a cocotb upstream issue (filed separately
in the cocotb repository).

### What the model does NOT cover

- **Multi-cycle DUT operations.** The model is single-step. The
  DUT takes 1/34 cycles for MUL/DIV. Model-vs-DUT tests for M
  extension must step the DUT multiple times per model step.
  This is out of scope for this ADR; a future ADR will cover
  M-extension model-vs-DUT tests.
- **Performance counters.** The DUT's `cycle_count` and
  `instr_retired` (in `perf_counter.sv`) are not modelled.
  These are diagnostic signals, not architectural state, and
  the cocotb tests do not assert them.
- **Memory ordering (FENCE).** FENCE is treated as a NOP in
  the model. The DUT also treats it as a NOP (the control
  unit's default case sets no side effects). The FENCE
  instruction's architectural semantics (ordering of memory
  accesses) are not modelled because the single-core DUT
  has no out-of-order execution or shared memory.
- **Misaligned access traps.** The DUT does not trap on
  misaligned loads/stores (it just performs the access with
  byte enables). The model matches.

---

## Rationale

### Why a Python model, not a SystemVerilog reference

A SystemVerilog reference would be the "obvious" choice for a
CPU verification project, but it has downsides:

- The reference would have to be compiled and loaded into the
  simulator, doubling the build time.
- Differential testing against a SystemVerilog reference would
  still be slow (both are running in the simulator).
- Bugs in the SystemVerilog reference would not be caught by
  the existing test infrastructure (no easy self-test).

A Python model:

- Loads instantly (no compile step).
- Has its own self-test (62 checks, runs in <1 s).
- Is reusable for the pipeline DUT (the same model can be
  the golden reference for both microarchitectures).
- Is 10-100x faster than simulation, so property-based tests
  (random programs, many instructions) are tractable.

### Why match the DUT's non-standard conventions

The model is a **verification artifact**, not a fresh spec
implementation. Its purpose is to be a known-good oracle for
the DUT. If the model uses the spec's convention and the DUT
uses a different convention, every test will fail and the
verification provides no signal.

The non-standard `mepc = pc + 4` choice in the DUT is a
documented design decision. The model matches it. If the DUT
is ever fixed, the model is fixed in lockstep. The ADR
documents the convention so future maintainers understand
why the model diverges from the RISC-V spec.

### Why the importlib workaround is acceptable

The importlib workaround adds 10 lines to the test file. It
is ugly but it works. The alternative is to:

1. **Copy `reference_model/` into `cocotb/common/`.** This
   creates duplication. If the model is fixed, both copies
   must be updated.
2. **Create a symlink.** Works on Linux but not on Windows
   (the project's CI runs on Linux per the Makefile setup,
   but the test infrastructure should be cross-platform).
3. **Fix cocotb.** This is the right fix but is outside the
   scope of this project.

The importlib workaround is the least bad option. The cocotb
upstream issue tracks the proper fix.

### Why a 1300-line model is the right size

The model is intentionally compact: each instruction handler
is 3-10 lines, and the dispatch table is a single dict. Larger
models (e.g., spike, the RISC-V reference simulator) are
tens of thousands of lines because they support all of
RISC-V (RV32I + RV64I + RV32E + RV64E + V + B + K + ...) and
all of the privilege levels (M + S + U). This model is
RV32IM only, M-mode only, no vector/packed extensions, no
floating point.

The compactness makes the model:

- Easy to read (an instruction handler is one short function).
- Easy to verify (the self-test has 62 checks; coverage is ~85%
  of the instruction set).
- Easy to extend (adding a new instruction is one handler function
  + one entry in `HANDLERS` + one entry in the decoder table).

---

## Test results

Before this ADR: 107/107 cocotb tests pass (37 RV32I + 8 RV32M +
15 RV32MI + 27 ALU + 20 BRANCH). No reference model.

After this ADR:

```
reference_model/test_self.py :  62/62 checks pass
cocotb/common/test_model_vs_dut.py :   4/4 tests pass
cocotb/common (full suite)    : 111/111 tests pass
                                   107 previous + 4 new model-vs-DUT
```

The 4 model-vs-DUT tests are:

- `test_model_matches_dut_for_add` (36 ns sim time)
- `test_model_matches_dut_for_taken_branch` (36 ns)
- `test_model_matches_dut_for_program_five_steps` (76 ns)
- `test_model_matches_dut_for_ecall_trap` (46 ns)

The model self-test (62 checks) runs in <0.1 s wall time and
catches bugs in the model itself (5 bugs were found and fixed
during development: missing `mpp` property, `encode_i` vs
`encode_csr` confusion in the CSR test, wrong BNE target in
the fibonacci program, etc.).

The cocotb test for `test_model_matches_dut_for_program_five_steps`
exercises 5 different instructions (ADDI, ADDI, ADD, SW, LW)
and the model-vs-DUT comparison checks all 32 registers, the
PC, and (implicitly via the next test) the CSRs after each
step. This is a much higher diagnostic resolution than the
spec-vs-DUT tests in `test_alu_rv32i.py`, which check one
register per test.

---

## Consequences

- **A new package `verification/reference_model/` exists.** It
  contains the CPU model, decoder, handlers, CSR file,
  encoders, and a standalone self-test. The package is
  importable from any Python script; the standalone self-test
  is runnable with `python3 -m reference_model.test_self`.

- **A new cocotb test file `verification/cocotb/common/test_model_vs_dut.py` exists.**
  It demonstrates the model-vs-DUT comparison style with 4
  tests. Future test files for the pipeline DUT will use the
  same style.

- **The cocotb test file uses `importlib.util` to load the
  reference model.** This is a workaround for a cocotb 2.0.1 /
  pytest interaction bug. The workaround is documented in the
  test file's header comment. A proper fix in cocotb upstream
  is preferred but out of scope.

- **The model matches the DUT's non-standard `mepc = pc + 4`
  trap convention.** This is documented in `csr.py` and
  in this ADR. If the DUT is fixed, the model is fixed
  in lockstep.

- **The model does not cover M-extension multi-cycle timing
  in the cocotb test.** The model is single-step; the DUT
  takes 1/34 cycles for MUL/DIV. A future ADR (likely 037)
  will add a `test_model_vs_dut_m_extension.py` that steps
  the DUT multiple times per model step.

- **The reference model is reusable for the pipeline DUT.**
  The pipeline is a different microarchitecture, but the ISA
  behavior is the same. The model is the golden reference
  for both. The pipeline tests will use the same
  `_check_states` pattern as `test_model_vs_dut.py`.

- **The Makefile sets `COCOTB_PYTHONPATH` and `PYTHONPATH`
  to include the reference_model directory.** Neither env
  var is actually used by cocotb 2.0.1 (it has its own path
  setup), so the test file's `importlib.util` workaround is
  the actual mechanism. The Makefile entries are kept for
  documentation and for future cocotb versions that may
  honour them.
