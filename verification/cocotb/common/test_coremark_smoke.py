"""
CoreMark smoke test: verify program starts and executes without crashing.
Runs for a limited number of cycles (not full benchmark completion).
"""

import os
import pathlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tohost import (
    generate_mem_for_elf,
    reset_and_reload_memories,
    REPO_ROOT,
    BUILD_DIR,
)

# Which ELF to load
_DEFAULT_ELF = REPO_ROOT / "build" / "coremark" / "coremark.elf"

# Number of cycles to run
SMOKE_CYCLES = int(os.environ.get("SMOKE_CYCLES", 2000))


@cocotb.test()
async def test_coremark_smoke(dut):
    """Load CoreMark, run SMOKE_CYCLES, verify PC advances and no crash."""

    is_pipeline = hasattr(dut, "mem_dm_wr")
    arch = "pipeline" if is_pipeline else "single_cycle"

    elf_str = os.environ.get("VALIDATION_ELF", str(_DEFAULT_ELF))
    elf_path = pathlib.Path(elf_str)
    if not elf_path.exists():
        raise FileNotFoundError(f"CoreMark ELF not found: {elf_path}")

    cocotb.log.info(f"CoreMark smoke test: architecture={arch} ELF={elf_path}")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Generate .mem files and load
    imem_path, dmem_path = generate_mem_for_elf(elf_path)
    await reset_and_reload_memories(dut, imem_path, dmem_path)

    # Run for SMOKE_CYCLES
    last_pc = 0
    pc_stuck_count = 0
    max_instr = 0
    ran_ok = True

    for cycle in range(SMOKE_CYCLES):
        await RisingEdge(dut.clk)

        # Read PC
        try:
            if is_pipeline:
                pc = int(dut.u_pcunit.pc.value)
            else:
                pc = int(dut.u_pc.pc_out.value)
        except Exception:
            pc = -1

        # Read perf counters
        try:
            cycle_count = int(dut.u_perf.cycle_count.value)
            instr_retired = int(dut.u_perf.instr_retired.value)
        except Exception:
            cycle_count = 0
            instr_retired = 0

        max_instr = max(max_instr, instr_retired)

        # Track if PC is stuck
        if pc == last_pc and pc >= 0:
            pc_stuck_count += 1
        else:
            pc_stuck_count = 0
        last_pc = pc

        # Check for PC stuck (500+ cycles same address)
        if pc_stuck_count >= 500:
            cocotb.log.warning(
                f"PC stuck at 0x{pc:08x} for {pc_stuck_count} cycles "
                f"(cycle {cycle}, instr_retired={instr_retired})"
            )

        # Check DMEM write (pipeline: mem_dm_wr, single-cycle: dm_wr)
        try:
            if is_pipeline:
                dm_wr = int(dut.mem_dm_wr.value)
                dm_addr = int(dut.mem_alu_result.value)
            else:
                dm_wr = int(dut.dm_wr.value)
                dm_addr = int(dut.dm_addr.value)
        except Exception:
            dm_wr = 0
            dm_addr = 0

        # Log first few DM writes
        if dm_wr and cycle < 10:
            if is_pipeline:
                data = int(dut.mem_rs2_data.value)
            else:
                data = int(dut.dm_wdata.value)
            cocotb.log.info(f"  DM write: addr=0x{dm_addr:x} data=0x{data:x}")

    # Summary
    cocotb.log.info("=== CoreMark Smoke Test Results ===")
    cocotb.log.info(f"  Cycles:        {SMOKE_CYCLES}")
    cocotb.log.info(f"  Instr retired: {max_instr}")
    cocotb.log.info(f"  PC stuck count: {pc_stuck_count}")
    cocotb.log.info(f"  Final PC:      0x{last_pc:x}")

    if pc_stuck_count >= 500:
        cocotb.log.error("PC was stuck — possible infinite loop")
        ran_ok = False

    assert ran_ok, "CoreMark smoke test FAILED: PC stuck or unexpected behavior"
    cocotb.log.info("CoreMark smoke test PASSED")
