#!/usr/bin/env python3
"""Measure the effective CPI of the benchmarks on both microarchitectures.

The measurement follows the procedure of the anteproyecto: the CPI comes from
the counters embedded in the processor, read by cocotb, and the Fmax comes
from the Quartus timing reports.  Throughput and speedup are derived from
both.

The script runs the cocotb validation test once per (architecture, program)
and merges the result with the Fmax collected in results/results_synthesis.csv.

A single simulation run per (architecture, program) is enough: the CPI is
deterministic in simulation, so the propagated source of variability is
the place-and-route process, which is covered by the five synthesis replicas
and propagated through their Fmax. This is a reduced simulation protocol,
not evidence of five physical executions per program.

A (program, architecture) pair whose CSV was produced from the same RTL and
the same ELF is reused instead of simulated again; use --force to re-run it.

Usage:
    python3 scripts/measure_benchmarks.py
    python3 scripts/measure_benchmarks.py --riscv-tests
    python3 scripts/measure_benchmarks.py --max-cycles 2000000
    python3 scripts/measure_benchmarks.py --force
"""

import argparse
import csv
import pathlib
import os
import subprocess
import sys

from elftools.elf.elffile import ELFFile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO_ROOT / "results"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fpga_validate import run_cocotb_validation  # noqa: E402
from campaign_state import (  # noqa: E402
    file_fingerprint, load_state, mark, matches, save_state, verification_fingerprint,
)

# Reduced CoreMark runs retain startup/finalization overhead, so the 1- and
# 10-iteration variants are measured separately. Selected variants are rebuilt
# incrementally before simulation, rather than trusting an existing ELF.
BENCHMARKS = [
    ("raw_stress", "build/synthetic/raw_stress.elf"),
    ("branch_stress", "build/synthetic/branch_stress.elf"),
    ("load_use_stress", "build/synthetic/load_use_stress.elf"),
    ("m_ext_stress", "build/synthetic/m_ext_stress.elf"),
    ("coremark_iter10", "build/coremark_iter10/coremark.elf"),
    ("coremark_iter1", "build/coremark_iter1/coremark.elf"),
]

ARCHES = ["single_cycle", "pipeline"]
COREMARK_ITERATIONS = {"coremark_iter1": 1, "coremark_iter10": 10}


def validate_coremark_elf(elf_path: pathlib.Path, iterations: int) -> None:
    """Reject obsolete ports or mismatched build parameters before simulation."""
    with elf_path.open("rb") as stream:
        elf = ELFFile(stream)
        symbols = elf.get_section_by_name(".symtab")

        def symbol(name):
            matches = symbols.get_symbol_by_name(name) if symbols else None
            if not matches:
                raise ValueError(f"{elf_path}: missing {name}; rebuild the CoreMark port")
            return matches[0]

        record = symbol("coremark_validation")
        if int(record["st_size"]) != 64:
            raise ValueError(f"{elf_path}: incompatible CoreMark CRC record")
        if int(symbol("tohost")["st_value"]) != 0x6000:
            raise ValueError(f"{elf_path}: obsolete CoreMark memory map; expected tohost=0x6000")
        if int(symbol("static_memblk")["st_size"]) != 2000:
            raise ValueError(f"{elf_path}: expected TOTAL_DATA_SIZE=2000")
        for name, expected in (("seed1_volatile", 0), ("seed2_volatile", 0),
                               ("seed3_volatile", 0x66), ("seed4_volatile", iterations)):
            seed = symbol(name)
            section = elf.get_section(seed["st_shndx"])
            offset = int(seed["st_value"]) - int(section["sh_addr"])
            contents = section.data()[offset:offset + 4]
            if len(contents) != 4 or int.from_bytes(contents, "little") != expected:
                raise ValueError(f"{elf_path}: {name} does not match {expected}")


def prepare_coremark_benchmarks(benchmarks: list) -> None:
    """Incrementally build and inspect every selected CoreMark variant."""
    for name, relative_path in benchmarks:
        if name not in COREMARK_ITERATIONS:
            continue
        elf_path = REPO_ROOT / relative_path
        iterations = COREMARK_ITERATIONS[name]
        print(f"Preparing {name}: {iterations} iterations, CRC-enabled port", flush=True)
        subprocess.run(["make", "-C", str(REPO_ROOT / "programs/coremark"),
                        f"BUILD_DIR={elf_path.parent}", f"ITERATIONS={iterations}",
                        "RUN_MODE=PERFORMANCE_RUN", "TOTAL_DATA_SIZE=2000", "all"],
                       cwd=REPO_ROOT, check=True)
        validate_coremark_elf(elf_path, iterations)


