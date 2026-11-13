# ADR 029 - cocotb Directory Structure and Makefile Convention

**Status:** Accepted (updated 2026-11-12 to match the implemented tree)
**Date:** 2026-05-11
**Depends on:** ADR 025 (mem_config.vh injection), ADR 027, ADR 028

---

## Context

The root Makefile invokes `make -C verification/cocotb/common`,
`make -C verification/cocotb/single_cycle` and
`make -C verification/cocotb/pipeline` for the verification targets. Each
subdirectory therefore needs a cocotb Makefile, and all of them must share the
simulator setup (Icarus, memory depths, memory images, `mem_config` overrides)
without duplicating it.

The layers serve different purposes:

- **`common/`**: ISA conformance. Runs the riscv-tests suite (RV32I + RV32M +
  RV32MI), the instruction-level ALU/branch layers, the reference-model
  comparison and the validation/diagnostics helpers.
- **`single_cycle/`**: properties that only make sense for the single-cycle
  design: CPI = 1, step mode, program loader.
- **`pipeline/`**: the pipeline's own tests: hazards, forwarding, control,
  CPI, step mode, tail jump, trace, loader.

---

## Decision

### Directory layout

```
verification/cocotb/
├── common.mk                  # shared simulator setup (include at the end)
├── common/
│   ├── Makefile
│   ├── conftest.py            # start_clock(), apply_reset()
│   ├── tohost.py              # generate_mem_for_elf(), monitor_tohost() (ADR 028)
│   ├── benchmark_evidence.py
│   ├── test_rv32i.py          # 37 tests, generated in a loop
│   ├── test_rv32m.py          # 8 tests
│   ├── test_rv32mi.py         # 15 tests (CSR/trap, ADR 033)
│   ├── test_alu_rv32i.py      # instruction-level
│   ├── test_branch.py
│   ├── test_model_vs_dut.py   # reference model (ADR 036)
│   ├── test_validation.py
│   ├── test_coremark_smoke.py
│   └── test_program_loader.py
├── single_cycle/
│   ├── Makefile
│   └── test/
│       ├── test_cpi_one.py
│       └── test_step_mode.py
└── pipeline/
    ├── Makefile
    ├── conftest.py
    └── test_pipeline_*.py, test_loader_executes.py
```

Notes on the real tree, which differs from the first draft of this ADR:

- There is **no `tests/` Python package**. The test modules are top-level
  modules in each directory (and `single_cycle/test/` for the single-cycle
  layer). They are selected through `COCOTB_TEST_MODULES`, not through a
  `MODULE = tests.test_x` dotted path.
- `single_cycle/` keeps its own `test/` subdirectory because it imports
  `tohost` and `conftest` from `../common` through `PYTHONPATH`; the extra
  directory keeps the two helper modules out of the import namespace.
- Each layer has its own `Makefile` that sets `TOPLEVEL`, `COCOTB_TEST_MODULES`
  and `VERILOG_SOURCES`, then ends with `include ../common.mk`.

### Makefile contract

`verification/cocotb/common.mk` centralizes everything that must be identical
in all layers:

```makefile
TOPLEVEL_LANG  = verilog
SIM            = icarus

REPO_ROOT    = $(shell git rev-parse --show-toplevel)
RTL_ROOT     = $(REPO_ROOT)/rtl
BUILD_DIR    = $(REPO_ROOT)/build

SIM_MEM_DIR  = $(BUILD_DIR)/sim
SIM_IMEM     = $(SIM_MEM_DIR)/imem.mem
SIM_DMEM     = $(SIM_MEM_DIR)/dmem.mem

COMPILE_ARGS ?= -I$(RTL_ROOT)/shared
COMPILE_ARGS += -DIMEM_FILE=\"$(abspath $(SIM_IMEM))\"
COMPILE_ARGS += -DDMEM_FILE=\"$(abspath $(SIM_DMEM))\"
COMPILE_ARGS += -P$(TOPLEVEL).IMEM_DEPTH=$(IMEM_DEPTH)
COMPILE_ARGS += -P$(TOPLEVEL).DMEM_DEPTH=$(DMEM_DEPTH)
```

The simulation **never writes `rtl/shared/mem_config.vh`**: it exports the paths
through `-DIMEM_FILE` / `-DDMEM_FILE`, which win because of the `` `ifndef ``
guards installed by ADR 025. `make mem` keeps the header pointed at the
synthesis image, and `build/sim/` holds the per-ELF simulation images. This
removed the per-test rewrite of a shared file that the first draft of this ADR
described.

A layer Makefile therefore only lists its sources and module names:

```makefile
# verification/cocotb/common/Makefile (abridged)
TOPLEVEL            ?= top_single_cycle
COCOTB_TEST_MODULES  = test_rv32i,test_rv32m,test_rv32mi,test_alu_rv32i,test_branch,test_model_vs_dut

VERILOG_SOURCES = $(SHARED_SRCS) $(SHARED_VGA_SRCS) ... $(RTL_ROOT)/single_cycle/top_single_cycle.sv

include ../common.mk
```

`common/Makefile` accepts `TOPLEVEL=top_pipeline` as an override, so the ISA
suite can be pointed at either microarchitecture without duplicating tests
(ADR 002).

### Test style

Tests are plain `cocotb.test()` coroutines. Parametrization is done by
generating one coroutine per case in a module-level loop, which is what keeps
the per-test names (`test_rv32i_add`, ...) visible in `results.xml` without a
pytest plugin:

```python
def _make_test(test_name: str):
    elf = _TESTS_DIR / f"{test_name}.elf"

    @cocotb.test(name=f"test_rv32i_{test_name}")
    async def _test(dut):
        await start_clock(dut)
        imem_path, dmem_path = generate_mem_for_elf(elf)
        await reset_and_reload_memories(dut, imem_path, dmem_path)
        await apply_reset(dut)
        result = await monitor_tohost(dut, elf, max_cycles=MAX_CYCLES)
        assert result == "pass", ...

    return _test


for _name in _RV32I_TESTS:
    globals()[f"test_rv32i_{_name}"] = _make_test(_name)
```

Every test follows the same four steps: `start_clock` → `generate_mem_for_elf`
→ `reset_and_reload_memories` → `apply_reset` → `monitor_tohost`. The memories
are reloaded per test because the DUT keeps its contents between coroutines.

---

## Consequences

- `make verify-common` runs the ISA suite on `top_single_cycle`; the same
  sources with `TOPLEVEL=top_pipeline` run it on the pipeline.
- The shared `common.mk` means a change in memory depth, memory image or
  simulator flags happens once, not once per layer.
- `rtl/shared/mem_config.vh` is owned by the synthesis flow; simulation
  overrides it from the command line, so the two never fight over the file.
- There is no pytest-based parametrization. Adding a riscv-test means adding its
  name to the list at the top of the corresponding module.
- `single_cycle/test/` is on `PYTHONPATH` together with `../common`, which is
  how `test_cpi_one` reaches `tohost` and `conftest` (ADR 032).
