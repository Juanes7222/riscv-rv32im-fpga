# ADR 029 — cocotb Directory Structure and Makefile Convention

**Status:** Accepted  
**Date:** 2026-05-11  
**Depends on:** ADR 025 (mem_config.vh injection), ADR 027, ADR 028

---

## Context

The root Makefile (Makefile in repo root) invokes `make -C verification/cocotb/common`
and `make -C verification/cocotb/single_cycle` for the `verify-common` and
`verify` targets respectively. Each subdirectory must therefore contain a valid
cocotb Makefile. Nothing inside these directories has been defined yet.

The two layers serve different purposes:

- **`common/`**: ISA conformance tests. Runs the full riscv-tests suite
  (RV32I + RV32M) against the DUT. Identical tests run against single-cycle
  and pipeline — the DUT module is the only difference.
- **`single_cycle/`**: Architecture-specific tests. Exercises properties that
  only make sense for the single-cycle design: CPI=1 for every instruction,
  no stall cycles, performance counter sanity.

---

## Decision

### Directory layout

```
verification/cocotb/
├── common/
│ ├── Makefile
│ ├── tests/
│ │ ├── _init_.py
│ │ ├── conftest.py # shared fixtures: clock, reset, tohost monitor
│ │ ├── test_rv32i.py # parametrized over all rv32ui ELFs
│ │ └── test_rv32m.py # parametrized over all rv32um ELFs
│ └── tohost.py # get_tohost_addr(), monitor_tohost() (ADR 028)
├── single_cycle/
│ ├── Makefile
│ └── tests/
│ ├── _init_.py
│ └── test_cpi_one.py # verifies cycle_count == instr_count for each test
└── pipeline/
├── Makefile
└── tests/
├── _init_.py
└── test_hazards.py # RAW forwarding, load-use stall, branch flush
```


### Makefile contract (common/Makefile — canonical form)

```makefile
# verification/cocotb/common/Makefile
TOPLEVEL_LANG   = verilog
SIM             = icarus
TOPLEVEL        = top_single_cycle        # override: TOPLEVEL=top_pipeline
MODULE          = tests.test_rv32i tests.test_rv32m

VERILOG_SOURCES = \
    $(PWD)/../../../rtl/shared/instruction_memory.sv \
    $(PWD)/../../../rtl/shared/data_memory.sv \
    $(PWD)/../../../rtl/shared/register_file.sv \
    $(PWD)/../../../rtl/shared/alu_rv32im.sv \
    $(PWD)/../../../rtl/shared/branch_unit.sv \
    $(PWD)/../../../rtl/shared/imm_gen.sv \
    $(PWD)/../../../rtl/shared/perf_counter.sv \
    $(PWD)/../../../rtl/single_cycle/control_unit.sv \
    $(PWD)/../../../rtl/single_cycle/pc.sv \
    $(PWD)/../../../rtl/single_cycle/top_single_cycle.sv

# Pass mem_config.vh include path to Icarus (ADR 025)
COMPILE_ARGS    = -I$(PWD)/../../../rtl/shared

include $(shell cocotb-config --makefiles)/Makefile.sim
```

### `mem_config.vh` per-test generation

Each test in `test_rv32i.py` generates its own `mem_config.vh` before
simulation by calling `gen_mem_config.py` with the test's `.mem` file path.
This is done in a `pytest` fixture decorated with `@pytest.fixture(autouse=True)`.
The file is written to `rtl/shared/mem_config.vh` (same path used by
synthesis), overwriting it for each test run. Tests run sequentially (not
in parallel) to avoid race conditions on this shared file.

### Parametrized test structure (test_rv32i.py)

```python
import pytest, cocotb, subprocess, pathlib
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock
from .tohost import get_tohost_addr, monitor_tohost

RISCV_TESTS_DIR = pathlib.Path("build/riscv-tests/rv32ui")
ELF_LIST = sorted(RISCV_TESTS_DIR.glob("*.elf"))

@pytest.mark.parametrize("elf", ELF_LIST, ids=lambda e: e.stem)
@cocotb.test()
async def test_rv32i_instruction(dut, elf):
    # 1. Generate .mem and mem_config.vh for this ELF
    _generate_mem(elf)
    # 2. Clock + reset
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rstn.value = 0
    await Timer(40, units="ns")
    dut.rstn.value = 1
    # 3. Monitor tohost
    result = await monitor_tohost(dut, elf, MAX_CYCLES=200_000)
    assert result == "pass", f"{elf.stem}: FAIL (testnum={result})"
```

---

## Consequences

- Running `make verify-common ARCH=single_cycle` from the root runs all 46
  RV32I + 8 RV32M tests sequentially and reports pass/fail per test.  
- The `common/` Makefile accepts `TOPLEVEL=top_pipeline` as an override,
  allowing the same test suite to run against the pipeline when it is ready,
  without duplicating test code (consistent with ADR 002).  
- `mem_config.vh` is regenerated per test; synthesis replicas are not affected
  because replicas are run separately via `make replicas`.  
- No test runs in parallel. This is a deliberate trade-off: simplicity and
  absence of file-system race conditions over test execution speed.  
- The `single_cycle/tests/test_cpi_one.py` test reads `cycle_count` and
  `instr_count` from the DUT's `perf_counter` outputs and asserts
  `cycle_count == instr_count` after each riscv-tests binary. This is the
  architectural invariant of the single-cycle design and constitutes the
  specific verification criterion for Objective 1 beyond ISA conformance.