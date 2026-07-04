import cocotb

from tohost import generate_mem_for_elf, reset_and_reload_memories, monitor_tohost, REPO_ROOT
from conftest import start_clock, apply_reset

_TESTS_DIR = REPO_ROOT / "build" / "riscv-tests" / "rv32ui"
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

    @cocotb.test(name=f"test_rv32i_{test_name}")   # FIX: era test_rv32m_
    async def _test(dut):
        if not elf.exists():
            raise FileNotFoundError(
                f"ELF not found: {elf}\n"
                f"Run 'make -C verification/riscv-tests all' first."
            )
        await start_clock(dut)
        imem_path, dmem_path = generate_mem_for_elf(elf)
        await reset_and_reload_memories(dut, imem_path, dmem_path)
        await apply_reset(dut)
        result = await monitor_tohost(dut, elf, max_cycles=MAX_CYCLES)  # FIX: MAX_CYCLES
        assert result == "pass", (
            f"[rv32i/{test_name}] "
            + (f"FAIL at TESTNUM={result}" if result != "timeout" else "TIMEOUT")
        )

    return _test


for _name in _RV32I_TESTS:
    globals()[f"test_rv32i_{_name}"] = _make_test(_name)