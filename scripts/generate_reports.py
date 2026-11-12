#!/usr/bin/env python3
"""Generate one checked report bundle without modifying measurement inputs."""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import collect_results as collector
import thesis_artifacts as artifacts
import coremark_hardware as physical
import measure_benchmarks as benchmark_preparation
from campaign_state import source_fingerprint, verification_fingerprint
from replica_manifest import verified

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build/reports/latest"
GENERATOR_FILES = [Path(p) for p in (__file__, artifacts.__file__, collector.__file__,
                                    physical.__file__, benchmark_preparation.__file__)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configure(results, output, verification):
    """Keep measurement inputs separate from every generated file."""
    artifacts.INPUT_RESULTS = results
    artifacts.RESULTS = output / "results"
    artifacts.TABLES = output / "thesis/tables"
    artifacts.FIGURES = output / "thesis/figures/diagrams"
    artifacts.REPRO = output / "docs"
    artifacts.COREMARK_INPUT_CSV = results / "results_coremark.csv"
    artifacts.COREMARK_CSV = artifacts.RESULTS / "results_coremark.csv"
    artifacts.TIMING_PATHS_TXT = {arch: results / f"timing_paths_{arch}.txt"
                                  for arch in artifacts.ARCHES}
    collector.RESULTS_DIR = results
    collector.VERIF_DIR = verification


def input_files(results, verification):
    files = {results / name for name in ("results_benchmarks.csv", "results_coremark.csv",
             "timing_paths_single_cycle.txt", "timing_paths_pipeline.txt", "campaign_state.json")
             if (results / name).is_file()}
    for arch in artifacts.ARCHES:
        for directory in (results / arch).glob("replica_*"):
            files.update(directory / name for name in ("meta.json", "manifest.json", "fmax.txt", "fit.summary")
                         if (directory / name).is_file())
            if (directory / "manifest.json").is_file():
                manifest = json.loads((directory / "manifest.json").read_text())
                files.update(directory / name for name in manifest.get("artifacts", {})
                             if (directory / name).is_file())
        if not (verification / arch / "results.xml").is_file():
            archived = results / f"verification_{arch}.xml"
            if archived.is_file():
                files.add(archived)
    files.update(verification / name / "results.xml"
                 for name in ("common", "single_cycle", "pipeline")
                 if (verification / name / "results.xml").exists())
    for arch, row in physical.latest_measurements(results).items():
        files.add(results / f"hardware_{arch}_coremark_v2.csv")
        files.update(path for path in physical.observation_inputs(row, results) if path.is_file())
    files.update(GENERATOR_FILES)
    return sorted(files)


def evidence_issues(replicas, benchmarks, verification, tests_ran=False):
    """Report evidence gaps separately from the correctness of rendered values."""
    issues = []
    fingerprint = source_fingerprint()
    state_path = artifacts.INPUT_RESULTS / "campaign_state.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    if not tests_ran and state.get("verify", {}).get("inputs", {}).get("sources") != verification_fingerprint():
        issues.append("Verification results lack a matching RTL/test fingerprint")
    for arch in artifacts.ARCHES:
        rows = [r for r in replicas if r["arch"] == arch]
        if not rows:
            issues.append(f"{arch}: no synthesis replicas")
        for row in rows:
            directory = artifacts.INPUT_RESULTS / arch / f"replica_{row['replica']}"
            if not verified(directory, fingerprint):
                issues.append(f"{arch}/{directory.name}: provenance unverified or stale")
            if row["fmax_mhz"] is None or any(row.get(k) is None for k in artifacts.RESOURCE_PATTERNS):
                issues.append(f"{arch}/{directory.name}: missing frequency or resource data")
        tests = [r for r in verification if r["arch"] == arch]
        if not tests:
            issues.append(f"{arch}: no verification results")
        expected = {suite for group in collector.TEST_SUITES[arch].values() for suite in group}
        missing = expected - {r["suite"] for r in tests}
        if missing:
            issues.append(f"{arch}: missing verification suites: {', '.join(sorted(missing))}")
        if any(r["failed"] or r["errors"] for r in tests):
            issues.append(f"{arch}: unexpected verification failures")
    if not benchmarks:
        issues.append("No benchmark measurements")
    for row in benchmarks:
        name = f"{row['architecture']}/{row['program']}"
        if row["result"] != "pass":
            issues.append(f"{name}: benchmark result {row['result']}")
        if row.get("rtl_sha256") != fingerprint:
            issues.append(f"{name}: benchmark source provenance missing or stale")
        if not row.get("elf_sha256"):
            issues.append(f"{name}: program hash missing")
        if row.get("reference_valid") != "True":
            issues.append(f"{name}: final-state differential validation missing")
        if int(row["cycle_count"]) <= 0 or int(row["instr_retired"]) <= 0:
            issues.append(f"{name}: nonpositive counters")
        if row.get("counter_protocol") != "retire-inclusive-v2":
            issues.append(f"{name}: retirement protocol missing or historical")
        if "coremark" in row["program"].lower() and row.get("coremark_functional_valid") != "True":
            issues.append(f"{name}: functional CRC evidence missing")
    hardware = {row["arch"]: row for row in artifacts.read_coremark_hardware()}
    for arch in artifacts.ARCHES:
        row = hardware.get(arch, {})
        if row.get("coremark_functional_valid") != "True":
            reason = row.get("physical_evidence_issue") or "physical observation missing"
            issues.append(f"{arch}: physical CoreMark CRC evidence missing or invalid ({reason})")
            continue
        for replica in (r for r in replicas if r["arch"] == arch):
            directory = artifacts.INPUT_RESULTS / arch / f"replica_{replica['replica']}"
            path = directory / "manifest.json"
            if path.is_file():
                manifest = json.loads(path.read_text())
                programs = [value for name, value in manifest.get("inputs", {}).items()
                            if name.endswith(".elf")]
                if programs != [row["elf_sha256"]]:
                    issues.append(f"{arch}/{directory.name}: synthesized workload differs from physical CoreMark ELF")
    return issues


def write_report(output, replicas, benchmarks, verification, issues):
    stats = artifacts.replica_stats(replicas)
    metrics = artifacts.benchmark_metrics(benchmarks, stats)
    lines = ["# Resultados de la campaña", "",
             "Estado: **diagnóstico; evidencia incompleta o histórica**." if issues else
             "Estado: evidencia de entrada comprobada para este informe.", "",
             "Las frecuencias de síntesis producen proyecciones de rendimiento. "
             "Las aprobaciones de wrappers incluyen limitaciones de modo máquina; "
             "no acreditan conformidad ISA completa.", "",
             "## Verificación", "", "| Arquitectura | Aprobadas | Fallos/errores | Total |",
             "|---|---:|---:|---:|"]
    for arch in artifacts.ARCHES:
        rows = [r for r in verification if r["arch"] == arch]
        lines.append(f"| {arch} | {sum(r['passed'] for r in rows)} | "
                     f"{sum(r['failed'] + r['errors'] for r in rows)} | {sum(r['total'] for r in rows)} |")
    lines += ["", "## Síntesis por réplicas", "",
              "| Arquitectura | Réplicas con Fmax | Fmax media (MHz) | ALM media |",
              "|---|---:|---:|---:|"]
    for arch in artifacts.ARCHES:
        frequency, alms = stats[arch]["fmax"], stats[arch]["alms"]
        lines.append(f"| {arch} | {frequency['n'] if frequency else 0} | "
                     f"{artifacts.fmt(frequency['mean']) if frequency else '---'} | "
                     f"{artifacts.fmt(alms['mean']) if alms else '---'} |")
    lines += ["", "## Comparación temporal proyectada", "",
              "Media de cocientes de duración pareados por semilla; "
              "la dispersión es descriptiva.", "",
              "| Programa | Speedup temporal medio | Desviación muestral |",
              "|---|---:|---:|"]
    for metric in metrics:
        speedup = metric.get("speedup")
        lines.append(f"| {metric['program']} | {artifacts.fmt(speedup['mean'], 4) if speedup else '---'} | "
                     f"{artifacts.fmt(speedup['std'], 4) if speedup else '---'} |")
    hardware = artifacts.read_coremark_hardware()
    if hardware:
        lines += ["", "## CoreMark en FPGA", "",
                  "El método crc-gated-t0-v1 registra el resultado de las comprobaciones CRC "
                  "mediante x5/t0 tras finalizar; no captura los CRC individuales ni valida "
                  "el temporizador interno de CoreMark.", "",
                  "| Arquitectura | Ciclos | Instrucciones | Resultado CRC acreditado |",
                  "|---|---:|---:|---|"]
        for row in hardware:
            status = "Sí (x5/t0)" if row.get("coremark_functional_valid") == "True" else "Pendiente o inválido"
            lines.append(f"| {row['arch']} | {row['cycles']} | {row['instructions']} | {status} |")
    lines += ["", "## Evidencia pendiente", ""]
    lines += [f"- {issue}" for issue in issues] or ["Sin incidencias detectadas por estas comprobaciones."]
    lines += ["", "## Archivos", "", "- `results/`: datos y resúmenes usados en este informe.",
              "- `thesis/tables/`: tablas LaTeX.",
              "- `thesis/figures/diagrams/`: figuras pgfplots y fuentes standalone.",
              "- `manifest.json`: hashes de entradas y salidas.", "",
              "Los capítulos y PDF de ProyectoGrado requieren incorporar estos archivos; "
              "este comando conserva el documento existente.", ""]
    (output / "report.md").write_text("\n".join(lines))


def standalone_figures(render, compiler):
    for path in artifacts.FIGURES.glob("*.tex"):
        if path.name.endswith("_standalone.tex"):
            continue
        match = re.search(r"(\\begin\{tikzpicture\}.*?\\end\{tikzpicture\})", path.read_text(), re.S)
        if not match:
            raise ValueError(f"Missing TikZ figure: {path}")
        standalone = path.with_name(path.stem + "_standalone.tex")
        standalone.write_text("\\documentclass[tikz,border=6pt]{standalone}\n"
                              "\\usepackage[T1]{fontenc}\n\\usepackage{lmodern}\n"
                              "\\usepackage{pgfplots,siunitx}\n\\pgfplotsset{compat=1.18}\n"
                              "\\pgfplotsset{/pgf/number format/use comma,/pgf/number format/1000 sep={.}}\n"
                              "\\setlength{\\textwidth}{15cm}\n\\begin{document}\n"
                              + match[1] + "\n\\end{document}\n")
        if render:
            result = subprocess.run([compiler, "-interaction=nonstopmode", "-halt-on-error",
                                     standalone.name], cwd=standalone.parent,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            standalone.with_suffix(".build.log").write_text(result.stdout)
            if result.returncode or not standalone.with_suffix(".pdf").is_file():
                raise RuntimeError(f"Figure compilation failed: {standalone}\n{result.stdout[-3500:]}")


def check_manifest(output):
    manifest = json.loads((output / "manifest.json").read_text())
    for name, expected in manifest["outputs"].items():
        if not (output / name).is_file() or digest(output / name) != expected:
            raise ValueError(f"Changed or missing output: {name}")
    for name, expected in manifest["inputs"].items():
        if not Path(name).is_file() or digest(Path(name)) != expected:
            raise ValueError(f"Report input changed: {name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--verification-dir", type=Path, default=ROOT / "verification/cocotb")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Reject incomplete or stale evidence")
    parser.add_argument("--render", action="store_true", help="Compile standalone figures to PDF")
    parser.add_argument("--compiler", default="pdflatex.exe" if shutil.which("pdflatex.exe") else "pdflatex")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    source, output = args.results_dir.resolve(), args.output_dir.resolve()
    if source == output or source in output.parents or output in source.parents:
        parser.error("Report output must be separate from measurement inputs")
    if args.run_tests and (source != ROOT / "results" or args.verification_dir.resolve() != ROOT / "verification/cocotb"):
        parser.error("--run-tests uses the repository verification and results directories")
    try:
        if args.check:
            configure(source, output, args.verification_dir.resolve())
            check_manifest(output)
            return artifacts.check_artifacts()
        generator_files = GENERATOR_FILES
        generator_hashes = {str(p): digest(p) for p in generator_files}
        tests_ok = collector.run_all_tests() if args.run_tests else True
        if any(digest(Path(name)) != expected for name, expected in generator_hashes.items()):
            raise ValueError("Generator sources changed while tests were running")
        configure(source, output, args.verification_dir.resolve())
        inputs = {str(p): digest(p) for p in input_files(source, collector.VERIF_DIR)}
        replicas = artifacts.collect_replicas()
        benchmarks = artifacts.read_benchmarks()
        verification = artifacts.read_verification()
        issues = evidence_issues(replicas, benchmarks, verification, tests_ran=args.run_tests and tests_ok)
        if args.strict and issues:
            raise ValueError("Evidence is not ready for a validated report:\n" + "\n".join(issues))
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
        try:
            configure(source, staging, args.verification_dir.resolve())
            artifacts.RESULTS.mkdir(parents=True)
            artifacts.generate_artifacts()
            if artifacts.check_artifacts():
                raise ValueError("Generated tables or figures failed consistency checks")
            standalone_figures(args.render, args.compiler)
            write_report(staging, replicas, benchmarks, verification, issues)
            for name, expected in inputs.items():
                if digest(Path(name)) != expected:
                    raise ValueError(f"Input changed during generation: {name}")
            manifest = {"schema": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                        "status": "diagnostic" if issues else "checked",
                        "issues": issues, "inputs": inputs,
                        "outputs": {str(p.relative_to(staging)): digest(p)
                                    for p in staging.rglob("*") if p.is_file()}}
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            backup = None
            if output.exists():
                backup = output.with_name(output.name + ".previous-" + staging.name.rsplit("-", 1)[-1])
                output.rename(backup)
            try:
                staging.rename(output)
            except OSError:
                if backup:
                    backup.rename(output)
                raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        configure(source, output, args.verification_dir.resolve())
        print(f"Report: {output / 'report.md'} ({manifest['status']})")
        return 0 if tests_ok and not any(r["failed"] or r["errors"] for r in verification) else 1
    except (OSError, ValueError, KeyError, RuntimeError, ZeroDivisionError, ET.ParseError) as error:
        print(f"Report generation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
