# verification/cocotb/single_cycle/test/test_cpi_one.py
"""
Single-cycle architectural invariant: cycle_count == instr_retired for every
instruction except DIV/DIVU/REM/REMU, where instr_retired < cycle_count because
each division occupies 34 cycles (1 fetch + 32 RUNNING + 1 DONE, see ADR 031).

`cycle_count` and `instr_retired` are internal signals of `top_single_cycle.sv`
(perf_counter instance, not top-level ports). They are read by hierarchy in
cocotb (Icarus). This keeps the DE1-SoC pinout unchanged; if Verilator or
another simulator is added later, these signals must be promoted to
top-level outputs.

Each test reuses the same DUT module (top_single_cycle) but gets a fresh
instance per test. The 37 RV32I tests and 8 RV32M tests are split by whether
the test binary contains a division: non-division tests assert strict
equality, division tests assert the inequality and log the effective CPI.
"""
import pathlib

import cocotb

from tohost import (
    generate_mem_for_elf,
    monitor_tohost,
    reset_and_reload_memories,
    REPO_ROOT,
)
from conftest import apply_reset, start_clock

_TESTS_DIR_I = REPO_ROOT / "build" / "riscv-tests" / "rv32ui"
_TESTS_DIR_M = REPO_ROOT / "build" / "riscv-tests" / "rv32um"
MAX_CYCLES = 500_000

# Division instructions: each one stalls the PC for 34 cycles (ADR 031),
# so the strict CPI=1 invariant does not hold for them.
_DIV_NAMES = {"div", "divu", "rem", "remu"}


def _make_cpi_test(test_name: str, elf: pathlib.Path, is_div: bool):
    @cocotb.test(name=f"test_cpi_one_{test_name}")
    async def _test(dut):
        if not elf.exists():
            raise FileNotFoundError(f"ELF not found: {elf}")
        await start_clock(dut)
        imem_path, dmem_path = generate_mem_for_elf(elf)
        await reset_and_reload_memories(dut, imem_path, dmem_path)
        await apply_reset(dut)

        result = await monitor_tohost(dut, elf, max_cycles=MAX_CYCLES)
        assert result == "pass", (
            f"[cpi/{test_name}] ISA conformance failed before CPI check: "
            + (f"TESTNUM={result}" if result != "timeout" else "TIMEOUT")
        )

        cycles = int(dut.cycle_count.value)
        instrs = int(dut.instr_retired.value)

        if not is_div:
            assert cycles == instrs, (
                f"[cpi/{test_name}] CPI != 1: "
                f"cycles={cycles}, instrs={instrs}, "
                f"ratio={cycles / max(instrs, 1):.4f}"
            )
        else:
            assert instrs > 0, f"[cpi/{test_name}] instr_retired is zero"
            assert instrs <= cycles, (
                f"[cpi/{test_name}] instr_retired > cycle_count: "
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
