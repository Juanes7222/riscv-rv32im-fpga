"""
cocotb test wrapper for the RV32MI riscv-tests suite against the
pipelined DUT. Validates the CSR / trap handling described in ADR 030
and the CSR register file extension in ADR 033.

Same test binaries and pass/fail expectations as the monocycle's
test_rv32mi.py, with a different test name prefix and the pipeline
top-level. The tohost-monitor infrastructure (tohost.py) is shared
between the two test directories via PYTHONPATH in the pipeline
Makefile.
"""
import pathlib

import cocotb

from tohost import generate_mem_for_elf, reset_and_reload_memories, monitor_tohost, REPO_ROOT
from conftest import start_clock, apply_reset

_TESTS_DIR = REPO_ROOT / "build" / "riscv-tests" / "rv32mi"

# The longest pipeline MI test runs in ~50_000 cycles. The single-cycle
# used 500_000 as a safe upper bound; the pipeline is the same.
MAX_CYCLES = 500_000

# Tests that the DUT should pass. Same list as the monocycle — the
# CSR / trap path is shared between the two implementations.
EXPECTED_PASS = [
    "breakpoint",
    "csr",
    "instret_overflow",
    "mcsr",
    "scall",
    "sh-misaligned",
    "sw-misaligned",
    "zicntr",
]

# Tests the DUT is expected to FAIL on, per ADR 030's documented
# limitations. The pipeline has the same limitations as the monocycle
# (no illegal-instruction trap, no misaligned-access trap, etc.).
EXPECTED_FAIL = [
    "illegal",
    "lh-misaligned",
    "lw-misaligned",
    "ma_addr",
    "ma_fetch",
    "sbreak",
    "shamt",
]

assert set(EXPECTED_PASS).isdisjoint(set(EXPECTED_FAIL)), (
    "EXPECTED_PASS and EXPECTED_FAIL overlap: "
    f"{set(EXPECTED_PASS) & set(EXPECTED_FAIL)}"
)


def _make_test(test_name: str, expected_outcome: str):
    elf = _TESTS_DIR / f"{test_name}.elf"

    @cocotb.test(name=f"test_pipeline_rv32mi_{test_name}")
    async def _test(dut):
        if not elf.exists():
            raise FileNotFoundError(
                f"ELF not found: {elf}\n"
                f"Run 'make -C verification/riscv-tests rv32mi' first."
            )
        await start_clock(dut)
        imem_path, dmem_path = generate_mem_for_elf(elf)
        await reset_and_reload_memories(dut, imem_path, dmem_path)
        await apply_reset(dut)
        result = await monitor_tohost(dut, elf, max_cycles=MAX_CYCLES)

        if expected_outcome == "pass":
            assert result == "pass", (
                f"[pipeline/rv32mi/{test_name}] "
                + (f"FAIL at TESTNUM={result}" if result != "timeout" else "TIMEOUT")
            )
        else:  # expected_outcome == "fail"
            if result == "pass":
                assert False, (
                    f"[pipeline/rv32mi/{test_name}] Expected to fail per ADR 030 "
                    f"but DUT passed. Move to EXPECTED_PASS if the "
                    f"limitation has been lifted."
                )
            else:
                cocotb.log.info(
                    f"[pipeline/rv32mi/{test_name}] expected-fail confirmed "
                    f"(result={result})"
                )

    return _test


for _name in EXPECTED_PASS:
    globals()[f"test_pipeline_rv32mi_{_name}"] = _make_test(_name, "pass")
for _name in EXPECTED_FAIL:
    globals()[f"test_pipeline_rv32mi_{_name}"] = _make_test(_name, "fail")
