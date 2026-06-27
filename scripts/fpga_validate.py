#!/usr/bin/env python3
"""
FPGA cross-validation workflow for RISC-V RV32IM.

Prepares everything needed to validate the FPGA implementation against cocotb:
  1. Generates .mem files with FPGA-compatible depths (IMEM_DEPTH=2048, DMEM_DEPTH=512).
  2. Generates mem_config.vh pointing to those files.
  3. Runs cocotb to get expected cycle_count, instr_retired.
  4. Writes a validation reference CSV.
  5. Prints step-by-step FPGA instructions.

Usage:
    # Full workflow (cocotb + FPGA prep):
    python scripts/fpga_validate.py --elf build/riscv-tests/rv32ui/add.elf

    # FPGA prep only (skip cocotb):
    python scripts/fpga_validate.py --elf build/riscv-tests/rv32ui/add.elf --fpga-only

    # Compare FPGA capture against cocotb reference:
    python scripts/fpga_validate.py --compare results/capture_pipeline.csv --arch pipeline

Outputs:
    build/fpga_validate/imem.mem, dmem.mem  — FPGA-compatible memory images
    results/validation_reference.csv         — expected values from cocotb
    results/cross_validation_pipeline.csv    — FPGA vs cocotb comparison
"""

import argparse
import csv
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_DIR = REPO_ROOT / "build" / "fpga_validate"
RESULTS_DIR = REPO_ROOT / "results"
SCRIPTS_DIR = REPO_ROOT / "scripts"
RTL_SHARED = REPO_ROOT / "rtl" / "shared"
SYNTH_PIPELINE = REPO_ROOT / "synthesis" / "pipeline"
SYNTH_SC = REPO_ROOT / "synthesis" / "single_cycle"

# FPGA synthesis defaults (must match .qsf)
IMEM_DEPTH = 2048
DMEM_DEPTH = 512

# cocotb depths (used by test infrastructure)
COCOTB_IMEM_DEPTH = 16384
COCOTB_DMEM_DEPTH = 8192


def _get_tohost_addr(elf_path: pathlib.Path) -> int:
    """Extract the tohost symbol address from an ELF."""
    from elftools.elf.elffile import ELFFile
    with open(elf_path, "rb") as f:
        elf = ELFFile(f)
        symtab = elf.get_section_by_name(".symtab")
        if symtab is None:
            raise RuntimeError(f"No .symtab in {elf_path}")
        symbols = symtab.get_symbol_by_name("tohost")
        if not symbols:
            raise RuntimeError(f"Symbol 'tohost' not found in {elf_path}")
        return symbols[0].entry["st_value"]


