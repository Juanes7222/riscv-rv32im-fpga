import pathlib

import cocotb

from ..tohost import generate_mem_for_elf, monitor_tohost, REPO_ROOT
from .conftest import apply_reset

_TESTS_DIR = REPO_ROOT / "build" / "riscv-tests" / "rv32um"

# DIV stalls: CPI=34 per division instruction (ADR 008).
# Most rv32um tests execute dozens of division instances → budget accordingly.
MAX_CYCLES_MUL = 200_000
MAX_CYCLES_DIV = 500_000

_RV32M_MUL_TESTS = ["mul", "mulh", "mulhsu", "mulhu"]
_RV32M_DIV_TESTS = ["div", "divu", "rem", "remu"]


def _make_test(test_name: str, max_cycles: int):
    elf = _TESTS_DIR / f"{test_name}.elf"

    @cocotb.test(name=f"test_rv32m_{test_name}")
    async def _test(dut):
        if not elf.exists():
            raise FileNotFoundError(
                f"ELF not found: {elf}\n"
                f"Run 'make -C verification/riscv-tests all' first."
            )
        generate_mem_for_elf(elf)
        await apply_reset(dut)
        result = await monitor_tohost(dut, elf, max_cycles=max_cycles)
        assert result == "pass", (
            f"[rv32m/{test_name}] "
            + (f"FAIL at TESTNUM={result}" if result != "timeout" else "TIMEOUT")
        )

    return _test


for _name in _RV32M_MUL_TESTS:
    globals()[f"test_rv32m_{_name}"] = _make_test(_name, MAX_CYCLES_MUL)

for _name in _RV32M_DIV_TESTS:
    globals()[f"test_rv32m_{_name}"] = _make_test(_name, MAX_CYCLES_DIV)