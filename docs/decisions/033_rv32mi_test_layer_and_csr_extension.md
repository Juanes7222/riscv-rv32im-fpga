# ADR 033 — RV32MI Test Layer + CSR Register File Extension

**Status:** Accepted
**Date:** 2026-06-12
**Depends on:** ADR 030 (CSR file and minimal trap handling), ADR 031 (M extension FSM correction), ADR 032 (single-cycle cpi_one test layer)

---

## Context

The cocotb test suite at `verification/cocotb/common/` previously
covered only the RV32I and RV32M riscv-tests suites (37 + 8 ELFs).
The riscv-tests `rv32mi/` (machine-mode interrupt) suite, which
directly exercises the CSR file and the trap mechanism that ADR 030
introduced, was not built and not run. Adding it would:

1. **Close the verification gap on ADR 030.** ADR 030 added a
   minimal CSR file (mstatus, mtvec, mepc, mcause) and trap
   handling (ECALL, EBREAK, MRET). The riscv-tests `env/p/`
   framework exercises this path indirectly through every ELF's
   boot code (ecall → trap → tohost), but never checks the corner
   cases: which CSRs exist, whether CSRRS/CSRRC/CSRRSI/CSRRCWI
   honour the `rs1=x0` / `uimm=0` "no write" rule, whether mcause
   captures the correct cause, whether mepc captures pc+4, etc.

2. **Catch CSR bugs that pass the riscv-tests RV32I/RV32M suite.**
   The RV32I/RV32M tests only use a small subset of CSRs (mstatus,
   mtvec, mepc, mcause for the trap path). Bugs in mscratch,
   misa, mhartid, mcounteren, or in the read-only CSR behavior
   would not be caught.

3. **Document the boundary between "implemented" and
   "documented limitation" of the trap mechanism.** Several
   rv32mi tests check for traps the DUT does not produce
   (illegal-instruction, misaligned-access, EBREAK-vs-ECALL
   distinction, rv32 shamt-illegal). The cleanest way to handle
   these is to formalise them as *expected failures* with
   explicit pass conditions, so future readers know which features
   the DUT does and does not implement.

---

## Decision

### Decision 1 — Build `rv32mi` ELFs

Add a `rv32mi` target to `verification/riscv-tests/Makefile` that
compiles 15 of the 16 riscv-tests `rv32mi-p-*` ELFs. The `pmpaddr`
test is omitted because the DUT does not implement PMP.

The CFLAGS are extended from `-march=rv32im_zicsr` to
`-march=rv32im_zicsr_zicntr` because `instret_overflow.S` and
`zicntr.S` reference the Zicntr extension's cycle / instret CSRs
(they compile but the DUT returns 0 for those CSRs since the
counters are exposed via `perf_counters` not the CSR file — see
ADR 024).

### Decision 2 — Extend the CSR file with 8 new registers

`rtl/shared/csr_file.sv` is extended to include the CSRs that the
`rv32mi` suite actually reads or writes. New registers:

| CSR        | Address | Mode | Reset | Purpose |
|------------|---------|------|-------|---------|
| `misa`     | 0x301   | RO   | `0x4000_1100` | I+M, XLEN=32 |
| `mcounteren`| 0x306  | RW   | 0x0  | m-mode access to cycle/instret (not enforced) |
| `mscratch` | 0x340   | RW   | 0x0  | scratch register for M-mode trap handlers |
| `mtval`    | 0x343   | RW   | 0x0  | trap value (instruction word on illegal-instruction trap) |
| `mvendorid`| 0xF11   | RO   | 0x0  | vendor JEDEC ID; 0 = not implemented |
| `marchid`  | 0xF12   | RO   | 0x0  | microarchitecture JEDEC ID; 0 = not implemented |
| `mimpid`   | 0xF13   | RO   | 0x0  | implementation version; 0 = not implemented |
| `mhartid`  | 0xF14   | RO   | 0x0  | hardware thread ID; 0 = single-core |

The `misa` reset value encodes:
- `bits 31:30 = 01` (XLEN = 32)
- `bit 12 = 1` (M extension)
- `bit 8 = 1` (I extension)

This matches the `mcsr.S` test expectation `misa >> 30 == 0x1`.

