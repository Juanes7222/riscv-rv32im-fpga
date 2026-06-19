"""
cocotb tests for the RV32M riscv-tests suite against the pipelined DUT.

Same test binaries as test_rv32m.py in the common/ (single-cycle)
directory, but with a different test name prefix and the pipeline
top-level. The pipeline's multi-cycle division stall (ADR 008)
holds the entire pipeline for 34 cycles per division, so DIV/REM
tests need a larger cycle budget.
"""
import pathlib

import cocotb

from tohost import generate_mem_for_elf, reset_and_reload_memories, monitor_tohost, REPO_ROOT
from conftest import start_clock, apply_reset

_TESTS_DIR = REPO_ROOT / "build" / "riscv-tests" / "rv32um"

# DIV stalls: CPI=34 per division instruction (ADR 008). The longest
# rv32um test (div) executes dozens of divisions → budget accordingly.
# Single-cycle: ~500K was enough. Pipeline: same budget is fine because
# the pipeline makes up for the per-instruction overhead.
MAX_CYCLES_MUL = 500_000
MAX_CYCLES_DIV = 2_000_000

_RV32M_MUL_TESTS = ["mul", "mulh", "mulhsu", "mulhu"]
_RV32M_DIV_TESTS = ["div", "divu", "rem", "remu"]


def _make_test(test_name: str, max_cycles: int):
    elf = _TESTS_DIR / f"{test_name}.elf"

    @cocotb.test(name=f"test_pipeline_rv32m_{test_name}")
    async def _test(dut):
        if not elf.exists():
            raise FileNotFoundError(
                f"ELF not found: {elf}\n"
                f"Run 'make -C verification/riscv-tests rv32um' first."
            )
        await start_clock(dut)
        imem_path, dmem_path = generate_mem_for_elf(elf)
        await reset_and_reload_memories(dut, imem_path, dmem_path)
        await apply_reset(dut)
        result = await monitor_tohost(dut, elf, max_cycles=max_cycles)
        assert result == "pass", (
            f"[pipeline/rv32m/{test_name}] "
            + (f"FAIL at TESTNUM={result}" if result != "timeout" else "TIMEOUT")
        )

    return _test


for _name in _RV32M_MUL_TESTS:
    globals()[f"test_pipeline_rv32m_{_name}"] = _make_test(_name, MAX_CYCLES_MUL)

for _name in _RV32M_DIV_TESTS:
    globals()[f"test_pipeline_rv32m_{_name}"] = _make_test(_name, MAX_CYCLES_DIV)
