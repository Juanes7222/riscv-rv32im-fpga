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

import csv
import hashlib
import json
import os
import pathlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly

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

    trace = None
    if is_pipeline and os.environ.get("VALIDATION_LOCKSTEP", "0") == "1":
        from benchmark_evidence import check_pipeline_retirement
        trace = cocotb.start_soon(check_pipeline_retirement(
            dut, imem_path, dmem_path, tohost_addr))

    # Wait for tohost write or timeout.
    # MAX_CYCLES env var overrides default (200k) - needed for CoreMark.
    max_cycles = int(os.environ.get("VALIDATION_MAX_CYCLES", 200_000))
    result = await monitor_tohost(dut, elf_path, max_cycles=max_cycles)

    # MEM detects the store before its WB retirement. Sample settled flops.
    for _ in range(128):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(dut.u_perf.program_done_synced.value):
            break
    else:
        raise AssertionError("Completion store did not retire within 128 cycles")
    cycle_count = int(dut.u_perf.cycle_count.value)
    instr_retired = int(dut.u_perf.instr_retired.value)
    cycles_at_done = int(dut.u_perf.cycles_at_done.value)
    instr_at_done = int(dut.u_perf.instr_at_done.value)
    cpi = cycle_count / max(instr_retired, 1)

    from benchmark_evidence import validate_coremark, compare_reference_model
    evidence = validate_coremark(dut, elf_path)
    cocotb.log.info(f"Functional evidence: {evidence}")
    if evidence and not evidence["functional_valid"]:
        result = "crc-fail"
    differential = None
    if os.environ.get("VALIDATION_REFERENCE", "0") == "1":
        differential = compare_reference_model(
            dut, imem_path, dmem_path, tohost_addr, max_cycles, instr_retired)
    if trace is not None:
        await trace

    cocotb.log.info("=== Validation Results ===")
    cocotb.log.info(f"  Architecture:    {arch}")
    cocotb.log.info(f"  Program:         {elf_path.name}")
    cocotb.log.info(f"  Result:          {result}")
    cocotb.log.info(f"  cycle_count:     {cycle_count}")
    cocotb.log.info(f"  instr_retired:   {instr_retired}")
    cocotb.log.info(f"  CPI:             {cpi:.4f}")
    cocotb.log.info(f"  cycles_at_done:  {cycles_at_done}")
    cocotb.log.info(f"  instr_at_done:   {instr_at_done}")
    cocotb.log.info(f"  tohost_addr:     {tohost_addr:#x}")

    # Write CSV
    csv_dir = pathlib.Path(csv_path).parent
    csv_dir.mkdir(parents=True, exist_ok=True)

    from campaign_state import source_fingerprint
    record = {
        "architecture": arch, "program": elf_path.name, "result": result,
        "cycle_count": cycle_count, "instr_retired": instr_retired,
        "cpi": f"{cpi:.8f}", "tohost_addr": hex(tohost_addr),
        "counter_protocol": "retire-inclusive-v2",
        "elf_sha256": hashlib.sha256(elf_path.read_bytes()).hexdigest(),
        "rtl_sha256": source_fingerprint(),
        "coremark_functional_valid": evidence["functional_valid"] if evidence else "",
        "reference_valid": differential is not None,
    }
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(record))
        writer.writeheader()
        writer.writerow(record)
    pathlib.Path(str(csv_path) + ".evidence.json").write_text(
        json.dumps({"measurement": record, "coremark": evidence,
                    "reference": differential}, indent=2) + "\n")

    cocotb.log.info(f"Results written to: {csv_path}")

    # The on-board counters must agree with the simulated ones.  They are
    # only frozen when the program writes to the tohost address the RTL
    # watches, so the check applies to the programs that use it: CoreMark
    # signals the end of the run through its own tohost address.
    rtl_tohost_addr = int(os.environ.get("VALIDATION_TOHOST_ADDR", "0x708"), 0)
    if tohost_addr != rtl_tohost_addr:
        cocotb.log.warning(
            f"Program tohost is {tohost_addr:#x} but the RTL freezes the counters "
            f"at {rtl_tohost_addr:#x}: the frozen counters of this program are "
            "not comparable with the simulation")
    else:
        assert cycles_at_done == cycle_count, (
            f"cycles_at_done ({cycles_at_done}) != cycle_count ({cycle_count})")
        assert instr_at_done == instr_retired, (
            f"instr_at_done ({instr_at_done}) != instr_retired ({instr_retired})")

    # Test must pass
    if result not in ("pass", "expected-fail-acknowledged"):
        raise AssertionError(f"Validation failed: {result}")
