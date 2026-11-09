#!/usr/bin/env python3
"""Interactive hardware measurement on the DE1-SoC.

Automates everything that can be automated (memory images, synthesis,
programming) and only asks the user for the two values that must be read
from the VGA console: CyclesToPass and InstrToPass.

SignalTap II cannot be built with Quartus Prime 25.1 (see ADR 042), so the
counters are read from the visualisation module instead.

Modes:

  Single program:
    python3 scripts/hardware_measure.py --arch pipeline \
        --elf build/synthetic/raw_stress.elf

  Batch: measure every available program for one architecture, one command,
  pausing after each FPGA program load so you can read the VGA console:
    python3 scripts/hardware_measure.py --arch pipeline --all

  Both architectures in a row, synthetic programs and CoreMark:
    python3 scripts/hardware_measure.py --all-both

  Force re-measurement even when the saved CSV is current:
    FORCE=1 make measure-all-both

  Show what is still pending without touching the board:
    python3 scripts/hardware_measure.py --status

The result is appended to results/hardware_<arch>_<program>.csv.

A batch run skips a program when:
  * results/hardware_<arch>_<program>.csv already exists, and
  * its cycle_count / instr_retired match the cocotb reference in
    results/benchmark_<program>_<arch>.csv, or, for programs without a
    comparable reference (CoreMark runs a different iteration count on the
    board), it was measured with the current RTL and the current ELF.

Use FORCE=1 to ignore existing CSVs and measure everything from scratch.
"""

import argparse
import csv
import datetime
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from fpga_validate import _get_tohost_addr  # noqa: E402
from campaign_state import (  # noqa: E402
    file_fingerprint, load_state, mark, matches, save_state, source_fingerprint,
)

RESULTS = REPO_ROOT / "results"
VALID_ARCHS = ("single_cycle", "pipeline")
SYNTHETIC_PROGRAMS = ("raw_stress", "branch_stress", "load_use_stress", "m_ext_stress")
COREMARK = "coremark"
COREMARK_ELF = REPO_ROOT / "build" / COREMARK / f"{COREMARK}.elf"
PROGRAMS = SYNTHETIC_PROGRAMS + (COREMARK,)


def run(cmd, cwd=REPO_ROOT, extra_env=None):
    """Run a command, streaming its output."""
    print(f"  $ {' '.join(cmd)}")
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(cmd, cwd=str(cwd), env=env, text=True)
    if result.returncode != 0:
        sys.exit(f"Command failed with exit {result.returncode}: {' '.join(cmd)}")
    return result


def _parse_int(text: str) -> int:
    """Parse an integer, accepting decimal or hexadecimal (0x prefix or a-f digits)."""
    text = text.strip().replace(",", "").replace("_", "").replace(" ", "")
    if not text:
        raise ValueError("empty value")
    try:
        if text.lower().startswith("0x"):
            return int(text, 16)
        if any(c in text.lower() for c in "abcdef"):
            return int(text, 16)
        return int(text, 10)
    except ValueError:
        raise ValueError(f"not an integer: {text}")


def elf_for(program: str) -> Path:
    """Path to the program ELF, failing when it has not been built."""
    elf = (COREMARK_ELF if program == COREMARK
           else REPO_ROOT / "build" / "synthetic" / f"{program}.elf")
    if not elf.exists():
        sys.exit(f"ELF not found: {elf}  (build the benchmarks first)")
    return elf


def available_programs() -> list:
    """Programs whose ELF already exists."""
    return [program for program in PROGRAMS
            if (COREMARK_ELF if program == COREMARK
                else REPO_ROOT / "build" / "synthetic" / f"{program}.elf").exists()]