def generate_fpga_mem(elf_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Generate .mem files for FPGA (small depths)."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    bin_path = BUILD_DIR / "program.bin"
    imem_path = BUILD_DIR / "imem.mem"
    dmem_path = BUILD_DIR / "dmem.mem"

    # Convert ELF to raw binary
    subprocess.run(
        ["riscv-none-elf-objcopy", "-O", "binary", str(elf_path), str(bin_path)],
        check=True,
    )

    # Generate .mem files with FPGA depths
    subprocess.run(
        ["python3", str(SCRIPTS_DIR / "elf_to_mem.py"),
         str(bin_path), str(IMEM_DEPTH), str(imem_path)],
        check=True,
    )
    subprocess.run(
        ["python3", str(SCRIPTS_DIR / "elf_to_mem.py"),
         str(bin_path), str(DMEM_DEPTH), str(dmem_path)],
        check=True,
    )

    return imem_path, dmem_path


def generate_mem_config(imem_path: pathlib.Path, dmem_path: pathlib.Path,
                        relative_to: pathlib.Path) -> pathlib.Path:
    """Generate mem_config.vh with paths relative to a given directory."""
    subprocess.run(
        ["python3", str(SCRIPTS_DIR / "gen_mem_config.py"),
         "--imem", str(imem_path),
         "--dmem", str(dmem_path),
         "--relative-to", str(relative_to),
         "--validate-linux-path", str(imem_path),
         "--validate-linux-dmem", str(dmem_path)],
        check=True,
    )
    return RTL_SHARED / "mem_config.vh"


def run_cocotb_validation(elf_path: pathlib.Path, arch: str,
                          csv_path: pathlib.Path) -> dict:
    """Run the validation test in cocotb and return counter values."""
    from verification.cocotb.common.tohost import (
        generate_mem_for_elf as generate_cocotb_mem,
    )

    # Generate cocotb-compatible .mem files (large depths)
    generate_cocotb_mem(elf_path)

    verif_dir = REPO_ROOT / "verification" / "cocotb" / arch
    top = "top_pipeline" if arch == "pipeline" else "top_single_cycle"

    env = os.environ.copy()
    env["VALIDATION_ELF"] = str(elf_path)
    env["VALIDATION_CSV"] = str(csv_path)
    env["PATH"] = f"{REPO_ROOT / '.venv' / 'bin'}:{env.get('PATH', '')}"

    result = subprocess.run(
        ["make", "-C", str(verif_dir),
         "TOPLEVEL_LANG=verilog",
         "SIM=icarus",
         f"COCOTB_TEST_MODULES=test_validation",
         "TEST=test_validation",
         f"TOPLEVEL={top}"],
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        print("cocotb test failed. Checking CSV anyway...")
        print(result.stderr[-500:] if result.stderr else "")

    # Read CSV
    if csv_path.exists():
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                return dict(row)

    raise RuntimeError(f"cocotb did not produce CSV at {csv_path}")


def compare_with_fpga(fpga_csv: pathlib.Path, ref_csv: pathlib.Path,
                      output_csv: pathlib.Path) -> bool:
    """Compare FPGA capture results against cocotb reference."""
    from scripts.parse_stp_csv import parse_stp_csv, compute_cpi
    from scripts.parse_stp_csv import parse_cocotb_csv as _parse_ref

    fpga_data = parse_stp_csv(fpga_csv)
    ref_data = _parse_ref(ref_csv)

    fpga_cpi = compute_cpi(fpga_data["cycle_count"], fpga_data["instr_retired"])
    ref_cpi = compute_cpi(ref_data["cycle_count"], ref_data["instr_retired"])

    cycle_match = fpga_data["cycle_count"] == ref_data["cycle_count"]
    instr_match = fpga_data["instr_retired"] == ref_data["instr_retired"]
    all_match = cycle_match and instr_match

    print()
    print("=== Cross-Validation Results ===")
    print(f"  {'Metric':<20} {'FPGA':<12} {'Cocotb':<12} {'Match':<8}")
    print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*8}")
    print(f"  {'cycle_count':<20} {fpga_data['cycle_count']:<12} "
          f"{ref_data['cycle_count']:<12} {'✅' if cycle_match else '❌'}")
    print(f"  {'instr_retired':<20} {fpga_data['instr_retired']:<12} "
          f"{ref_data['instr_retired']:<12} {'✅' if instr_match else '❌'}")
    print(f"  {'CPI':<20} {fpga_cpi:<12.4f} {ref_cpi:<12.4f} "
          f"{'✅' if all_match else '❌'}")
    print(f"  {'Result':<20} {'':<12} {'':<12} "
          f"{'✅ PASS' if all_match else '❌ FAIL'}")

    # Write comparison CSV
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "fpga", "cocotb", "match"])
        writer.writerow(["cycle_count", fpga_data["cycle_count"],
                         ref_data["cycle_count"], str(cycle_match)])
        writer.writerow(["instr_retired", fpga_data["instr_retired"],
                         ref_data["instr_retired"], str(instr_match)])
        writer.writerow(["cpi", f"{fpga_cpi:.4f}", f"{ref_cpi:.4f}",
                         str(all_match)])
        writer.writerow(["result", "", "", "PASS" if all_match else "FAIL"])

    print(f"\nComparison written to: {output_csv}")
    return all_match


