# verification/cocotb/single_cycle/test/test_cpi_one.py
"""
Single-cycle cycle balance: retired instructions, synchronous exceptions, and
division waits explain every measured cycle. Faulting instructions do not retire.
The riscv-tests startup executes ECALL, so its aggregate CPI need not be one.

`cycle_count` and `instr_retired` are internal signals of `top_single_cycle.sv`
(perf_counter instance, not top-level ports). They are read by hierarchy in
cocotb (Icarus). This keeps the DE1-SoC pinout unchanged; if Verilator or
another simulator is added later, these signals must be promoted to
top-level outputs.

Each case also requires functional success. A concurrent clock monitor counts
exception and division cycles independently of the performance counters.
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
from cocotb.triggers import FallingEdge, Timer

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
        counts = {'faults': 0, 'division': 0}

        async def count_nonretiring_cycles():
            while True:
                await FallingEdge(dut.clk_cpu)
                await Timer(1, unit='ns')
                if (int(dut.rst_n_cpu.value) and int(dut.fetch_valid.value)
                        and not int(dut.step_hold_effective.value)
                        and not int(dut.program_done.value)):
                    if int(dut.div_busy.value):
                        counts['division'] += 1
                    elif int(dut.trap_entry.value):
                        counts['faults'] += 1

        await start_clock(dut)
        watcher = cocotb.start_soon(count_nonretiring_cycles())
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
        watcher.cancel()

        assert cycles == instrs + counts['faults'] + counts['division'], (
            f"[cpi/{test_name}] cycle balance mismatch: "
            f"cycles={cycles}, retired={instrs}, faults={counts['faults']}, "
            f"division_waits={counts['division']}"
        )

        if not is_div:
            assert cycles - counts['faults'] == instrs, (
                f"[cpi/{test_name}] Ordinary instruction cycle balance failed: "
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