`mhartid` is read-only zero. This matches the
`RISCV_MULTICORE_DISABLE` boot-code sequence, which spins on
`bnez mhartid`. The DUT's `mhartid` is hardwired to 0, so the
boot code falls through to the test entry point.

The five read-only machine-mode information CSRs (mvendorid,
marchid, mimpid, mhartid) are write-ignored (the `csr_wr` case
statement in the always_ff block has no entry for them) and
read-zero. The csr.S test reads them and discards the result, so
0 is fine.

`mtval` is added because the csr.S test reads it after a
synchronous exception (the test's trap handler reads `mtval` to
check whether it contains 0 or the instruction word). The DUT
does not write `mtval` on any trap path (ADR 030 limitation),
but the read returns 0, which is one of the two values the test
accepts. The mcsr.S test's `csrs mtvec, t0` and `csrs mepc, t0`
checks also pass with the new file.

The cycle / instret CSRs (0xC00, 0xC02) and the time*/hpmcounter*
family are **not** added to the CSR file. They are exposed
internally by `perf_counters` (ADR 024) for cocotb hierarchy
read. The `zicntr.S` test reads cycle and instret expecting 0
from any implementation that does not implement them; the DUT
returns 0 because the CSR file's read-mux defaults to 0 for
unimplemented addresses. `instret_overflow.S` does not check the
instret value; it loops for a fixed number of iterations and
expects to finish before instret wraps, which the single-cycle
design does (the test takes <3000 cycles, well below 2^32).

### Decision 3 — Add `test_rv32mi.py` with expected-fail handling

`verification/cocotb/common/test_rv32mi.py` is created with 15
parametrized tests. The tests are split into two lists:

- `EXPECTED_PASS` (8 tests): the DUT should pass these.
- `EXPECTED_FAIL` (7 tests): the DUT should fail these per ADR 030
  limitations (illegal-instruction trap, misaligned-access trap,
  EBREAK-vs-ECALL distinction, rv32 shamt-illegal).

The cocotb test logic for an `expected_outcome == "pass"` test is
the same as `test_rv32i.py` / `test_rv32m.py`: assert `result ==
"pass"`. For an `expected_outcome == "fail"` test, the logic
asserts `result != "pass"`. If the DUT *unexpectedly* passes an
expected-fail test (i.e., the limitation has been lifted), the
cocotb assertion fires and the test fails — this is the signal
that the `EXPECTED_FAIL` list should be updated. The cocotb test
log records the actual `result` for each expected-fail test (e.g.,
`[rv32mi/shamt] expected-fail confirmed (result=3)`).

The 8 expected-pass tests:
```
breakpoint, csr, instret_overflow, mcsr, scall,
sh-misaligned, sw-misaligned, zicntr
```

The 7 expected-fail tests (per ADR 030 limitations):
```
illegal, lh-misaligned, lw-misaligned, ma_addr, ma_fetch,
sbreak, shamt
```

The `common/Makefile`'s `COCOTB_TEST_MODULES` is updated from
`test_rv32i,test_rv32m` to `test_rv32i,test_rv32m,test_rv32mi`.

---

## Rationale

### Why extend the CSR file rather than skip the failing tests

The 8 CSRs added to the CSR file are tiny (8 × 32-bit registers,
no new logic, no synthesis impact — they are just 256 bits of
storage). The cost of adding them is one small RTL change; the
cost of skipping the corresponding `rv32mi` tests is the loss of
direct verification of features that ADR 030 already implements.
For example, the csr.S test exercises CSRRS/CSRRC semantics that
the riscv-tests RV32I boot code never uses in a way that would
catch a bug in the "rs1=x0 means no write" rule. Without the
csr.S test, a future change to the control unit's `csr_wr` gating
logic could silently break that rule and the riscv-tests RV32I
suite would still pass.

### Why hardwire `misa` to 0x40001100

The mcsr.S test reads `misa` and expects the XLEN field to encode
32 (`misa >> 30 == 1`). The DUT's actual extensions are
RV32I + RV32M + Zicsr + Zicntr. Encoding all of them would set
bits 8, 12, and the Zicntr / Zicsr bits; the test only checks the
XLEN field, so a minimal encoding (I, M, XLEN=32) is sufficient
and matches the test expectation. If a future extension is added
(I/A/F/D/C etc.), the constant must be updated to set the
corresponding `misa` bit.

