"""
Cocotb test infrastructure for the pipelined RV32IM processor.

The pipeline takes 5 cycles to execute one instruction (IF, ID, EX,
MEM, WB). The IMEM provides combinational read output so IF/ID captures
the current value at posedge. For tests that preload a single instruction
and check the result, the test code must step the clock 5 times.

Two clock/reset patterns are provided:
  - **Manual clock driver** (step_clock, reset_dut): used by the
    instruction-level smoke tests where exact timing matters.
  - **Cocotb Clock + RisingEdge** (start_clock, apply_reset): used by
    the riscv-tests where the test waits for the program to write to
    tohost. The cocotb Clock toggles clk in the background; RisingEdge
    yields until the next rising edge.

The pipeline has more `dmem_depth` than typical for instruction-level
testing, so the IMEM_DEPTH=16384 and DMEM_DEPTH=8192 env vars in the
Makefile must match the RTL parameter (and the riscv-tests ELF's load
segments must fit in 8 KB of data memory).
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
    """Start the cocotb Clock coroutine. Runs in the background."""
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns").start())


async def apply_reset(dut) -> None:
    """Assert active-low reset for RESET_CYCLES cycles, then deassert.

    Used by the riscv-tests. Uses RisingEdge so the test waits for the
    cocotb Clock to actually toggle."""
    dut.rst_n.value = 0
    for _ in range(RESET_CYCLES):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


# ──────────────────────────────────────────────────────────────────────
# Manual clock driver (instruction-level tests)
# ──────────────────────────────────────────────────────────────────────

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