def print_fpga_instructions(elf_path: pathlib.Path, arch: str,
                            tohost_addr: int):
    """Print step-by-step FPGA validation instructions."""
    top = "top_pipeline" if arch == "pipeline" else "top_single_cycle"

    print()
    print("=" * 70)
    print(f"  FPGA VALIDATION INSTRUCTIONS — {arch.upper()}")
    print("=" * 70)
    print()
    print(f"  Program:       {elf_path.name}")
    print(f"  Architecture:  {arch}")
    print(f"  Tohost addr:   {tohost_addr:#x}")
    print(f"  TOHOST_ADDR:   {tohost_addr:#x} (default matches)")
    print()
    print("  STEP 1 — Generate .mem files and mem_config.vh for FPGA:")
    print(f"    python scripts/fpga_validate.py --elf {elf_path} --fpga-only")
    print()
    print("  STEP 2 — Build with SignalTap II:")
    print(f"    make build-fpga ARCH={arch}")
    print()
    print("  STEP 3 — Program the FPGA:")
    print(f"    make program ARCH={arch}")
    print("    (press KEY[0] to release reset after programming)")
    print()
    print("  STEP 4 — Capture SignalTap data:")
    print(f"    make capture ARCH={arch}")
    print()
    print("  STEP 5 — Cross-validate against cocotb:")
    print(f"    python scripts/fpga_validate.py \\")
    print(f"      --compare results/capture_{arch}.csv --arch {arch}")
    print()
    print("  Or in one command (after build-fpga):")
    print(f"    make build-fpga ARCH={arch} && \\")
    print(f"    make program ARCH={arch} && \\")
    print(f"    make capture ARCH={arch} && \\")
    print(f"    python scripts/fpga_validate.py --compare results/capture_{arch}.csv --arch {arch}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="FPGA cross-validation workflow for RV32IM"
    )
    parser.add_argument("--elf", type=pathlib.Path,
                        default=REPO_ROOT / "build" / "riscv-tests" / "rv32ui" / "add.elf",
                        help="Path to ELF file for validation")
    parser.add_argument("--arch", choices=["pipeline", "single_cycle"],
                        default="pipeline",
                        help="Target architecture")
    parser.add_argument("--fpga-only", action="store_true",
                        help="Only prepare FPGA files, skip cocotb")
    parser.add_argument("--compare", type=pathlib.Path, default=None,
                        help="FPGA capture CSV to compare against cocotb reference")
    parser.add_argument("--output-dir", type=pathlib.Path, default=RESULTS_DIR,
                        help="Output directory for results")
    args = parser.parse_args()

    if not args.elf.exists():
        print(f"Error: ELF not found: {args.elf}")
        sys.exit(1)

    # ---- Mode: Compare FPGA capture against cocotb reference ----
    if args.compare:
        ref_csv = args.output_dir / f"validation_reference.csv"
        if not ref_csv.exists():
            print(f"Error: Reference CSV not found at {ref_csv}")
            print("Run without --compare first to generate the reference.")
            sys.exit(1)

        output_csv = args.output_dir / f"cross_validation_{args.arch}.csv"
        success = compare_with_fpga(args.compare, ref_csv, output_csv)
        sys.exit(0 if success else 1)

    # ---- Normal mode: Prepare validation ----
    tohost_addr = _get_tohost_addr(args.elf)
    print(f"Tohost address: {tohost_addr:#x}")

    # Generate FPGA .mem files
    print("Generating FPGA-compatible .mem files...")
    imem_fpga, dmem_fpga = generate_fpga_mem(args.elf)
    print(f"  IMEM: {imem_fpga} ({imem_fpga.stat().st_size} bytes)")
    print(f"  DMEM: {dmem_fpga} ({dmem_fpga.stat().st_size} bytes)")

    # Generate mem_config.vh pointing to FPGA .mem files
    print("Generating mem_config.vh for FPGA synthesis...")
    generate_mem_config(imem_fpga, dmem_fpga, SYNTH_PIPELINE)
    print("  mem_config.vh updated for pipeline")

    # Generate single-cycle mem_config.vh too
    generate_mem_config(imem_fpga, dmem_fpga, SYNTH_SC)
    print("  mem_config.vh updated for single-cycle")

    # Run cocotb validation (unless --fpga-only)
    ref_csv = args.output_dir / "validation_reference.csv"
    cocotb_data = None

    if not args.fpga_only:
        for arch_name in ["pipeline", "single_cycle"]:
            print(f"\nRunning cocotb validation for {arch_name}...")
            try:
                data = run_cocotb_validation(args.elf, arch_name, ref_csv)
                print(f"  cycle_count={data['cycle_count']}, "
                      f"instr_retired={data['instr_retired']}, "
                      f"CPI={data['cpi']}")
                cocotb_data = data
            except Exception as e:
                print(f"  cocotb failed: {e}")
                print("  (The cocotb infrastructure must be set up)")

        # Write combined reference CSV
        if cocotb_data:
            combined = args.output_dir / "validation_reference.csv"
            combined.parent.mkdir(parents=True, exist_ok=True)
            with open(combined, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "architecture", "program", "result",
                    "cycle_count", "instr_retired", "cpi", "tohost_addr"
                ])
                # Read back individual CSVs
                for arch_name in ["pipeline", "single_cycle"]:
                    csv_file = args.output_dir / f"validation_{arch_name}.csv"
                    if csv_file.exists():
                        with open(csv_file) as cf:
                            reader = csv.DictReader(cf)
                            for row in reader:
                                writer.writerow([
                                    row["architecture"], row["program"],
                                    row["result"], row["cycle_count"],
                                    row["instr_retired"], row["cpi"],
                                    row["tohost_addr"],
                                ])
            print(f"\nCombined reference written to: {combined}")
    else:
        print("\nSkipping cocotb (--fpga-only set).")

    # Print FPGA instructions
    print_fpga_instructions(args.elf, args.arch, tohost_addr)


if __name__ == "__main__":
    main()
