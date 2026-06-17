"""
Cocotb test infrastructure shared by all test files in this directory.

Two clock/reset patterns are provided:

  - **Cocotb Clock + RisingEdge pattern** (`start_clock`, `apply_reset`):
    used by the riscv-tests-based tests (test_rv32i, test_rv32m, test_rv32mi)
    which wait for a `tohost` write via `monitor_tohost`. The cocotb Clock
    coroutine toggles the clock; the test code `await`s rising edges.

  - **Manual clock driver pattern** (`step_clock`, `reset_dut`): used by
    the instruction-level tests (test_alu_rv32i, test_branch, ...) which
    deposit initial register state and a single instruction into memory
    and then step the clock once. The cocotb Clock is also started via
    `start_clock` (the framework needs it), but the manual toggles win
    because the test coroutine runs after the Clock coroutine yields on
    every Timer. See ADR 034 for the full rationale.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

CLOCK_PERIOD_NS = 10
RESET_CYCLES    = 4


# ──────────────────────────────────────────────────────────────────────
# Cocotb Clock + RisingEdge pattern (riscv-tests)
# ──────────────────────────────────────────────────────────────────────

async def start_clock(dut) -> None:
    """Start clock only if not already running (safe for multi-test sessions)."""
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns").start())


async def apply_reset(dut) -> None:
    """Assert reset for RESET_CYCLES cycles using RisingEdge. Used by the
    riscv-tests-based tests that rely on the cocotb Clock to advance time."""
    dut.rst_n.value = 0
    for _ in range(RESET_CYCLES):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


# ──────────────────────────────────────────────────────────────────────
# Manual clock driver (instruction-level tests)
# ──────────────────────────────────────────────────────────────────────

async def step_clock(dut) -> None:
    """Toggle clk for one full period (10 ns). The DUT samples its
    inputs on the rising edge (the second half of this function)."""
    dut.clk.value = 0
    await Timer(5, unit="ns")
    dut.clk.value = 1
    await Timer(5, unit="ns")


async def reset_dut(dut, hold_cycles: int = 2) -> None:
    """Assert reset and hold for `hold_cycles` clock cycles, then deassert.

    Does NOT step the clock after deasserting reset. The test must do that
    itself, AFTER setting up the state, so that the test instruction is
    at PC=0 when the DUT exits reset (see ADR 034 for the full rationale)."""
    dut.rst_n.value = 0
    await Timer(2, unit="ns")
    for _ in range(hold_cycles):
        await step_clock(dut)
    await Timer(2, unit="ns")
    dut.rst_n.value = 1
