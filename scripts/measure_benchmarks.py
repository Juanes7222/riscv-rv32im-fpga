#!/usr/bin/env python3
"""Measure the effective CPI of the benchmarks on both microarchitectures.

The measurement follows the procedure of the anteproyecto: the CPI comes from
the counters embedded in the processor, read by cocotb, and the Fmax comes
from the Quartus timing reports.  Throughput and speedup are derived from
both.

The script runs the cocotb validation test once per (architecture, program)
and merges the result with the Fmax collected in results/results_synthesis.csv.

Usage:
    python3 scripts/measure_benchmarks.py
    python3 scripts/measure_benchmarks.py --riscv-tests
    python3 scripts/measure_benchmarks.py --max-cycles 2000000
"""

import argparse
import csv
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "results"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fpga_validate import run_cocotb_validation  # noqa: E402

# The synthetic stress programs and CoreMark.  The CoreMark binary uses a
# reduced iteration count (10): the instruction mix - and therefore the CPI -
# is the same, but the run finishes in minutes instead of hours.  Build it
# with: make -C programs/coremark BUILD_DIR=../../build/coremark_iter10
# ITERATIONS=10
BENCHMARKS = [
    ("raw_stress", "build/synthetic/raw_stress.elf"),
    ("branch_stress", "build/synthetic/branch_stress.elf"),
    ("load_use_stress", "build/synthetic/load_use_stress.elf"),
    ("m_ext_stress", "build/synthetic/m_ext_stress.elf"),
    ("coremark_iter10", "build/coremark_iter10/coremark.elf"),
    ("coremark_iter1", "build/coremark_iter1/coremark.elf"),
]

ARCHES = ["single_cycle", "pipeline"]


def read_fmax(path=None) -> dict:
    """Mean Fmax per architecture, from the synthesis results.

    The default source is the file written by the synthesis stage of the
    experiment (the mean of the replicas); the legacy summary of the
    collector is used as a fallback.
    """
    if path is None:
        path = RESULTS_DIR / "results_fmax.csv"
        if not path.exists():
            path = RESULTS_DIR / "results_synthesis.csv"
    fmax = {}
    with open(path) as fp:
        for row in csv.DictReader(fp):
            if row.get("fmax_mean_mhz"):
                fmax[row["arch"]] = float(row["fmax_mean_mhz"])
    return fmax


def riscv_test_elfs() -> list:
    """The riscv-tests binaries, one row per instruction test."""
    directory = REPO_ROOT / "build" / "riscv-tests" / "rv32ui"
    return [(p.stem, str(p.relative_to(REPO_ROOT)))
            for p in sorted(directory.glob("*.elf"))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--riscv-tests", action="store_true",
                        help="Also measure every riscv-tests RV32UI binary")
    parser.add_argument("--max-cycles", type=int, default=20_000_000,
                        help="Cycle limit of the cocotb run "
                             "(default: 20000000, enough for CoreMark)")
    parser.add_argument("--output", type=pathlib.Path,
                        default=RESULTS_DIR / "results_benchmarks.csv")
    parser.add_argument("--only", nargs="+", default=None,
                        help="Measure only the named benchmarks")
    parser.add_argument("--from-csv", action="store_true",
                        help="Assemble the table from the saved per-benchmark "
                             "CSVs instead of running the simulations again")
    parser.add_argument("--fmax-csv", type=pathlib.Path, default=None,
                        help="CSV with the mean Fmax per architecture "
                             "(default: results/results_fmax.csv)")
    args = parser.parse_args()

    benchmarks = list(BENCHMARKS)
    if args.only:
        benchmarks = [b for b in benchmarks if b[0] in args.only]
    if args.riscv_tests:
        benchmarks += riscv_test_elfs()

    fmax = read_fmax(args.fmax_csv)
    rows = []

    for name, rel_path in benchmarks:
        elf_path = REPO_ROOT / rel_path
        if not elf_path.exists():
            print(f"  skip {name}: {rel_path} not found")
            continue
        for arch in ARCHES:
            csv_path = RESULTS_DIR / f"benchmark_{name}_{arch}.csv"
            if args.from_csv:
                if not csv_path.exists():
                    print(f"[{arch}] {name}: no saved CSV, skipped")
                    continue
                with open(csv_path) as fp:
                    data = next(csv.DictReader(fp))
                print(f"[{arch}] {name} (from CSV)")
            else:
                print(f"[{arch}] {name} ...", end="", flush=True)
                try:
                    data = run_cocotb_validation(elf_path, arch, csv_path,
                                                 max_cycles=args.max_cycles)
                except Exception as error:
                    print(f" FAILED ({error})")
                    continue
            cycles = int(data["cycle_count"])
            instr = int(data["instr_retired"])
            cpi = cycles / max(instr, 1)
            # A run that did not reach the tohost write leaves the counters
            # frozen at an arbitrary point: the measurement is not valid and
            # must not reach the throughput or the speedup.
            valid = data["result"] == "pass"
            throughput = fmax[arch] / cpi          # MIPS
            rows.append({
                "architecture": arch,
                "program": name,
                "result": data["result"],
                "cycle_count": cycles,
                "instr_retired": instr,
                "cpi": f"{cpi:.4f}",
                "fmax_mhz": fmax[arch],
                "throughput_mips": f"{throughput:.3f}" if valid else "",
                "note": "" if valid else f"invalid measurement: {data['result']}",
            })
            print(f" cycles={cycles} instr={instr} CPI={cpi:.4f}"
                  f"{'' if valid else ' INVALID'}")

    # Both designs must execute the same instruction stream.  A difference
    # means one of them took a different path, and its counters cannot be
    # compared with the other one.
    by_program_instr = {}
    for row in rows:
        by_program_instr.setdefault(row["program"], {})[row["architecture"]] = row
    for program, per_arch in by_program_instr.items():
        sc = per_arch.get("single_cycle")
        pipe = per_arch.get("pipeline")
        if not sc or not pipe:
            continue
        sc_instr = int(sc["instr_retired"])
        pipe_instr = int(pipe["instr_retired"])
        if sc_instr and abs(sc_instr - pipe_instr) > 0.01 * sc_instr:
            for row in (sc, pipe):
                row["result"] = "divergent"
                row["note"] = (f"instruction streams differ: "
                               f"single_cycle={sc_instr}, pipeline={pipe_instr}")

    # Speedup of the pipeline over the single-cycle, per program.
    by_program = {}
    for row in rows:
        by_program.setdefault(row["program"], {})[row["architecture"]] = row
    for program, per_arch in by_program.items():
        sc = per_arch.get("single_cycle")
        pipe = per_arch.get("pipeline")
        if not sc or not pipe:
            continue
        if sc["result"] != "pass" or pipe["result"] != "pass":
            continue
        if not sc["throughput_mips"] or not pipe["throughput_mips"]:
            continue
        speedup = float(pipe["throughput_mips"]) / float(sc["throughput_mips"])
        sc["speedup_pipeline_over_single_cycle"] = f"{speedup:.4f}"
        pipe["speedup_pipeline_over_single_cycle"] = f"{speedup:.4f}"

    fields = ["architecture", "program", "result", "cycle_count",
              "instr_retired", "cpi", "fmax_mhz", "throughput_mips",
              "speedup_pipeline_over_single_cycle", "note"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"Measurements written to: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
