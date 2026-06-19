"""
cocotb tests for the RV32I riscv-tests suite against the pipelined DUT.

Same test binaries as test_rv32i.py in the common/ (single-cycle) directory,
but with a different test name prefix and the pipeline top-level.
The tohost-monitor infrastructure (tohost.py) is shared between the two
test directories via PYTHONPATH in the pipeline Makefile.
"""
import cocotb

from tohost import generate_mem_for_elf, reset_and_reload_memories, monitor_tohost, REPO_ROOT
from conftest import start_clock, apply_reset

_TESTS_DIR = REPO_ROOT / "build" / "riscv-tests" / "rv32ui"
# Pipeline has a longer fill-up (5 cycles) and an extra cycle per branch
# flush, so individual tests run a bit longer than on the single-cycle.
# 200_000 cycles is well above what the longest rv32ui test (e.g., jal,
# lw, sw) needs; the longest test runs in ~1000 cycles on the pipeline.
MAX_CYCLES = 200_000

# fmt: off
_RV32I_TESTS = [
    "add",  "addi", "and",  "andi",  "auipc",
    "beq",  "bge",  "bgeu", "blt",   "bltu",  "bne",
    "jal",  "jalr",
    "lb",   "lbu",  "lh",   "lhu",   "lui",   "lw",
    "or",   "ori",
    "sb",   "sh",   "sll",  "slli",  "slt",   "slti",
    "sltiu","sltu",
    "sra",  "srai", "srl",  "srli",  "sub",   "sw",
    "xor",  "xori",
]
# fmt: on


def _make_test(test_name: str):
    elf = _TESTS_DIR / f"{test_name}.elf"

    @cocotb.test(name=f"test_pipeline_rv32i_{test_name}")
    async def _test(dut):
        if not elf.exists():
            raise FileNotFoundError(
                f"ELF not found: {elf}\n"
                f"Run 'make -C verification/riscv-tests rv32ui' first."
            )
        await start_clock(dut)
        imem_path, dmem_path = generate_mem_for_elf(elf)
        await reset_and_reload_memories(dut, imem_path, dmem_path)
        await apply_reset(dut)
        result = await monitor_tohost(dut, elf, max_cycles=MAX_CYCLES)
        assert result == "pass", (
            f"[pipeline/rv32i/{test_name}] "
            + (f"FAIL at TESTNUM={result}" if result != "timeout" else "TIMEOUT")
        )

    return _test


for _name in _RV32I_TESTS:
    globals()[f"test_pipeline_rv32i_{_name}"] = _make_test(_name)
