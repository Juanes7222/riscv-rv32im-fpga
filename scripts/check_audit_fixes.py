#!/usr/bin/env python3
"""Run differential benchmark checks without overwriting historical results."""

import json
import os
import subprocess
from pathlib import Path

from elftools.elf.elffile import ELFFile

from fpga_validate import run_cocotb_validation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/audit_checks"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ["VALIDATION_REFERENCE"] = "1"
    os.environ["IMEM_DEPTH"] = "4096"
    os.environ["DMEM_DEPTH"] = "1024"
    subprocess.run(["make", "-C", "programs/synthetic"], cwd=ROOT, check=True)
    subprocess.run(["make", "-C", "programs/coremark",
                    "BUILD_DIR=../../build/audit_coremark_iter1", "ITERATIONS=1"],
                   cwd=ROOT, check=True)
    regression = OUT / "retirement_window.elf"
    subprocess.run(["riscv-none-elf-gcc", "-march=rv32im", "-mabi=ilp32",
                    "-nostdlib", "-T", "programs/synthetic/link.ld", "-o",
                    str(regression),
                    "verification/cocotb/common/retirement_window.S"],
                   cwd=ROOT, check=True)
    programs = [(name, ROOT / f"build/synthetic/{name}.elf") for name in
                ("raw_stress", "branch_stress", "load_use_stress", "m_ext_stress")]
    programs += [("retirement_window", regression),
                 ("coremark_iter1", ROOT / "build/audit_coremark_iter1/coremark.elf")]
    results = []
    for name, elf in programs:
        for arch in ("single_cycle", "pipeline"):
            row = run_cocotb_validation(elf, arch, OUT / f"{name}_{arch}.csv",
                                       max_cycles=1_000_000)
            if row["result"] != "pass" or row["reference_valid"] != "True":
                raise SystemExit(f"Validation failed: {name}/{arch}: {row}")
            results.append(row)
            print(f"PASS {name}/{arch}: {row['cycle_count']} cycles, "
                  f"{row['instr_retired']} instructions", flush=True)
    (OUT / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    # Corrupt an expected CRC in a separate ELF: termination must become failure.
    original = ROOT / "build/audit_coremark_iter1/coremark.elf"
    broken = OUT / "coremark_bad_crc.elf"
    data = bytearray(original.read_bytes())
    with original.open("rb") as stream:
        elf = ELFFile(stream)
        symbol = elf.get_section_by_name(".symtab").get_symbol_by_name("list_known_crc")[0]
        section = elf.get_section(symbol["st_shndx"])
        offset = section["sh_offset"] + symbol["st_value"] - section["sh_addr"] + 6
    data[offset] ^= 1
    broken.write_bytes(data)
    for arch in ("single_cycle", "pipeline"):
        csv_path = OUT / f"bad_crc_{arch}.csv"
        try:
            run_cocotb_validation(broken, arch, csv_path, max_cycles=1_000_000)
        except RuntimeError:
            evidence = json.loads(Path(str(csv_path) + ".evidence.json").read_text())
            assert evidence["measurement"]["result"] == "crc-fail"
            assert evidence["coremark"]["errors"] > 0
            print(f"PASS bad_crc/{arch}: corrupted CRC rejected", flush=True)
        else:
            raise AssertionError(f"Corrupted CoreMark accepted on {arch}")


if __name__ == "__main__":
    main()
