"""
Standalone validation test for FPGA cross-validation.

Usage:
    cd verification/cocotb/pipeline
    make TEST=test_validation TOPLEVEL=top_pipeline TOPLEVEL_LANG=verilog SIM=icarus

    cd verification/cocotb/single_cycle
    make TEST=test_validation TOPLEVEL=top_single_cycle TOPLEVEL_LANG=verilog SIM=icarus

Environment variables:
    VALIDATION_ELF  - path to the ELF to validate (default: build/riscv-tests/rv32ui/add.elf)
    VALIDATION_CSV  - path to write validation results (default: results/validation_<arch>.csv)

This test loads the program, runs until tohost write, and logs the
performance counter values (cycle_count, instr_retired, CPI).
"""

import os
import pathlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

from tohost import (
    generate_mem_for_elf,
    reset_and_reload_memories,
    monitor_tohost,
    get_tohost_addr,
    REPO_ROOT,
    BUILD_DIR,
)

# Default: use the riscv-tests add program
_DEFAULT_ELF = REPO_ROOT / "build" / "riscv-tests" / "rv32ui" / "add.elf"


@cocotb.test()
async def test_validation(dut):
    """Run a single ELF and report performance counters."""

    # Detect architecture: pipeline exposes mem_dm_wr, single-cycle exposes dm_wr
    is_pipeline = hasattr(dut, "mem_dm_wr")
    arch = "pipeline" if is_pipeline else "single_cycle"

    # Which ELF to run
    elf_str = os.environ.get("VALIDATION_ELF", str(_DEFAULT_ELF))
    elf_path = pathlib.Path(elf_str)

    if not elf_path.exists():
        raise FileNotFoundError(f"Validation ELF not found: {elf_path}")

    # Output CSV path
    csv_path = os.environ.get(
        "VALIDATION_CSV",
        str(REPO_ROOT / "results" / f"validation_{arch}.csv"),
    )

    tohost_addr = get_tohost_addr(elf_path)
    cocotb.log.info(f"Validation architecture: {arch}")
    cocotb.log.info(f"Validation ELF:          {elf_path}")
    cocotb.log.info(f"Tohost address:          {tohost_addr:#x}")
    cocotb.log.info(f"Output CSV:              {csv_path}")

    # Start clock (use unit=, not the deprecated units=)
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Generate .mem files from ELF and reload memories
    imem_path, dmem_path = generate_mem_for_elf(elf_path)

    # Reset and reload memories into the DUT
    await reset_and_reload_memories(dut, imem_path, dmem_path)
    cocotb.log.info("Reset complete, program loaded, starting execution...")

    # Wait for tohost write or timeout.
    # MAX_CYCLES env var overrides default (200k) - needed for CoreMark.
    max_cycles = int(os.environ.get("VALIDATION_MAX_CYCLES", 200_000))
    result = await monitor_tohost(dut, elf_path, max_cycles=max_cycles)

    # Read counters AFTER the tohost write (give the pipeline one extra cycle)
    await RisingEdge(dut.clk)
    cycle_count = int(dut.u_perf.cycle_count.value)
    instr_retired = int(dut.u_perf.instr_retired.value)
    cpi = cycle_count / max(instr_retired, 1)

    cocotb.log.info("=== Validation Results ===")
    cocotb.log.info(f"  Architecture:    {arch}")
    cocotb.log.info(f"  Program:         {elf_path.name}")
    cocotb.log.info(f"  Result:          {result}")
    cocotb.log.info(f"  cycle_count:     {cycle_count}")
    cocotb.log.info(f"  instr_retired:   {instr_retired}")
    cocotb.log.info(f"  CPI:             {cpi:.4f}")
    cocotb.log.info(f"  tohost_addr:     {tohost_addr:#x}")

    # Write CSV
    csv_dir = pathlib.Path(csv_path).parent
    csv_dir.mkdir(parents=True, exist_ok=True)

    with open(csv_path, "w") as f:
        f.write("architecture,program,result,cycle_count,instr_retired,cpi,tohost_addr\n")
        f.write(
            f"{arch},{elf_path.name},{result},{cycle_count},{instr_retired},{cpi:.4f},{tohost_addr:#x}\n"
        )

    cocotb.log.info(f"Results written to: {csv_path}")

    # Test must pass
    if result not in ("pass", "expected-fail-acknowledged"):
        raise AssertionError(f"Validation failed: {result}")
