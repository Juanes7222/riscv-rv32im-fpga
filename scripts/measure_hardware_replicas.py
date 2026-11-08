#!/usr/bin/env python3
"""Measure CoreMark on the 5 synthesis replicas of each architecture.

For each replica it prints the programming command of its .sof, waits for the
user to confirm that the FPGA was programmed, KEY[0] was pressed and the VGA
console was read, and saves the CyclesToPass and InstrToPass values.

Usage:
    python3 scripts/measure_hardware_replicas.py          # first pass: build plan and capture readings
    python3 scripts/measure_hardware_replicas.py --apply  # second pass: apply readings already noted

The result accumulates in results/results_coremark_hardware_replicas.csv.
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS = REPO_ROOT / "results"
CORE_MARK_ELF = REPO_ROOT / "build" / "coremark" / "coremark.elf"
OUT_CSV = RESULTS / "results_coremark_hardware_replicas.csv"


def replicas() -> list:
    """Return (arch, index, sof_path, fmax_mhz) for the 10 replicas."""
    out = []
    for arch in ("single_cycle", "pipeline"):
        for i in range(1, 6):
            d = RESULTS / arch / f"replica_{i}"
            sof = d / f"rv32im_{arch}.sof"
            fmax = None
            fmax_f = d / "fmax.txt"
            if fmax_f.exists():
                fmax = float(fmax_f.read_text().strip())
            out.append((arch, i, sof, fmax))
    return out


def program(sof: Path) -> bool:
    """Program the .sof on device 2 of the JTAG chain."""
    cmd = [
        "quartus_pgm.exe", "-c", "DE-SoC", "-m", "JTAG",
        f"P;{sof}@2",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = "Configuration succeeded" in r.stdout or "Configuration succeeded" in r.stderr
    if not ok:
        print(r.stdout[-500:])
        print(r.stderr[-500:])
    return ok


def load_existing() -> dict:
    """Read the already saved readings, indexed by (arch, replica)."""
    data = {}
    if not OUT_CSV.exists():
        return data
    with open(OUT_CSV) as f:
        for row in csv.DictReader(f):
            data[(row["architecture"], int(row["replica"]))] = row
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="Mark the replicas already read as completed (non-interactive mode)")
    args = ap.parse_args()

    if not CORE_MARK_ELF.exists():
        print(f"Missing {CORE_MARK_ELF}. Generate it with: make -C programs/coremark ITERATIONS=2000")
        return 1

    existing = load_existing()
    pending = []
    for arch, idx, sof, fmax in replicas():
        key = (arch, idx)
        if key in existing and existing[key].get("cycles") and existing[key].get("instr"):
            print(f"[{arch}] replica {idx}: already measured (cycles {existing[key]['cycles']}, "
                  f"instr {existing[key]['instr']})")
            continue
        if not sof.exists():
            print(f"[{arch}] replica {idx}: .sof MISSING, skipped")
            continue
        pending.append((arch, idx, sof, fmax))

    if not pending:
        print("All replicas are measured.")
        return 0

    rows = []
    for arch, idx, sof, fmax in pending:
        print(f"\n=== [{arch}] replica {idx} (Fmax {fmax} MHz) ===")
        print(f"  Program:    {CORE_MARK_ELF}")
        print(f"  Bitstream:  {sof}")
        print(f"  Command:    quartus_pgm.exe -c \"DE-SoC\" -m JTAG -o \"P;{sof}@2\"")
        print(f"  Then:       press KEY[0] to release reset")
        print(f"  Wait:       about 16-18 s until the console freezes")
        print(f"  Read:       HALTED, CyclesToPass, InstrToPass (hexadecimal)")

        if args.apply:
            # Non-interactive mode: the user had already noted the values and
            # passes them through environment variables or is prompted for them.
            cycles = input("  CyclesToPass (hex): ").strip()
            instr = input("  InstrToPass  (hex): ").strip()
            halted = input("  HALTED (0/1): ").strip() or "1"
        else:
            cycles = input("  CyclesToPass (hex): ").strip()
            instr = input("  InstrToPass  (hex): ").strip()
            halted = input("  HALTED (0/1): ").strip() or "1"

        rows.append({
            "architecture": arch,
            "replica": idx,
            "fmax_mhz": fmax,
            "halted": halted,
            "cycles": int(cycles, 16) if cycles else "",
            "instr": int(instr, 16) if instr else "",
            "cpi": (int(cycles, 16) / int(instr, 16)) if cycles and instr else "",
        })

    # Merge with the already existing rows and write
    all_rows = []
    seen = set()
    for key, row in existing.items():
        all_rows.append(row)
        seen.add(key)
    for row in rows:
        key = (row["architecture"], row["replica"])
        if key in seen:
            continue
        all_rows.append(row)
        seen.add(key)

    all_rows.sort(key=lambda r: (r["architecture"], int(r["replica"])))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        fields = ["architecture", "replica", "fmax_mhz", "halted", "cycles",
                  "instr", "cpi", "seconds_40mhz", "seconds_50mhz"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in all_rows:
            seconds = ""
            if r["cycles"]:
                arch = r["architecture"]
                clock = 40 if arch == "single_cycle" else 50
                seconds = f"{int(r['cycles']) / (clock * 1e6):.2f}"
            w.writerow({**r, "seconds_40mhz": seconds if arch == "single_cycle" else "",
                        "seconds_50mhz": seconds if arch == "pipeline" else ""})

    print(f"\nResult saved to {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
