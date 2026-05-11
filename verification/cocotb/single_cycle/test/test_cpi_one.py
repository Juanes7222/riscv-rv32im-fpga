# verification/cocotb/single_cycle/tests/test_cpi_one.py
"""
Single-cycle invariant: cycle_count == instr_count for all RV32I instructions
and M-extension multiplications. Division tests verify instr_count <= cycle_count.

Requires top_single_cycle to expose cycle_count and instr_count as outputs (ADR 024).
"""
import pathlib

import cocotb

from verification.cocotb.common.tohost import (
    generate_mem_for_elf,
    monitor_tohost,
    REPO_ROOT,
)
from verification.cocotb.common.tests.conftest import apply_reset

_TESTS_DIR_I = REPO_ROOT / "build" / "riscv-tests" / "rv32ui"
_TESTS_DIR_M = REPO_ROOT / "build" / "riscv-tests" / "rv32um"
MAX_CYCLES = 500_000

_DIV_NAMES = {"div", "divu", "rem", "remu"}


def _make_cpi_test(test_name: str, elf: pathlib.Path, is_div: bool):
    @cocotb.test(name=f"test_cpi_one_{test_name}")
    async def _test(dut):
        if not elf.exists():
            raise FileNotFoundError(f"ELF not found: {elf}")
        generate_mem_for_elf(elf)
        await apply_reset(dut)

        result = await monitor_tohost(dut, elf, max_cycles=MAX_CYCLES)
        assert result == "pass", (
            f"[cpi/{test_name}] ISA conformance failed before CPI check: "
            + (f"TESTNUM={result}" if result != "timeout" else "TIMEOUT")
        )

        cycles = int(dut.cycle_count.value)
        instrs = int(dut.instr_count.value)

        if not is_div:
            assert cycles == instrs, (
                f"[cpi/{test_name}] CPI != 1: "
                f"cycles={cycles}, instrs={instrs}, "
                f"ratio={cycles / max(instrs, 1):.4f}"
            )
        else:
            assert instrs > 0, f"[cpi/{test_name}] instr_count is zero"
            assert instrs <= cycles, (
                f"[cpi/{test_name}] instr_count > cycle_count: "
                f"cycles={cycles}, instrs={instrs}"
            )
            effective_cpi = cycles / instrs
            cocotb.log.info(
                f"[cpi/{test_name}] effective_cpi={effective_cpi:.2f} "
                f"(cycles={cycles}, instrs={instrs})"
            )

    return _test


_all_i = [
    "add", "addi", "and", "andi", "auipc",
    "beq", "bge", "bgeu", "blt", "bltu", "bne",
    "jal", "jalr", "lb", "lbu", "lh", "lhu", "lui", "lw",
    "or", "ori", "sb", "sh", "sll", "slli", "slt", "slti",
    "sltiu", "sltu", "sra", "srai", "srl", "srli", "sub", "sw",
    "xor", "xori",
]
_all_m = ["mul", "mulh", "mulhsu", "mulhu", "div", "divu", "rem", "remu"]

for _n in _all_i:
    globals()[f"test_cpi_one_{_n}"] = _make_cpi_test(
        _n, _TESTS_DIR_I / f"{_n}.elf", is_div=False
    )
for _n in _all_m:
    globals()[f"test_cpi_one_{_n}"] = _make_cpi_test(
        _n, _TESTS_DIR_M / f"{_n}.elf", is_div=(_n in _DIV_NAMES)
    )