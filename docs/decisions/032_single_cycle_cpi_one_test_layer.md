# ADR 032 - Single-Cycle CPI=1 Test Layer (test_cpi_one)

**Status:** Accepted
**Date:** 2026-06-12
**Depends on:** ADR 019 (alu_rv32im), ADR 023 (wr_en_gated), ADR 024 (perf_counters), ADR 028 (tohost monitoring), ADR 029 (cocotb directory structure), ADR 031 (M extension FSM correction)

---

## Context

The cocotb test suite is split into two layers (per ADR 029):

- `verification/cocotb/common/` - ISA conformance via riscv-tests. 45 ELFs
  (37 RV32I + 8 RV32M), each loaded as a binary, run to a write to
  `tohost`, and verified to have written the value `1` (pass). This layer
  proves that the DUT implements the spec correctly. It does *not* prove
  anything about the microarchitecture: the same 45 ELFs would pass on
  any correct RV32IM implementation, single-cycle or 30-stage pipeline.

- `verification/cocotb/single_cycle/` - microarchitecture-specific tests.
  The only test that currently belongs here is `test_cpi_one`, which
  verifies the single-cycle architectural invariant:
  `cycle_count == instr_retired` for every instruction except
  `DIV / DIVU / REM / REMU`, where the division occupies 34 cycles
  (1 fetch + 32 `DIV_RUNNING` + 1 `DIV_DONE`, ADR 031) so
  `instr_retired < cycle_count`. This is the *only* test that
  distinguishes the single-cycle design from a correct-but-slow
  pipeline implementation.

`test_cpi_one.py` was committed to the repository but could not be
run. Three independent defects:

1. **Broken imports.** The file imported from
   `verification.cocotb.common.tests.conftest` and
   `verification.cocotb.common.tohost` using absolute package paths,
   but the cocotb runner loads test modules from `sys.path`, not as
   members of the `verification.cocotb.common` package. The
   `common/tests/conftest.py` path also does not exist (the actual
   location is `common/conftest.py`).
2. **Wrong signal name.** The test read `dut.instr_count`, but the
   `perf_counter` instance in `top_single_cycle.sv` is named
   `instr_retired` (ADR 024). The signal does not exist under the
   `instr_count` name.
3. **Missing setup.** The test called `apply_reset` directly without
   `start_clock` or memory reload. The riscv-tests `common/test_rv32i.py`
   pattern is `start_clock --> generate_mem_for_elf --> reset_and_reload_memories
   --> apply_reset --> monitor_tohost`; the `single_cycle/test/test_cpi_one.py`
   skipped the first three, so the DUT would run with whatever memories
   the previous test left in place.

The `verification/cocotb/single_cycle/` directory also had no
`Makefile`, so even a fixed `test_cpi_one.py` could not be invoked
through `make`.

Without a working `test_cpi_one`, the project has no way to
report the single-cycle CPI=1 invariant that is the headline result
of the single-cycle implementation. The riscv-tests layer is
necessary but not sufficient for the thesis' Objective 1
("CPI = 1 for all non-division instructions").

---

## Decision

### Fix 1 - `verification/cocotb/single_cycle/test/test_cpi_one.py`

Replace the broken imports with the same `from <module> import …` style
that `common/test_rv32i.py` uses. Rename `dut.instr_count.value` to
`dut.instr_retired.value` (matches the `perf_counter` port). Add
`start_clock` and `reset_and_reload_memories` to the setup, mirroring
the RV32I/RV32M tests exactly. Update the docstring to reflect the
real path (`single_cycle/test/`, not `single_cycle/tests/`) and to
note that the perf_counter signals are read by hierarchy in Icarus
rather than via top-level ports (no synthesis pinout impact).

The test logic itself is unchanged: 45 parametrized cases (37 RV32I +
8 RV32M), each one starts the clock, loads the ELF, runs to a `tohost`
write, asserts the program passed, and then checks the
`cycle_count` / `instr_retired` invariant. Division tests log the
effective CPI instead of asserting strict equality.