def read_fmax(path=None) -> dict:
    """Mean Fmax per architecture, from the synthesis results.

    The default source is the file the synthesis stage of the experiment
    writes (the mean of the replicas).  The legacy collector summary is only
    a fallback: it is not refreshed by the campaign and would pair the new
    CPI numbers with an old Fmax.
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
    parser.add_argument("--force", action="store_true",
                        help="Simulate every benchmark again even when its "
                             "saved CSV was produced from the same RTL and ELF")
    parser.add_argument("--fmax-csv", type=pathlib.Path, default=None,
                        help="CSV with the mean Fmax per architecture "
                             "(default: results/results_fmax.csv)")
    args = parser.parse_args()
    os.environ.setdefault("VALIDATION_REFERENCE", "1")

    benchmarks = list(BENCHMARKS)
    if args.only:
        benchmarks = [b for b in benchmarks if b[0] in args.only]
    if args.riscv_tests:
        benchmarks += riscv_test_elfs()

    if not args.from_csv:
        try:
            prepare_coremark_benchmarks(benchmarks)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            print(f"Benchmark preparation failed: {error}", file=sys.stderr)
            return 1

    fmax = read_fmax(args.fmax_csv)
    fingerprint = verification_fingerprint()
    state = load_state()
    rows = []
    failures = []

    for name, rel_path in benchmarks:
        elf_path = REPO_ROOT / rel_path
        if not elf_path.exists():
            print(f"  skip {name}: {rel_path} not found")
            continue
        elf_fingerprint = file_fingerprint(elf_path)
        for arch in ARCHES:
            csv_path = RESULTS_DIR / f"benchmark_{name}_{arch}.csv"
            key = f"benchmark:{arch}:{name}"
            inputs = {"rtl": fingerprint, "elf": elf_fingerprint,
                      "validation_protocol": "retire-inclusive-v2-reference"}
            if args.from_csv:
                if not csv_path.exists():
                    print(f"[{arch}] {name}: no saved CSV, skipped")
                    continue
                with open(csv_path) as fp:
                    data = next(csv.DictReader(fp))
                print(f"[{arch}] {name} (from CSV)")
            else:
                if csv_path.exists() and matches(state, key, **inputs):
                    reused = True
                else:
                    reused = False
                if reused and not args.force:
                    with open(csv_path) as fp:
                        data = next(csv.DictReader(fp))
                    print(f"[{arch}] {name} (unchanged, reused CSV)")
                else:
                    print(f"[{arch}] {name} ...", end="", flush=True)
                    try:
                        data = run_cocotb_validation(elf_path, arch, csv_path,
                                                     max_cycles=args.max_cycles)
                    except Exception as error:
                        print(f" FAILED ({error})")
                        failures.append((arch, name, str(error)))
                        continue
                    mark(state, key, **inputs)
                    save_state(state)
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
                **{field: data.get(field, "") for field in (
                    "rtl_sha256", "elf_sha256", "counter_protocol",
                    "coremark_functional_valid", "reference_valid", "tohost_addr")},
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
                row["throughput_mips"] = ""

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
        speedup = ((int(sc["cycle_count"]) / fmax["single_cycle"])
                   / (int(pipe["cycle_count"]) / fmax["pipeline"]))
        sc["speedup_pipeline_over_single_cycle"] = f"{speedup:.4f}"
        pipe["speedup_pipeline_over_single_cycle"] = f"{speedup:.4f}"

    fields = ["architecture", "program", "result", "cycle_count",
              "instr_retired", "cpi", "fmax_mhz", "throughput_mips",
              "speedup_pipeline_over_single_cycle", "note", "rtl_sha256", "elf_sha256",
              "counter_protocol", "coremark_functional_valid", "reference_valid", "tohost_addr"]

    # A filtered run (--only) must not erase the benchmarks it did not
    # measure: keep their rows and replace only the ones measured now.
    measured = {(arch, name) for name, _ in benchmarks for arch in ARCHES}
    previous = []
    if args.only and args.output.exists():
        with open(args.output) as fp:
            previous = [row for row in csv.DictReader(fp)
                        if (row["architecture"], row["program"]) not in measured]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(previous + rows)

    print()
    print(f"Measurements written to: {args.output}")
    return 1 if failures or any(r["result"] != "pass" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
