import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

CLOCK_PERIOD_NS = 10
RESET_CYCLES    = 4


async def start_clock(dut) -> None:
    """Start clock only if not already running (safe for multi-test sessions)."""
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns").start())


async def apply_reset(dut) -> None:
    dut.rst_n.value = 0
    for _ in range(RESET_CYCLES):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)