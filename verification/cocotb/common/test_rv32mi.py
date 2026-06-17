"""
cocotb test wrapper for the RV32MI riscv-tests suite (machine-mode
interrupt and trap tests). Validates the CSR / trap handling described
in ADR 030 and the CSR register file extension in ADR 033 against the
official test binaries.

Each test ELF exercises one piece of the M-mode machinery:
  - breakpoint, scall, sbreak: trap delivery on EBREAK/ECALL, mcause
    encoding, mepc capture.
  - csr, mcsr: read/write semantics of mstatus/mtvec/mepc/mcause,
    mscratch, misa, mhartid, mvendorid, marchid, mimpid, mcounteren,
    and the CSRRW/CSRRS/CSRRC ops (read-only when rs1=x0).
  - illegal: trap on illegal-instruction encoding, mcause=2.
  - ma_addr, ma_fetch: trap on misaligned memory access, mcause=0/1.
  - lw-misaligned / lh-misaligned / sh-misaligned / sw-misaligned:
    same, at the data-memory bus.
  - shamt: shift-amount decoding (rv32im only, no shamt>31).
  - zicntr: read semantics of cycle / instret CSRs (the DUT exposes
    these via perf_counters, not via the CSR file — see ADR 024).
  - instret_overflow: instret rolls over correctly.

The pmpaddr test is omitted because the DUT does not implement PMP.
The build also omits pmpaddr (see verification/riscv-tests/Makefile).

Test classification
-------------------
The DUT only implements a minimal M-mode trap path (ADR 030). Several
features that the rv32mi suite checks are documented as
"limitations" of the DUT — illegal-instruction traps, misaligned-access
traps, the EBREAK-vs-ECALL distinction, and the rv32im shamt-illegal
trap. The tests for these features are in EXPECTED_FAIL; the test
suite reports PASS for them when the DUT fails (the expected
behaviour), and reports FAIL only if the DUT unexpectedly passes
(meaning the limitation has been lifted and the test should be
re-categorised).

Tests in EXPECTED_PASS are asserted to pass against the DUT.

Test naming follows the convention established by test_rv32i.py:
`test_rv32mi_<name>`, where <name> is the riscv-tests test name.
"""
import pathlib

import cocotb

from tohost import generate_mem_for_elf, reset_and_reload_memories, monitor_tohost, REPO_ROOT
from conftest import start_clock, apply_reset

_TESTS_DIR = REPO_ROOT / "build" / "riscv-tests" / "rv32mi"

# MAX_CYCLES is higher than RV32I's 200_000 because some MI tests loop
# (e.g. illegal.S, scall.S, zicntr.S) and the boot code is longer due to
# the additional CSR setup. 500_000 is a safe upper bound.
MAX_CYCLES = 500_000

# Tests that the DUT should pass. These exercise features the DUT
# actually implements (ECALL/EBREAK trap delivery, mcause/mepc capture,
# CSR read/write, Zicntr counters).
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

# Tests that the DUT is expected to FAIL on, per the limitations
# documented in ADR 030:
#   - illegal: no illegal-instruction trap (default: ru_wr=0, PC advances).
#   - ma_addr, ma_fetch, lh-misaligned, lw-misaligned: no
#     misaligned-access trap (the data memory silently masks the
#     byte enables per ADR 021).
#   - sbreak: the DUT treats EBREAK identically to ECALL (mcause=11)
#     per ADR 030's "EBREAK (treated as ECALL)" decision. The test
#     expects mcause=3.
#   - shamt: the DUT does not trap on shamt with bit 5 set (which
#     would be a 32-bit-specific illegal encoding).
# If any of these is moved into EXPECTED_PASS, it means the
# corresponding limitation has been implemented; the cocotb test will
# then fail until EXPECTED_PASS is updated.
EXPECTED_FAIL = [
    "illegal",
    "lh-misaligned",
    "lw-misaligned",
    "ma_addr",
    "ma_fetch",
    "sbreak",
    "shamt",
]

# Sanity: every test in EXPECTED_PASS and EXPECTED_FAIL must be a
# distinct riscv-tests rv32mi binary.
assert set(EXPECTED_PASS).isdisjoint(set(EXPECTED_FAIL)), (
    "EXPECTED_PASS and EXPECTED_FAIL overlap: "
    f"{set(EXPECTED_PASS) & set(EXPECTED_FAIL)}"
)


def _make_test(test_name: str, expected_outcome: str):
    elf = _TESTS_DIR / f"{test_name}.elf"

    @cocotb.test(name=f"test_rv32mi_{test_name}")
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
                f"[rv32mi/{test_name}] "
                + (f"FAIL at TESTNUM={result}" if result != "timeout" else "TIMEOUT")
            )
        else:  # expected_outcome == "fail"
            if result == "pass":
                # The DUT has started passing a test that the design
                # does not yet claim to support. This means either
                # (a) the corresponding ADR 030 limitation has been
                #     lifted (move this test to EXPECTED_PASS), or
                # (b) something is masking the real failure (e.g. the
                #     memory is being silently corrupted by a misaligned
                #     access that should have trapped).
                assert False, (
                    f"[rv32mi/{test_name}] Expected to fail per ADR 030 "
                    f"but DUT passed. Move to EXPECTED_PASS if the "
                    f"limitation has been lifted."
                )
            else:
                cocotb.log.info(
                    f"[rv32mi/{test_name}] expected-fail confirmed "
                    f"(result={result})"
                )

    return _test


for _name in EXPECTED_PASS:
    globals()[f"test_rv32mi_{_name}"] = _make_test(_name, "pass")
for _name in EXPECTED_FAIL:
    globals()[f"test_rv32mi_{_name}"] = _make_test(_name, "fail")