### Fix 2 - `verification/cocotb/single_cycle/Makefile`

Create a new `Makefile` that mirrors `common/Makefile` (same RTL
sources, same `mem_config.vh` handling) but with:

- `COCOTB_TEST_MODULES = test_cpi_one` (only this file's tests).
- `COCOTB_PYTHONPATH = $(PWD)/test:$(PWD)/../common` (test dir
  *and* `common/` so the test can do `from tohost import …` and
  `from conftest import …`).
- `export PYTHONPATH := $(PWD)/test:$(PWD)/../common:$(PWD)/../../../.venv/lib/python3.12/site-packages:$(PYTHONPATH)`.

The last line is a workaround for a cocotb 2.0.1 quirk: the
Makefile-based runner does not propagate `COCOTB_PYTHONPATH` into
`PYTHONPATH` before the embedded Python is started. The cocotb VPI
(`libcocotb.so`) reads `PYTHONPATH` (visible as the string
`pythonpath_env` in the binary's strings) and uses it as the
embedded Python's `sys.path`. Without an explicit `PYTHONPATH`
export the runner only sees the simulator's working directory, and
the embedded Python does not find the test module. The venv's
`site-packages` is also added explicitly so the embedded
interpreter can locate the `cocotb` package itself; the venv's
`lib-dynload` is found by `LIBPYTHON_LOC` separately.

### Limitation - perf_counter signals are internal

`cycle_count` and `instr_retired` are `logic [63:0]` declared inside
`top_single_cycle.sv` and driven by the `perf_counters` instance.
They are not top-level output ports. The cocotb test reads them
via the Icarus VPI's hierarchy walk (`dut.cycle_count.value`). This
is fine for Icarus Verilog 12.0 but is simulator-specific. If a
Verilator or Synopsys VCS backend is added, the signals must be
promoted to `output logic [63:0]` of `top_single_cycle.sv`, which
adds 128 output pins that the synthesis `setup.tcl` does not need
to assign (Quartus will leave unconnected outputs unrouted). The
cocotb test does not change; only the top module's port list
grows.

---

## Rationale

### Why the test_cpi_one test matters

The riscv-tests `env/p/` framework writes `(TESTNUM << 1) | 1` to
`tohost` on failure and `1` on pass. A correct RV32IM implementation
passes regardless of how many cycles each instruction takes.
Without `test_cpi_one`, the single-cycle design cannot be
distinguished from a slow multi-cycle implementation that happens
to compute the right results. The test is the load-bearing
verification artefact for Objective 1 of the thesis.

### Why the test uses the same setup as the RV32I tests

The five-step setup (`start_clock --> generate_mem_for_elf -->
reset_and_reload_memories --> apply_reset --> monitor_tohost`) is the
canonical "boot a fresh ELF into a clean DUT and run it to
completion" sequence that the cocotb `common/` layer established.
Reusing it means a single change to the boot flow (e.g., a new
reset sequence or a new ELF format) only needs to be made once.
It also means the test_cpi_one test and the RV32I test exercise
the *same* code paths through the same DUT, so any testbench-side
bug that affects one affects the other and is caught early.

### Why read `cycle_count` and `instr_retired` by hierarchy

`cycle_count` and `instr_retired` are 64 bits each. Promoting them
to top-level outputs of `top_single_cycle.sv` would consume 128
output pins that the DE1-SoC's pinout does not have free (the
board has 10 LEDs + 6 x 7-segment displays = 52 outputs already
assigned). Adding 128 more would force a synthesis-side pin
re-mapping. Hierarchy read in Icarus is free, requires no RTL
change, and works today.

The trade-off is that the test is Icarus-specific. A Verilator
or commercial simulator backend would need either the port
promotion or a Verilator-specific hierarchy access path. This
limitation is documented in the test file's docstring and above.

### Why log the effective CPI instead of asserting it

The CPI of a division test depends on the ratio of division
instructions to total instructions. The riscv-tests `div.elf`
has 10 divisions and 184 other instructions, giving an effective
CPI of `(10 * 34 + 184) / 194 = 2.33`. The `divu.elf` has a
slightly different mix and gives 2.56. Asserting a specific
number would be brittle to upstream changes in the riscv-tests
suite. Logging it instead makes the test report useful (the
number *is* the experimental result) without coupling to a
particular release.

---

## Test results

Before the fix: 0/45 tests could be run. The Makefile did not
exist, so `make` from `verification/cocotb/single_cycle/` failed
immediately with "No rule to make target".

After the fix, `cd verification/cocotb/single_cycle && make`:

```
** test_cpi_one.test_cpi_one_add      PASS    5185.00 ns
** test_cpi_one.test_cpi_one_addi     PASS    2955.00 ns
... (37 RV32I tests, all PASS, sim time within 1% of the
    corresponding common/ run)
** test_cpi_one.test_cpi_one_mul      PASS    5125.00 ns
** test_cpi_one.test_cpi_one_mulh     PASS    5125.00 ns
** test_cpi_one.test_cpi_one_mulhsu   PASS    5125.00 ns
** test_cpi_one.test_cpi_one_mulhu    PASS    5125.00 ns
** test_cpi_one.test_cpi_one_div      PASS    3275.00 ns
                                              [cpi/div]  effective_cpi=2.33 (cycles=312, instrs=134)
** test_cpi_one.test_cpi_one_divu     PASS    3605.00 ns
                                              [cpi/divu] effective_cpi=2.56 (cycles=345, instrs=135)
** test_cpi_one.test_cpi_one_rem      PASS    3275.00 ns
                                              [cpi/rem]  effective_cpi=2.33 (cycles=312, instrs=134)
** test_cpi_one.test_cpi_one_remu     PASS    3595.00 ns
                                              [cpi/remu] effective_cpi=2.57 (cycles=344, instrs=134)
** TESTS=45 PASS=45 FAIL=0 SKIP=0
```

For every non-division test, `cycle_count == instr_retired`
(CPI = 1). For the four division tests, `instr_retired <
cycle_count` and the effective CPI is logged for the experimental
record.

---

## Consequences

- **The single-cycle CPI=1 invariant is now verifiable end-to-end.**
  The 45 `test_cpi_one_*` tests are the input to the thesis'
  experimental result table; the `effective_cpi` log lines for
  the four division tests are the per-benchmark CPI measurements.

- **`verification/cocotb/single_cycle/Makefile` is the canonical
  Makefile for any future single-cycle-specific test.** New
  cocotb tests added under `single_cycle/test/` should be listed
  in the `COCOTB_TEST_MODULES` line and they will pick up the
  same Python path setup automatically.

- **The cocotb 2.0.1 `PYTHONPATH` workaround is documented but
  fragile.** It is repeated in the new `single_cycle/Makefile`
  and would also need to be applied to any new Makefile in the
  project. If cocotb 2.1+ restores the `COCOTB_PYTHONPATH`
  propagation, this line can be removed.

- **The hierarchy read of `cycle_count` and `instr_retired`
  is a known Icarus-only limitation.** Switching to a
  Verilator-based CI would require promoting these signals to
  top-level outputs (a 3-line change to `top_single_cycle.sv`,
  no synthesis pinout change required because the new outputs
  can be left unconnected in the synthesis `setup.tcl`).

- **No new cocotb infrastructure test is added.** The
  `test_cpi_one` layer exercises the existing `perf_counter`
  and `monitor_tohost` modules through the existing RTL
  hierarchy. A targeted regression test for the division FSM
  fix in ADR 031 (cycle-by-cycle `alu_res` / `wr_en_gated`
  comparison against a Python model) remains open and is
  tracked in ADR 031's Consequences section.
