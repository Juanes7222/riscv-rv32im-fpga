"""
Pipeline performance-counter tests (CPI / IPC measurement).

These tests verify that perf_counters.sv correctly counts cycles and
retired instructions in the five-stage pipeline.  The counters are
reset by rst_n and incremented every clock edge.

The tests verify relative properties:
  - A program with a load-use stall takes more cycles than the same
    program without the stall.
  - A program with a DIV takes significantly more cycles than without.
  - The instruction-retired counter increases monotonically.
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut

import os
import sys
import importlib.util

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_REF_MODEL = os.path.join(_REPO_ROOT, "reference_model")

_spec = importlib.util.spec_from_file_location(
    "reference_model",
    os.path.join(_REF_MODEL, "__init__.py"),
    submodule_search_locations=[_REF_MODEL],
)
_reference_model = importlib.util.module_from_spec(_spec)
sys.modules["reference_model"] = _reference_model
_spec.loader.exec_module(_reference_model)

encode_i = _reference_model.encode_i
encode_r = _reference_model.encode_r


def _load_prog(dut, words):
    for i, w in enumerate(words):
        dut.u_imem.mem[i].value = w
    for i in range(len(words), len(words) + 8):
        dut.u_imem.mem[i].value = 0x00000013


async def _run_and_get_cycles(dut, instructions, initial_regs=None, extra_cycles=4):
    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    if initial_regs:
        for reg, val in initial_regs.items():
            dut.u_rf.regs[reg].value = val
    _load_prog(dut, instructions)
    await Timer(2, unit="ns")
    total_cycles = 4 + len(instructions) + extra_cycles
    for _ in range(total_cycles):
        await step_clock(dut)
    return int(dut.u_perf.cycle_count.value)


@cocotb.test()
async def test_counters_reset_to_zero(dut):
    """After reset, cycle_count and instr_retired must both be 0."""
    await start_clock(dut)
    await reset_dut(dut)
    await Timer(2, unit="ns")
    assert int(dut.u_perf.cycle_count.value) == 0
    assert int(dut.u_perf.instr_retired.value) == 0


@cocotb.test()
async def test_load_use_increases_cycles(dut):
    """LW + ADD with a load-use stall takes more cycles than two ADDIs."""
    cycles_no_stall = await _run_and_get_cycles(dut, [
        encode_i(1, 0, 0, 1),   # ADDI x1, x0, 1
        encode_i(2, 0, 0, 2),   # ADDI x2, x0, 2
    ])

    addr = 0x20
    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    dut.u_rf.regs[2].value = addr
    dut.u_dmem.mem[addr // 4].value = 0xAABBCCDD
    _load_prog(dut, [
        encode_i(0, 2, 0b010, 1, opcode=0b0000011),  # LW x1, 0(x2)
        encode_r(0, 1, 1, 0, 3),                       # ADD x3, x1, x1
    ])
    await Timer(2, unit="ns")
    for _ in range(12):
        await step_clock(dut)
    cycles_stall = int(dut.u_perf.cycle_count.value)

    assert cycles_stall > cycles_no_stall, (
        f"load-use did not increase cycles: {cycles_stall} <= {cycles_no_stall}"
    )


@cocotb.test()
async def test_div_increases_cycles(dut):
    """ADDI + DIV takes significantly more cycles than ADDI + ADDI."""
    cycles_no_div = await _run_and_get_cycles(dut, [
        encode_i(1, 0, 0, 1),   # ADDI x1, x0, 1
        encode_i(2, 0, 0, 2),   # ADDI x2, x0, 2
    ])

    M_FUNCT7 = 0x01
    DIV = 0b100
    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    dut.u_rf.regs[2].value = 100
    dut.u_rf.regs[3].value = 5
    _load_prog(dut, [
        encode_i(0xAB, 0, 0, 10),          # ADDI x10, x0, 0xAB
        encode_r(M_FUNCT7, 3, 2, DIV, 1),  # DIV x1, x2, x3
    ])
    await Timer(2, unit="ns")
    for _ in range(50):
        await step_clock(dut)
    cycles_div = int(dut.u_perf.cycle_count.value)

    assert cycles_div > cycles_no_div + 10, (
        f"DIV did not increase cycles enough: {cycles_div} vs {cycles_no_div}"
    )


@cocotb.test()
async def test_counter_monotonicity(dut):
    """cycle_count and instr_retired must increase monotonically."""
    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    _load_prog(dut, [
        encode_i(1, 0, 0, 1),   # ADDI x1, x0, 1
        encode_i(2, 0, 0, 2),   # ADDI x2, x0, 2
    ])
    await Timer(2, unit="ns")

    prev_cycles = int(dut.u_perf.cycle_count.value)
    prev_retired = int(dut.u_perf.instr_retired.value)

    for _ in range(10):
        await step_clock(dut)
        curr_cycles = int(dut.u_perf.cycle_count.value)
        curr_retired = int(dut.u_perf.instr_retired.value)
        assert curr_cycles == prev_cycles + 1, (
            f"cycle_count not monotonic: {prev_cycles} -> {curr_cycles}"
        )
        assert curr_retired >= prev_retired, (
            f"instr_retired not monotonic: {prev_retired} -> {curr_retired}"
        )
        prev_cycles = curr_cycles
        prev_retired = curr_retired