def board_connected() -> bool:
    """True when the JTAG chain shows a device behind the USB-Blaster.

    quartus_pgm --list always reports the DE-SoC USB-Blaster instance, even
    with the board switched off; jtagconfig only shows the FPGA when the
    board is actually powered and connected.
    """
    try:
        result = subprocess.run(["jtagconfig.exe"], capture_output=True,
                                text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return any(re.match(r"\s+[0-9A-F]{8}\s+\S", line)
               for line in result.stdout.splitlines())


def expected_values(program: str, arch: str):
    """Return the cocotb reference row if the same ELF was simulated.

    CoreMark is simulated with a reduced iteration count and measured on the
    board with the full one, so the two counters are not comparable.
    """
    if program == COREMARK:
        return None
    expected_csv = RESULTS / f"benchmark_{program}_{arch}.csv"
    if not expected_csv.exists():
        return None
    with open(expected_csv) as f:
        for row in csv.DictReader(f):
            return row
    return None


def hardware_csv_path(arch: str, program: str) -> Path:
    return RESULTS / f"hardware_{arch}_{program}_v2.csv"


def last_hardware_row(arch: str, program: str) -> dict | None:
    """Last row of the hardware CSV, if it exists."""
    path = hardware_csv_path(arch, program)
    if not path.exists():
        return None
    last = None
    with open(path) as f:
        for row in csv.DictReader(f):
            last = row
    return last


def measurement_inputs(program: str, elf: Path | None = None) -> dict:
    """Inputs a hardware measurement depends on: RTL and program."""
    return {"rtl": source_fingerprint(),
            "elf": file_fingerprint(elf or elf_for(program))}


def already_measured_ok(arch: str, program: str,
                        elf: Path | None = None) -> tuple[bool, str]:
    """True when the hardware CSV is still valid for the current RTL and ELF."""
    row = last_hardware_row(arch, program)
    if row is None:
        return False, "not measured yet"
    try:
        cycles = int(row["cycle_count"])
        instructions = int(row["instr_retired"])
    except (KeyError, ValueError):
        return False, "hardware CSV unreadable"

    inputs = measurement_inputs(program, elf)
    if (row.get("rtl_sha256") != inputs["rtl"]
            or row.get("elf_sha256") != inputs["elf"]
            or not row.get("sof_sha256")
            or row.get("counter_protocol") != "retire-inclusive-v2"):
        return False, "missing or mismatched source/program/bitstream provenance"
    if row.get("result") != "pass":
        return False, "termination recorded; functional evidence still pending"
    expected = expected_values(program, arch)
    if expected is not None:
        if (expected.get("rtl_sha256") != inputs["rtl"]
                or expected.get("elf_sha256") != inputs["elf"]):
            return False, "simulation reference has different provenance"
        if (cycles != int(expected["cycle_count"])
                or instructions != int(expected["instr_retired"])):
            return False, "hardware counters differ from the matching reference"
    return True, "source, ELF and bitstream provenance recorded"


def make_env(tohost_addr: int) -> dict:
    """Environment for make/Quartus: venv Python first, TOTHOST_ADDR across WSL."""
    venv_bin = REPO_ROOT / ".venv" / "bin"
    return {
        "PATH": f"{venv_bin}:{os.environ.get('PATH', '')}",
        "TOHOST_ADDR": f"{tohost_addr:#x}",
        "WSLENV": "TOHOST_ADDR",
    }


def prepare_and_program(elf: Path, arch: str, tohost_addr: int) -> None:
    """Steps 1-3: memory images, synthesis, program the FPGA."""
    imem_mem = REPO_ROOT / "build" / "imem.mem"
    dmem_mem = REPO_ROOT / "build" / "dmem.mem"

    print("\n[1/3] Generating memory images...")
    run(["make", "mem", f"ELF={elf}", f"ARCH={arch}"], extra_env=make_env(tohost_addr))
    run([
        "python3", "scripts/gen_mem_config.py",
        "--imem", str(imem_mem.resolve()),
        "--dmem", str(dmem_mem.resolve()),
        "--relative-to", str((REPO_ROOT / "synthesis" / arch).resolve()),
        "--validate-linux-path", str(imem_mem.resolve()),
        "--validate-linux-dmem", str(dmem_mem.resolve()),
    ])

    print("\n[2/3] Synthesizing (a couple of minutes)...")
    run(["make", "build", f"ARCH={arch}"], extra_env=make_env(tohost_addr))

    print("\n[3/3] Programming the FPGA...")
    run(["make", "program-direct", f"ARCH={arch}"], extra_env=make_env(tohost_addr))


def ask_vga_values(tohost_addr: int) -> dict:
    """Steps 6-7: read VGA console values and return the CSV row dict."""
    print("\n" + "=" * 60)
    print("  READ THE VGA CONSOLE NOW")
    print("=" * 60)
    print("  1. Press KEY[0] on the DE1-SoC to release reset.")
    print("  2. Wait for HALTED = 1 (benchmark finished).")
    print(f"  3. Read CyclesToPass and InstrToPass (tohost was {tohost_addr:#x}).")
    print("=" * 60)

    cycles_raw = input("  CyclesToPass (decimal or 0xhex): ")
    instr_raw = input("  InstrToPass : (decimal or 0xhex) ")
    seconds_raw = input("  Seconds observed (optional): ").strip()
    notes = input("  Notes (optional): ").strip()

    try:
        cycles = _parse_int(cycles_raw)
        instructions = _parse_int(instr_raw)
    except ValueError:
        sys.exit("  Cycles and instructions must be integers.")
    if instructions == 0:
        sys.exit("  InstrToPass cannot be zero.")

    seconds_val = _parse_int(seconds_raw) if seconds_raw else ""
    cpi = cycles / instructions

    return {
        "cycle_count": cycles,
        "instr_retired": instructions,
        "cpi": f"{cpi:.4f}",
        "seconds": seconds_val,
        "notes": notes,
    }


def save_csv(out_csv: Path, arch: str, program: str, tohost_addr: int, values: dict, elf: Path) -> None:
    """Append one row to the hardware CSV."""
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    sof = REPO_ROOT / "synthesis" / arch / "output_files" / f"rv32im_{arch}.sof"
    sof_hash = file_fingerprint(sof)
    archive = RESULTS / "hardware_bitstreams" / f"{sof_hash}.sof"
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        shutil.copy2(sof, archive)
    row = {
        "architecture": arch,
        "program": program,
        "result": "terminated-unvalidated" if program == COREMARK else "pass",
        "cycle_count": values["cycle_count"],
        "instr_retired": values["instr_retired"],
        "cpi": values["cpi"],
        "tohost_addr": hex(tohost_addr),
        "seconds": values["seconds"],
        "source": "vga_console",
        "rtl_sha256": source_fingerprint(),
        "elf_sha256": file_fingerprint(elf),
        "sof_sha256": sof_hash,
        "counter_protocol": "retire-inclusive-v2",
        "clock_mhz": 40 if arch == "single_cycle" else 50,
        "functional_validation": "CRC pending" if program == COREMARK else "termination only",

        "date_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": values["notes"],
    }
    write_header = not out_csv.exists()
    with open(out_csv, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def compare_with_cocotb(values: dict, expected: dict | None) -> None:
    """Print the cocotb comparison if a reference exists."""
    if not expected:
        return
    exp_cycles = int(expected["cycle_count"])
    exp_instr = int(expected["instr_retired"])
    match = values["cycle_count"] == exp_cycles and values["instr_retired"] == exp_instr
    print(f"\n  Cocotb expectation: {exp_cycles} cycles / {exp_instr} instructions")
    print(f"  Match: {'YES' if match else 'NO - re-check the measurement'}")


def measure_one(program: str, arch: str, out_csv: Path | None = None,
                force: bool = False, elf: Path | None = None) -> None:
    """Measure one program on one architecture."""
    elf = elf or elf_for(program)
    if not force:
        skip, reason = already_measured_ok(arch, program, elf)
        if skip:
            print(f"\n{'─' * 60}")
            print(f"  SKIP {program.upper()} on {arch.upper()} — {reason}")
            print(f"{'─' * 60}")
            return

    tohost_addr = _get_tohost_addr(elf)
    expected = expected_values(program, arch)

    print(f"\n{'═' * 60}")
    print(f"  {program.upper()}  on  {arch.upper()}")
    print(f"{'═' * 60}")
    print(f"  ELF     : {elf.relative_to(REPO_ROOT)}")
    print(f"  tohost  : {tohost_addr:#x}")
    if expected:
        print(f"  Expected(cocotb): cycles={expected['cycle_count']}, "
              f"instr={expected['instr_retired']}, CPI={expected['cpi']}")

    prepare_and_program(elf, arch, tohost_addr)
    values = ask_vga_values(tohost_addr)

    out_csv = out_csv or hardware_csv_path(arch, program)
    save_csv(out_csv, arch, program, tohost_addr, values, elf)
    state = load_state()
    mark(state, f"hardware:{arch}:{program}", **measurement_inputs(program, elf))
    save_state(state)
    compare_with_cocotb(values, expected)

    print(f"\n  Saved to {out_csv}")
    print(f"  CPI = {values['cpi']}  ({values['cycle_count']} cycles / "
          f"{values['instr_retired']} instructions)")


def print_status() -> int:
    """Print which measurements are current and which are pending."""
    print("=" * 70)
    print("  HARDWARE MEASUREMENT STATUS (DE1-SoC, VGA console)")
    print("=" * 70)
    pending = 0
    for arch in VALID_ARCHS:
        print(f"\n--- {arch} ---")
        for program in available_programs():
            ok, reason = already_measured_ok(arch, program)
            print(f"  [{'OK' if ok else 'PENDING'}] {program:16s} {reason}")
            if not ok:
                pending += 1
                elf = COREMARK_ELF if program == COREMARK else (
                    REPO_ROOT / "build" / "synthetic" / f"{program}.elf")
                print(f"             make measure-hardware ARCH={arch} "
                      f"ELF={elf.relative_to(REPO_ROOT)}")
    print()
    print(f"  {pending} pending measurement(s).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arch", choices=VALID_ARCHS,
                    help="Target architecture (required unless --all-both)")
    ap.add_argument("--elf", type=Path,
                    help="ELF file to measure (single-program mode)")
    ap.add_argument("--program",
                    help="Program name in single-program mode (default: ELF stem)")
    ap.add_argument("--output", type=Path,
                    help="Output CSV (single-program mode)")
    ap.add_argument("--all", action="store_true",
                    help="Measure every available program for --arch, one after another")
    ap.add_argument("--all-both", action="store_true",
                    help="Measure every available program for both architectures")
    ap.add_argument("--force", action="store_true",
                    help="Re-measure everything even if the saved CSV is current")
    ap.add_argument("--status", action="store_true",
                    help="Print pending measurements and exit without touching the board")
    args = ap.parse_args()

    if args.status:
        return print_status()

    if not args.all_both and not args.arch:
        sys.exit("Error: --arch is required when not using --all-both.")

    if not board_connected():
        print("DE1-SoC not detected on the USB-Blaster. Pending measurements:")
        print_status()
        return 2

    if args.all_both:
        for arch in VALID_ARCHS:
            for program in available_programs():
                measure_one(program, arch, force=args.force)
        return 0

    if args.all:
        for program in available_programs():
            measure_one(program, args.arch, force=args.force)
        return 0

    # Single-program mode
    program = args.program
    elf = args.elf
    if elf is None:
        print(f"\nPrograms available for {args.arch}:")
        for index, name in enumerate(available_programs(), start=1):
            print(f"  {index}. {name}")
        choice = input("\nSelect a program (number): ").strip()
        try:
            index = int(choice)
            if 1 <= index <= len(available_programs()):
                program = available_programs()[index - 1]
            else:
                sys.exit("Invalid choice.")
        except ValueError:
            sys.exit("Invalid choice.")
        elf = elf_for(program)
    elif program is None:
        program = elf.stem

    out_csv = args.output or hardware_csv_path(args.arch, program)
    measure_one(program, args.arch, out_csv, force=args.force, elf=elf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