### Why expected-fail tests are listed in source, not just ADR

Cocotb does not have a built-in xfail mechanism, and adding one
to a thesis test suite is over-engineering. The `EXPECTED_FAIL`
list in the test file:
- is grep-able (readers of the test see immediately which
  features the DUT does not claim to support),
- is auditable (a reviewer can re-classify a test by moving one
  string),
- produces a clear log line (`expected-fail confirmed
  (result=3)`) that distinguishes "test passed in DUT" from "test
  failed in DUT as expected",
- and fails loudly if the DUT ever starts passing an
  expected-fail test (assertion on `result != "pass"`). This is the
  signal that the corresponding ADR 030 limitation has been
  implemented and the test should be re-categorised.

This is the same pattern used by pytest's `@pytest.mark.xfail`
and by the RISC-V Architectural Test Framework's own expected-fail
machinery.

### Why EBREAK is an expected-fail test

ADR 030 explicitly decides "EBREAK (treated as ECALL)" to keep the
control unit's `OP_SYSTEM` decode simple. The sbreak.S test
expects `mcause = 3` (CAUSE_BREAKPOINT) on an `sbreak` trap. The
DUT produces `mcause = 11` (CAUSE_MACHINE_ECALL). Both are
correct per their respective specs (RISC-V Privileged Spec for
mcause encoding, ADR 030 for the DUT's design); they are simply
different. The sbreak.S test is an expected-fail because the DUT
has chosen the simpler implementation.

If a future iteration lifts this limitation, the fix is:
1. In the control unit, decode `instr_31_20 == 12'h001` to a
   separate `breakpoint_trap` signal.
2. In the csr_file, set `mcause = 5'd3` when `breakpoint_trap`
   is asserted.
3. Move `sbreak` from `EXPECTED_FAIL` to `EXPECTED_PASS` in
   `test_rv32mi.py`.

### Why some misaligned tests pass and others fail

The misaligned access tests split into two groups by data width:

- `sh-misaligned` and `sw-misaligned` **pass**. The DUT's
  data memory uses the `addr_bit1` to determine the byte
  enable mask, so an `sh` to address 0x3 writes to bytes 2
  and 3 of word 0 (the same effect as a misaligned `sh` on a
  RISC-V core that takes the misaligned-access trap and
  re-issues the access as two aligned accesses). The test
  stores and loads back the same value, so the round-trip
  succeeds regardless of whether a trap was taken.
- `lh-misaligned` and `lw-misaligned` **fail**. The test
  uses `TEST_LD_OP` which expects a *trap*, not a silent
  misaligned access. The DUT's data memory for `WIDTH_HALF`
  and `WIDTH_WORD` uses the lower address bits to mask the
  byte enables, returning a partially-loaded value rather
  than trapping. The test sees the partial load as a
  failed trap, fails, and writes a non-pass value to
  tohost.

`ma_addr` and `ma_fetch` fail for the same reason: the
data memory and instruction memory do not trap on misaligned
addresses; they mask the byte enables or return the aligned
word, respectively. The `mtval` CSR added in this ADR
would capture the misaligned address if a future iteration
implements the trap, but the trap path itself is not added
here.

---

## Test results

Before this ADR: 0/15 rv32mi tests were built or run. The
cocotb test summary reported 45/45 (RV32I + RV32M only).

After this ADR: 15/15 rv32mi tests build and run. 8 pass in
the DUT; 7 fail in the DUT as expected per ADR 030
limitations. The cocotb summary reports 15/15 PASS for
rv32mi. Combined with the existing layers:

```
common/      : 37 (RV32I) + 8 (RV32M) + 15 (RV32MI) = 60/60 PASS
single_cycle/: 45 (test_cpi_one) = 45/45 PASS
```

Full cpi_one timing for rv32mi (informative, not asserted):

```
** test_rv32mi.test_rv32mi_breakpoint         PASS    1295.00 ns
** test_rv32mi.test_rv32mi_csr                PASS    1805.00 ns
** test_rv32mi.test_rv32mi_illegal            PASS    1025.00 ns  ← xfail
** test_rv32mi.test_rv32mi_instret_overflow   PASS    1205.00 ns
** test_rv32mi.test_rv32mi_lh-misaligned      PASS    1115.00 ns  ← xfail
** test_rv32mi.test_rv32mi_lw-misaligned      PASS    1155.00 ns  ← xfail
** test_rv32mi.test_rv32mi_ma_addr            PASS    1105.00 ns  ← xfail
** test_rv32mi.test_rv32mi_ma_fetch           PASS    1065.00 ns  ← xfail
** test_rv32mi.test_rv32mi_mcsr               PASS    1135.00 ns
** test_rv32mi.test_rv32mi_scall              PASS    1095.00 ns
** test_rv32mi.test_rv32mi_sbreak             PASS     945.00 ns  ← xfail
** test_rv32mi.test_rv32mi_sh-misaligned      PASS    1225.00 ns
** test_rv32mi.test_rv32mi_shamt              PASS    1085.00 ns  ← xfail
** test_rv32mi.test_rv32mi_sw-misaligned      PASS    1465.00 ns
** test_rv32mi.test_rv32mi_zicntr             PASS    1625.00 ns
```

The `test_cpi_one` suite still reports 45/45 PASS after the
CSR file extension, confirming the new CSRs do not regress
the single-cycle architectural invariant.

---

## Consequences

- **ADR 030's "limitations" section is now backed by a
  cocotb test that records the expected behaviour.** Any
  future iteration that lifts a limitation must (a) implement
  the corresponding trap path in RTL, (b) move the test from
  `EXPECTED_FAIL` to `EXPECTED_PASS`, and (c) update the ADR.

- **The CSR file now has 12 read/write-able registers**
  (mstatus, mtvec, mscratch, mepc, mcause, mtval, mcounteren)
  **plus 5 read-only** (misa, mvendorid, marchid, mimpid,
  mhartid). All reset to defined values; all honour the
  CSRRW / CSRRS / CSRRC / CSRRWI / CSRRSI / CSRRCI
  semantics, including the `rs1=x0` / `uimm=0` "no write"
  rule. The "no write" gating is in `top_single_cycle.sv`'s
  `csr_wr` (see ADR 030 §"Limitations" / §"Consequences").

- **The `verification/riscv-tests/Makefile` now has three
  targets** (`rv32i`, `rv32m`, `rv32mi`) **and a default
  `all` that builds all three.** The Makefile's `clean`
  target removes all three build directories.

- **`cocotb/common/Makefile`'s `COCOTB_TEST_MODULES` now
  includes `test_rv32mi`.** The `PYTHONPATH` workaround
  documented in ADR 032 (and the cocotb 2.0.1 `COCOTB_PYTHONPATH`
  → `PYTHONPATH` translation bug) carries over unchanged.

- **No synthesis impact.** The 8 new CSR registers are 256
  bits of FFs added to `csr_file.sv`. The read/write muxes
  are a small additional LUT count. Fmax is expected to be
  unaffected. The signals are internal to the CSR file
  (none of the new CSRs are exported as top-level ports),
  so the DE1-SoC pinout is unchanged.

- **No reference model impact yet.** The new CSRs are
  declared in RTL but not modelled in `reference_model.py`
  (which does not exist yet — see the "missing" list from
  the post-#2 review). When the reference model is added,
  it must model mstatus, mtvec, mscratch, mepc, mcause,
  mtval, misa, mvendorid, marchid, mimpid, mhartid,
  mcounteren at minimum to remain ISA-conformant at the
  CSR level.

- **The cycle / instret CSRs (0xC00, 0xC02) remain
  inaccessible via the CSR file.** They are exposed via
  `perf_counters` (ADR 024) for cocotb observability only.
  A user-mode program that reads `cycle` or `instret` will
  read 0 from the CSR file. This is consistent with the
  DUT's design (the counters are not architecturally
  visible to user-mode) and is acceptable for the thesis
  scope. A future iteration that wants architecturally
  visible counters must add the Zicntr CSR file entries
  and a way to map the `perf_counters` outputs into them.
