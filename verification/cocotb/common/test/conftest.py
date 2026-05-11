"""
Shared pytest fixtures for common ISA conformance tests.
Provides: apply_reset
"""

import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer

CLOCK_PERIOD_NS = 10
RESET_DURATION_NS = 40


async def apply_reset(dut) -> None:
    """Assert active-low reset for RESET_DURATION_NS, then release."""
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, units="ns").start())
    dut.rstn.value = 0
    await Timer(RESET_DURATION_NS, units="ns")
    dut.rstn.value = 1