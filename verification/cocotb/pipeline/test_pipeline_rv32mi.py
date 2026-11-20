"""All selected machine-mode programs must finish successfully.

Former expected failures remain in the gate as real functional requirements.
Passing this selection does not prove complete privileged-ISA conformance.
"""
import cocotb
from tohost import generate_mem_for_elf, reset_and_reload_memories, monitor_tohost, REPO_ROOT
from conftest import start_clock, apply_reset

TESTS = ['breakpoint', 'csr', 'instret_overflow', 'scall', 'sh-misaligned', 'sw-misaligned', 'zicntr', 'illegal', 'lh-misaligned', 'lw-misaligned', 'ma_addr', 'ma_fetch', 'mcsr', 'sbreak', 'shamt']
MAX_CYCLES = 500_000


def _make_test(test_name):
    elf = REPO_ROOT / "build/riscv-tests/rv32mi" / (test_name + ".elf")

    @cocotb.test(name="test_pipeline_rv32mi_" + test_name)
    async def _test(dut):
        assert elf.is_file(), str(elf)
        await start_clock(dut)
        imem, dmem = generate_mem_for_elf(elf)
        await reset_and_reload_memories(dut, imem, dmem)
        await apply_reset(dut)
        result = await monitor_tohost(dut, elf, max_cycles=MAX_CYCLES)
        assert result == "pass", f"{test_name}: {result}"
    return _test


for _name in TESTS:
    globals()["test_pipeline_rv32mi_" + _name] = _make_test(_name)
