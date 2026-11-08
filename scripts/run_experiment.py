#!/usr/bin/env python3
"""Run the whole experimental campaign of the RV32IM thesis with one command.

Stages, in order:

  preflight   check the toolchain, the benchmark images and the Quartus projects
  synthesis   five synthesis replicas per architecture, with Fmax and resources
  verify      the cocotb suites of both architectures
  benchmarks  the effective CPI of every program on both architectures
  artifacts   statistics, LaTeX tables, figures, protocol docs, results chapter
  hardware    measure the pending programs on the board (asks for the VGA
              console values)

Every stage is resumable: a synthesis replica whose fingerprint does not match
the current RTL is regenerated, the cocotb suites are skipped when the RTL and
the tests did not change, each benchmark is reused when its CSV came from the
same RTL and ELF, and the hardware stage only asks for the measurements that
are still pending.

Usage:
    python3 scripts/run_experiment.py                     # every stage but hardware
    python3 scripts/run_experiment.py --stages verify,artifacts
    python3 scripts/run_experiment.py --stages hardware --arch pipeline
    python3 scripts/run_experiment.py --force             # redo everything
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from thesis_artifacts import (  # noqa: E402
    collect_replicas, replica_stats, write_fmax_csv,
)
from campaign_state import (  # noqa: E402
    FINGERPRINT_VERSION, load_state, mark, matches, save_state,
    source_fingerprint, verification_fingerprint,
)

VENV_BIN = REPO_ROOT / ".venv" / "bin"
RESULTS = REPO_ROOT / "results"
BUILD = REPO_ROOT / "build"
ARCHES = ["single_cycle", "pipeline"]
PROJECT = {"single_cycle": "rv32im_single_cycle", "pipeline": "rv32im_pipeline"}

HARDWARE_PROGRAMS = [
    ("raw_stress", BUILD / "synthetic/raw_stress.elf"),
    ("load_use_stress", BUILD / "synthetic/load_use_stress.elf"),
    ("branch_stress", BUILD / "synthetic/branch_stress.elf"),
    ("m_ext_stress", BUILD / "synthetic/m_ext_stress.elf"),
]

ALL_STAGES = ["preflight", "synthesis", "verify", "benchmarks", "artifacts", "hardware"]

VERIFY_RESULTS = [
    REPO_ROOT / "verification" / "cocotb" / "common" / "results.xml",
    REPO_ROOT / "verification" / "cocotb" / "single_cycle" / "results.xml",
    REPO_ROOT / "verification" / "cocotb" / "pipeline" / "results.xml",
]


def venv_env() -> dict:
    """Environment with the project virtualenv first in the PATH.

    cocotb-config and the cocotb packages live in the virtualenv; without it
    the simulation makefiles cannot find the simulator includes.
    """
    env = os.environ.copy()
    env["PATH"] = f"{VENV_BIN}{os.pathsep}{env.get('PATH', '')}"
    return env


def run(cmd, cwd=REPO_ROOT, env=None, check=True, quiet=False) -> int:
    """Run a command, showing its output."""
    printable = " ".join(str(part) for part in cmd)
    if not quiet:
        print(f"  $ {printable}")
    result = subprocess.run([str(part) for part in cmd], cwd=cwd,
                            env=env or venv_env())
    if check and result.returncode != 0:
        raise SystemExit(f"Command failed ({result.returncode}): {printable}")
    return result.returncode


def git(*args) -> str:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT,
                            capture_output=True, text=True)
    return result.stdout.strip()


def banner(text: str) -> None:
    print()
    print("=" * 70)
    print(text)
    print("=" * 70)


# --------------------------------------------------------------------------
# Stage: preflight
# --------------------------------------------------------------------------

def stage_preflight(args) -> int:
    banner("PREFLIGHT - tools, images and projects")
    problems = []

    def check(name, path, kind="file"):
        ok = path.exists()
        print(f"  [{'ok' if ok else 'MISSING'}] {name}: {path}")
        if not ok:
            problems.append(name)
        return ok

    python = VENV_BIN / "python3"
    if check("venv interpreter", python):
        result = subprocess.run([str(python), "-c",
                                 "import cocotb; print(cocotb.__version__)"],
                                capture_output=True, text=True)
        version = result.stdout.strip() or result.stderr.strip()
        print(f"         cocotb {version}")
        if result.returncode != 0:
            problems.append("cocotb")

    for name, command in (("iverilog", ["iverilog", "-V"]),
                          ("riscv-none-elf-gcc", ["riscv-none-elf-gcc", "--version"]),
                          ("quartus_sh", ["quartus_sh.exe", "--version"])):
        result = subprocess.run(command, capture_output=True, text=True)
        first = (result.stdout or result.stderr).strip().splitlines()
        print(f"  [{'ok' if first else 'MISSING'}] {name}: "
              f"{first[0] if first else 'not found'}")

    for arch in ARCHES:
        check(f"Quartus project ({arch})",
              REPO_ROOT / "synthesis" / arch / f"{PROJECT[arch]}.qpf")
    check("instruction image", BUILD / "imem.mem")
    check("data image", BUILD / "dmem.mem")

    for name, elf in HARDWARE_PROGRAMS:
        check(f"program {name}", elf)
    coremark = BUILD / "coremark_iter10" / "coremark.elf"
    check("CoreMark (10 iterations)", coremark)

    if problems:
        print(f"\nMissing: {', '.join(problems)}")
        return 1
    print("\nPreflight OK.")
    return 0


# --------------------------------------------------------------------------
# Stage: synthesis
# --------------------------------------------------------------------------

def refresh_memory_artifacts() -> None:
    """Regenerate the memory header and the console image.

    Every replica must be built with the same program, otherwise the
    comparison between replicas is not homogeneous.
    """
    imem = BUILD / "imem.mem"
    dmem = BUILD / "dmem.mem"
    if not imem.exists() or not dmem.exists():
        raise SystemExit("Missing build/imem.mem or build/dmem.mem. "
                         "Generate them with: make mem ELF=<program.elf>")

    for arch in ARCHES:
        synth_dir = REPO_ROOT / "synthesis" / arch
        run([sys.executable, "scripts/gen_mem_config.py",
             "--imem", imem.resolve(), "--dmem", dmem.resolve(),
             "--relative-to", synth_dir.resolve(),
             "--validate-linux-path", imem.resolve(),
             "--validate-linux-dmem", dmem.resolve()])

    mif = REPO_ROOT / "synthesis" / "pipeline" / "screen.mif"
    if not mif.exists() or mif.stat().st_mtime < imem.stat().st_mtime:
        run(["bash", "scripts/gen_screen_artifacts.sh"])


def stage_synthesis(args) -> int:
    banner(f"SYNTHESIS - {args.replicas} replicas per architecture")
    refresh_memory_artifacts()
    fingerprint = source_fingerprint()
    commit = git("rev-parse", "HEAD")
    print(f"  commit    : {commit}")
    print(f"  RTL hash  : {fingerprint}")

    for arch in ARCHES:
        replicas_dir = RESULTS / arch
        kept = set()
        for index in range(1, args.replicas + 1):
            replica_dir = replicas_dir / f"replica_{index}"
            if not replica_dir.exists():
                continue
            if args.force:
                print(f"  [{arch}] replica {index}: forced regeneration")
                shutil.rmtree(replica_dir)
                continue
            meta_path = replica_dir / "meta.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            if (meta.get("fingerprint_version") == FINGERPRINT_VERSION
                    and meta.get("fingerprint") == fingerprint):
                print(f"  [{arch}] replica {index}: current, kept")
                kept.add(replica_dir)
                continue
            if meta and "fingerprint_version" not in meta:
                # Version 1 hashed the generated program artifacts, so its
                # value cannot be re-derived.  Adopt the replica instead of
                # forcing a full re-synthesis; FORCE=1 or deleting the
                # directory still rebuilds it.
                meta["fingerprint_version"] = FINGERPRINT_VERSION
                meta["fingerprint"] = fingerprint
                meta_path.write_text(json.dumps(meta, indent=2) + "\n")
                print(f"  [{arch}] replica {index}: legacy metadata adopted, kept")
                kept.add(replica_dir)
                continue
            if args.keep_stale:
                print(f"  [{arch}] replica {index}: stale, kept "
                      f"({replica_dir})")
                kept.add(replica_dir)
                continue
            print(f"  [{arch}] replica {index}: stale, regenerated")
            shutil.rmtree(replica_dir)

        for index in range(1, args.replicas + 1):
            replica_dir = replicas_dir / f"replica_{index}"
            if replica_dir in kept:
                # A kept replica keeps its own metadata: it does not come
                # from the current RTL.
                continue
            # One replica per call, so that a crash of the tool is retried
            # by the Makefile and the metadata is written as soon as the
            # replica exists.
            run(["make", "replica", f"ARCH={arch}", f"REPLICA={index}"])
            fmax = None
            fmax_file = replica_dir / "fmax.txt"
            if fmax_file.exists():
                fmax = float(fmax_file.read_text().strip())
            meta = {
                "git_commit": commit,
                "fingerprint_version": FINGERPRINT_VERSION,
                "fingerprint": fingerprint,
                "seed": index,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "fmax_mhz": fmax,
            }
            (replica_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
            print(f"  [{arch}] replica {index}: Fmax {fmax} MHz")
    return 0


# --------------------------------------------------------------------------
# Stage: verify
# --------------------------------------------------------------------------

def stage_verify(args) -> int:
    banner("VERIFY - cocotb suites of both architectures")
    fingerprint = verification_fingerprint()
    state = load_state()
    if (not args.force and all(path.exists() for path in VERIFY_RESULTS)
            and matches(state, "verify", sources=fingerprint)):
        print("  RTL and tests unchanged since the last successful run; skipped.")
        return 0
    # The common suite is run with the single-cycle top level.  Running it
    # with the pipeline top level would overwrite common/results.xml with
    # pipeline data and corrupt the single-cycle verification table.
    run(["make", "verify-common", "ARCH=single_cycle"])
    run(["make", "verify", "ARCH=single_cycle"])
    run(["make", "verify", "ARCH=pipeline"])
    mark(state, "verify", sources=fingerprint)
    save_state(state)
    return 0


# --------------------------------------------------------------------------
# Stage: benchmarks
# --------------------------------------------------------------------------

def stage_benchmarks(args) -> int:
    banner("BENCHMARKS - effective CPI per program and architecture")
    stats = replica_stats(collect_replicas())
    fmax_csv = write_fmax_csv(stats)
    print(f"  Replica Fmax -> {fmax_csv.relative_to(REPO_ROOT)}")
    cmd = [sys.executable, "scripts/measure_benchmarks.py",
           "--fmax-csv", fmax_csv, "--output", RESULTS / "results_benchmarks.csv"]
    if args.benchmarks_from_csv:
        cmd.append("--from-csv")
    if args.force:
        cmd.append("--force")
    run(cmd)
    return 0


# --------------------------------------------------------------------------
# Stage: artifacts
# --------------------------------------------------------------------------

def stage_artifacts(args) -> int:
    banner("ARTIFACTS - statistics, tables, figures and protocol docs")
    # The collector refreshes the summary report and the CSV of the
    # verification results; the thesis artifacts read the same data.
    run([sys.executable, "scripts/collect_results.py", "--markdown", "--latex", "--csv"])
    run([sys.executable, "scripts/thesis_artifacts.py"])
    return 0


# --------------------------------------------------------------------------
# Stage: hardware
# --------------------------------------------------------------------------

def stage_hardware(args) -> int:
    banner("HARDWARE - pending measurements on the DE1-SoC")
    cmd = [sys.executable, "scripts/hardware_measure.py"]
    if len(args.arch) == 1:
        cmd += ["--arch", args.arch[0], "--all"]
    else:
        cmd.append("--all-both")
    if args.force:
        cmd.append("--force")
    return run(cmd, check=False)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stages", nargs="+", default=None,
                        choices=ALL_STAGES,
                        help="stages to run (default: all but hardware)")
    parser.add_argument("--replicas", type=int, default=5,
                        help="synthesis replicas per architecture (default: 5)")
    parser.add_argument("--arch", nargs="+", default=ARCHES, choices=ARCHES,
                        help="architectures of the hardware stage")
    parser.add_argument("--keep-stale", action="store_true",
                        help="keep the replicas that do not match the current RTL")
    parser.add_argument("--benchmarks-from-csv", action="store_true",
                        help="assemble the benchmark table from the saved CSVs")
    parser.add_argument("--force", action="store_true",
                        help="ignore the saved state and redo every stage")
    args = parser.parse_args()

    stages = args.stages or [stage for stage in ALL_STAGES if stage != "hardware"]
    handlers = {
        "preflight": stage_preflight,
        "synthesis": stage_synthesis,
        "verify": stage_verify,
        "benchmarks": stage_benchmarks,
        "artifacts": stage_artifacts,
        "hardware": stage_hardware,
    }

    for stage in stages:
        code = handlers[stage](args)
        if code != 0:
            return code
    banner("STAGE FINISHED - review the artifacts under results/ and thesis/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
