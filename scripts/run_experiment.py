#!/usr/bin/env python3
"""Run the whole experimental campaign of the RV32IM thesis with one command.

Stages, in order:

  preflight   check the toolchain, the benchmark images and the Quartus projects
  synthesis   five synthesis replicas per architecture, with Fmax and resources
  verify      the cocotb suites of both architectures
  benchmarks  the effective CPI of every program on both architectures
  artifacts   statistics, LaTeX tables, figures, protocol docs, results chapter
  hardware    program the board and print the list of photographs to take

Every stage is resumable: a synthesis replica whose fingerprint does not match
the current RTL is regenerated, and the other stages simply re-run.

Usage:
    python3 scripts/run_experiment.py                     # every stage but hardware
    python3 scripts/run_experiment.py --stages verify,artifacts
    python3 scripts/run_experiment.py --stages hardware --arch pipeline
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
    collect_replicas, replica_stats, rtl_fingerprint, write_fmax_csv,
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
    banner("PREFLIGHT - herramientas, imágenes y proyectos")
    problems = []

    def check(name, path, kind="file"):
        ok = path.exists()
        print(f"  [{'ok' if ok else 'FALTA'}] {name}: {path}")
        if not ok:
            problems.append(name)
        return ok

    python = VENV_BIN / "python3"
    if check("intérprete del venv", python):
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
        print(f"  [{'ok' if first else 'FALTA'}] {name}: {first[0] if first else 'no encontrado'}")

    for arch in ARCHES:
        check(f"proyecto Quartus ({arch})", REPO_ROOT / "synthesis" / arch / f"{PROJECT[arch]}.qpf")
    check("imagen de instrucciones", BUILD / "imem.mem")
    check("imagen de datos", BUILD / "dmem.mem")

    for name, elf in HARDWARE_PROGRAMS:
        check(f"programa {name}", elf)
    coremark = BUILD / "coremark_iter10" / "coremark.elf"
    check("CoreMark (10 iteraciones)", coremark)

    if problems:
        print(f"\nFaltan: {', '.join(problems)}")
        return 1
    print("\nPreflight correcto.")
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
        raise SystemExit("Faltan build/imem.mem o build/dmem.mem. "
                         "Genere las imagenes con: make mem ELF=<programa.elf>")

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
    banner(f"SYNTHESIS - {args.replicas} replicas por arquitectura")
    refresh_memory_artifacts()
    fingerprint = rtl_fingerprint()
    commit = git("rev-parse", "HEAD")
    print(f"  commit    : {commit}")
    print(f"  huella RTL: {fingerprint}")

    for arch in ARCHES:
        replicas_dir = RESULTS / arch
        kept = set()
        for index in range(1, args.replicas + 1):
            replica_dir = replicas_dir / f"replica_{index}"
            if not replica_dir.exists():
                continue
            meta_path = replica_dir / "meta.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            if meta.get("fingerprint") == fingerprint:
                print(f"  [{arch}] réplica {index}: vigente, se conserva")
                kept.add(replica_dir)
                continue
            if args.keep_stale:
                print(f"  [{arch}] réplica {index}: obsoleta, se conserva "
                      f"({replica_dir})")
                kept.add(replica_dir)
                continue
            print(f"  [{arch}] réplica {index}: obsoleta, se regenera")
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
                "fingerprint": fingerprint,
                "seed": index,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "fmax_mhz": fmax,
            }
            (replica_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
            print(f"  [{arch}] réplica {index}: Fmax {fmax} MHz")
    return 0


# --------------------------------------------------------------------------
# Stage: verify
# --------------------------------------------------------------------------

def stage_verify(args) -> int:
    banner("VERIFY - suites cocotb de ambas arquitecturas")
    # The common suite is run with the single-cycle top level.  Running it
    # with the pipeline top level would overwrite common/results.xml with
    # pipeline data and corrupt the single-cycle verification table.
    run(["make", "verify-common", "ARCH=single_cycle"])
    run(["make", "verify", "ARCH=single_cycle"])
    run(["make", "verify", "ARCH=pipeline"])
    return 0


# --------------------------------------------------------------------------
# Stage: benchmarks
# --------------------------------------------------------------------------

def stage_benchmarks(args) -> int:
    banner("BENCHMARKS - CPI efectivo por programa y arquitectura")
    stats = replica_stats(collect_replicas())
    fmax_csv = write_fmax_csv(stats)
    print(f"  Fmax de las réplicas -> {fmax_csv.relative_to(REPO_ROOT)}")
    cmd = [sys.executable, "scripts/measure_benchmarks.py",
           "--fmax-csv", fmax_csv, "--output", RESULTS / "results_benchmarks.csv"]
    if args.benchmarks_from_csv:
        cmd.append("--from-csv")
    run(cmd)
    return 0


# --------------------------------------------------------------------------
# Stage: artifacts
# --------------------------------------------------------------------------

def stage_artifacts(args) -> int:
    banner("ARTIFACTS - tablas, figuras, protocolo y capítulo")
    # The collector refreshes the summary report and the CSV of the
    # verification results; the thesis artifacts read the same data.
    run([sys.executable, "scripts/collect_results.py", "--markdown", "--latex", "--csv"])
    run([sys.executable, "scripts/thesis_artifacts.py"])
    return 0


# --------------------------------------------------------------------------
# Stage: hardware
# --------------------------------------------------------------------------

def board_connected() -> bool:
    result = subprocess.run(["quartus_pgm.exe", "--list"], capture_output=True,
                            text=True, timeout=120)
    return "DE-SoC" in (result.stdout + result.stderr)


def stage_hardware(args) -> int:
    banner("HARDWARE - programación de la tarjeta y lista de capturas")
    if not board_connected():
        print("  No se detectó la DE1-SoC. Conecte la tarjeta y el USB-Blaster, "
              "y vuelva a ejecutar el objetivo.")
        return 1

    benchmarks = {}
    path = RESULTS / "results_benchmarks.csv"
    if path.exists():
        import csv
        with path.open() as fp:
            for row in csv.DictReader(fp):
                benchmarks[(row["architecture"], row["program"])] = row

    for arch in args.arch:
        for name, elf in HARDWARE_PROGRAMS:
            if not elf.exists():
                continue
            print(f"\n  [{arch}] {name}")
            run(["make", "flash", f"ELF={elf}", f"ARCH={arch}"])
            run([sys.executable, "scripts/check_mem_init.py",
                 "--project", f"synthesis/{arch}"])
            row = benchmarks.get((arch, name))
            if row:
                cycles = int(row["cycle_count"])
                instructions = int(row["instr_retired"])
                print(f"  Valores esperados en la consola: "
                      f"ciclos {cycles} (0x{cycles:X}), "
                      f"instrucciones {instructions} (0x{instructions:X})")
            print(f"  Fotografíe la consola VGA y compare con el valor anterior.")
    return 0


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
    banner("ETAPA FINALIZADA - revise los artefactos en results/ y thesis/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
