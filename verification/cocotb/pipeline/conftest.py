"""
Cocotb test infrastructure for the pipelined RV32IM processor.

The pipeline takes 5 cycles to execute one instruction (IF, ID, EX, MEM,
WB). For tests that preload a single instruction and check the result,
the test code must step the clock 5 times. For programs with multiple
instructions, the test steps the clock until the program finishes (e.g.,
tohost-based finish for riscv-tests) or until the test's expected number
of cycles has elapsed.

Helpers:
  - start_clock(dut): start the cocotb Clock in the background.
  - step_clock(dut): toggle clk for one full 10 ns period.
  - reset_dut(dut, hold_cycles=2): assert reset, step `hold_cycles` cycles.

The `reset_dut` helper does NOT step after deasserting reset, so the test
can preload state (regs, imem) and then step the clock to execute the
test instruction.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

CLOCK_PERIOD_NS = 10
RESET_CYCLES    = 4


async def start_clock(dut) -> None:
    """Start the cocotb Clock coroutine. Runs in the background."""
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns").start())


async def step_clock(dut) -> None:
    """Toggle clk for one full period (10 ns)."""
    dut.clk.value = 0
    await Timer(5, unit="ns")
    dut.clk.value = 1
    await Timer(5, unit="ns")


async def reset_dut(dut, hold_cycles: int = 2) -> None:
    """Assert reset for `hold_cycles` cycles. Does NOT step after deassert."""
    dut.rst_n.value = 0
    await Timer(2, unit="ns")
    for _ in range(hold_cycles):
        await step_clock(dut)
    await Timer(2, unit="ns")
    dut.rst_n.value = 1
