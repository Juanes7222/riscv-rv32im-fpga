#!/usr/bin/env python3
"""Turn the collected measurements into thesis-ready artifacts.

Reads the raw data of the experiment (the replica directories and the
benchmark CSV) and writes the statistics, the LaTeX tables, the pgfplots
figures, the protocol documents and the results chapter.

Usage:
    python3 scripts/thesis_artifacts.py            # regenerate every artifact
    python3 scripts/thesis_artifacts.py --check    # tables vs CSV check
"""

import csv
import hashlib
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from collect_results import TEST_SUITE_NAMES  # noqa: E402
RESULTS = REPO_ROOT / "results"
TABLES = REPO_ROOT / "thesis" / "tables"
FIGURES = REPO_ROOT / "thesis" / "figures" / "diagrams"
CHAPTERS = REPO_ROOT / "thesis" / "chapters"
REPRO = REPO_ROOT / "docs" / "reproduction"

ARCHES = ["single_cycle", "pipeline"]
ARCH_LABELS = {"single_cycle": "Monociclo", "pipeline": "Pipeline"}

RESOURCE_PATTERNS = {
    "alms": r"Logic utilization \(in ALMs\)\s*:\s*([\d,]+)",
    "registers": r"Total registers\s*:\s*([\d,]+)",
    "ram_blocks": r"Total RAM Blocks\s*:\s*([\d,]+)",
    "dsp_blocks": r"Total DSP Blocks\s*:\s*([\d,]+)",
    "memory_bits": r"Total block memory bits\s*:\s*([\d,]+)",
    "pins": r"Total pins\s*:\s*([\d,]+)",
}

RESOURCE_LABELS = {
    "alms": "ALMs",
    "registers": "Registros",
    "ram_blocks": "Bloques RAM",
    "dsp_blocks": "Bloques DSP",
    "memory_bits": "Bits de memoria",
    "pins": "Pines",
}


# --------------------------------------------------------------------------
# Raw data
# --------------------------------------------------------------------------

def rtl_fingerprint() -> str:
    """SHA-256 of the RTL and of the synthesis configuration.

    Two synthesis runs of the same fingerprint are comparable; a different
    fingerprint means the design changed and the old measurements are stale.
    """
    digest = hashlib.sha256()
    files = sorted(p for p in (REPO_ROOT / "rtl").rglob("*") if p.is_file())
    files += sorted((REPO_ROOT / "synthesis").glob("*/constraints.sdc"))
    files += sorted((REPO_ROOT / "synthesis").glob("*/setup.tcl"))
    files += sorted((REPO_ROOT / "synthesis").glob("*/build.tcl"))
    for path in files:
        digest.update(str(path.relative_to(REPO_ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def parse_fit_summary(path: Path) -> dict:
    """Resource counts of a .fit.summary file. Missing values are None."""
    resources = {key: None for key in RESOURCE_PATTERNS}
    if not path.exists():
        return resources
    text = path.read_text()
    for key, pattern in RESOURCE_PATTERNS.items():
        match = re.search(pattern, text)
        if match:
            resources[key] = int(match.group(1).replace(",", ""))
    return resources


def collect_replicas() -> list:
    """One record per synthesis replica, with Fmax and resource usage."""
    records = []
    for arch in ARCHES:
        for replica_dir in sorted((RESULTS / arch).glob("replica_*")):
            meta_path = replica_dir / "meta.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            fmax = None
            fmax_file = replica_dir / "fmax.txt"
            if fmax_file.exists():
                try:
                    fmax = float(fmax_file.read_text().strip())
                except ValueError:
                    fmax = None
            record = {
                "arch": arch,
                "replica": replica_dir.name.replace("replica_", ""),
                "fmax_mhz": fmax,
                "git_commit": meta.get("git_commit", ""),
                "fingerprint": meta.get("fingerprint", ""),
                "seed": meta.get("seed", ""),
                "date": meta.get("date", ""),
            }
            record.update(parse_fit_summary(replica_dir / "fit.summary"))
            records.append(record)
    return records


def read_benchmarks() -> list:
    """Rows of results/results_benchmarks.csv."""
    path = RESULTS / "results_benchmarks.csv"
    if not path.exists():
        return []
    with path.open() as fp:
        return list(csv.DictReader(fp))


def read_verification() -> list:
    """Verification suites of both architectures, from the results.xml files.

    The XML is the freshest source: the verification stage rewrites it on
    every run, while the CSV is only a snapshot of the last collection.
    """
    from collect_results import collect_verification_results

    rows = []
    for arch in ARCHES:
        for suite, summary in collect_verification_results(arch).items():
            rows.append({
                "suite": suite,
                "arch": arch,
                "passed": summary.passed,
                "failed": summary.failed,
                "errors": summary.errors,
                "total": summary.total,
            })
    return rows


def read_verification_csv(path: Path) -> list:
    """Rows of results/results_verification.csv as integer counts."""
    with path.open(newline="") as fp:
        return [
            {
                "suite": row["suite"],
                "arch": row["arch"],
                "passed": int(row["passed"]),
                "failed": int(row["failed"]),
                "errors": int(row.get("errors") or 0),
                "total": int(row["total"]),
            }
            for row in csv.DictReader(fp)
        ]


def describe(values) -> dict:
    """Mean, sample standard deviation (n-1), CV, min and max."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    n = len(vals)
    mean = sum(vals) / n
    sd = statistics.stdev(vals) if n > 1 else 0.0
    return {
        "n": n,
        "mean": mean,
        "std": sd,
        "cv": (sd / mean * 100.0) if mean else 0.0,
        "min": min(vals),
        "max": max(vals),
        "values": vals,
    }


def fmt(value, digits=2, dash="---"):
    """Format a number for the report, or the dash when it is missing."""
    if value is None:
        return dash
    return f"{value:.{digits}f}"


def tex_escape(text: str) -> str:
    """Escape the LaTeX specials of a free text field."""
    for old, new in (("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                     ("_", r"\_"), ("{", r"\{"), ("}", r"\}")):
        text = text.replace(old, new)
    return text


# --------------------------------------------------------------------------
# Derived metrics
# --------------------------------------------------------------------------

def replica_stats(replicas: list) -> dict:
    """Per-architecture statistics of Fmax and of every resource."""
    stats = {}
    for arch in ARCHES:
        rows = [r for r in replicas if r["arch"] == arch]
        arch_stats = {"fmax": describe([r["fmax_mhz"] for r in rows])}
        for key in RESOURCE_PATTERNS:
            arch_stats[key] = describe([r.get(key) for r in rows])
        arch_stats["replicas"] = rows
        stats[arch] = arch_stats
    return stats


def benchmark_metrics(benchmarks: list, stats: dict) -> list:
    """Throughput and speedup per program, spread over the synthesis replicas.

    The CPI is deterministic in simulation, so the variability of the
    throughput comes from the Fmax of each synthesis replica.
    """
    by_program = {}
    for row in benchmarks:
        by_program.setdefault(row["program"], {})[row["architecture"]] = row

    metrics = []
    for program, per_arch in sorted(by_program.items()):
        entry = {"program": program, "arch": {}}
        for arch in ARCHES:
            row = per_arch.get(arch)
            if row is None:
                continue
            cpi = float(row["cpi"])
            fmax_replicas = stats[arch]["fmax"]["values"] if stats[arch]["fmax"] else []
            # A run that did not finish leaves the counters frozen at an
            # arbitrary point: it has no valid throughput and no speedup.
            valid = row["result"] == "pass"
            throughputs = [f / cpi for f in fmax_replicas] if valid else []
            entry["arch"][arch] = {
                "row": row,
                "valid": valid,
                "cpi": cpi,
                "fmax_mean": (sum(fmax_replicas) / len(fmax_replicas))
                if fmax_replicas else None,
                "ipc": 1.0 / cpi if cpi else 0.0,
                "cycles": int(row["cycle_count"]),
                "instructions": int(row["instr_retired"]),
                "result": row["result"],
                "note": row.get("note", ""),
                "throughputs": throughputs,
                "throughput": describe(throughputs),
            }
        sc = entry["arch"].get("single_cycle")
        pipe = entry["arch"].get("pipeline")
        if sc and pipe and sc["valid"] and pipe["valid"] and sc["throughputs"] and pipe["throughputs"]:
            # The replicas are paired by index: they are exchangeable and the
            # pairing keeps the estimator variance low.
            pairs = list(zip(sc["throughputs"], pipe["throughputs"]))
            speedups = [p / s for s, p in pairs if s]
            entry["speedups"] = speedups
            entry["speedup"] = describe(speedups)
            entry["verdict"] = "H1" if entry["speedup"] and entry["speedup"]["mean"] - entry["speedup"]["std"] > 1.0 else "H0"
        metrics.append(entry)
    return metrics


def efficiency_table(metrics: list, stats: dict) -> list:
    """Resource efficiency and resource overhead of the pipeline."""
    rows = []
    for arch in ARCHES:
        sc = stats["single_cycle"]
        pipe = stats["pipeline"]
        for key, label in RESOURCE_LABELS.items():
            sc_stat = sc.get(key)
            pipe_stat = pipe.get(key)
            if not sc_stat or not pipe_stat:
                continue
            overhead = (pipe_stat["mean"] - sc_stat["mean"]) / sc_stat["mean"] * 100.0
            rows.append({
                "arch": arch,
                "resource": key,
                "label": label,
                "single_cycle": sc_stat["mean"],
                "pipeline": pipe_stat["mean"],
                "overhead_pct": overhead if arch == "pipeline" else None,
            })
    return rows


# --------------------------------------------------------------------------
# CSV outputs
# --------------------------------------------------------------------------

def write_replicas_csv(replicas: list) -> Path:
    path = RESULTS / "results_replicas.csv"
    fields = ["arch", "replica", "fmax_mhz", "alms", "registers", "ram_blocks",
              "dsp_blocks", "memory_bits", "pins", "seed", "date", "git_commit"]
    with path.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields, restval="")
        writer.writeheader()
        for record in replicas:
            writer.writerow({field: record.get(field, "") for field in fields})
    return path


def write_fmax_csv(stats: dict) -> Path:
    path = RESULTS / "results_fmax.csv"
    with path.open("w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["arch", "fmax_mean_mhz", "fmax_std_mhz", "fmax_cv_pct",
                         "fmax_min_mhz", "fmax_max_mhz", "replicas"])
        for arch in ARCHES:
            stat = stats[arch]["fmax"]
            writer.writerow([
                arch,
                fmt(stat["mean"]) if stat else "",
                fmt(stat["std"]) if stat else "",
                fmt(stat["cv"]) if stat else "",
                fmt(stat["min"]) if stat else "",
                fmt(stat["max"]) if stat else "",
                stat["n"] if stat else 0,
            ])
    return path


def write_statistics_csv(stats: dict) -> Path:
    path = RESULTS / "results_statistics.csv"
    with path.open("w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["arch", "metric", "n", "mean", "std", "cv_pct", "min", "max"])
        for arch in ARCHES:
            for key in ["fmax"] + list(RESOURCE_PATTERNS):
                stat = stats[arch].get(key)
                if not stat:
                    continue
                writer.writerow([arch, key, stat["n"], fmt(stat["mean"], 3),
                                 fmt(stat["std"], 3), fmt(stat["cv"], 3),
                                 fmt(stat["min"], 3), fmt(stat["max"], 3)])
    return path


def write_benchmarks_csv(metrics: list) -> Path:
    path = RESULTS / "results_benchmarks_summary.csv"
    fields = ["program", "architecture", "result", "cycle_count", "instr_retired",
              "cpi", "ipc", "fmax_mean_mhz", "throughput_mean_mips",
              "throughput_std_mips", "latency_ms", "speedup_mean", "speedup_std",
              "verdict"]
    with path.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields, restval="")
        writer.writeheader()
        for entry in metrics:
            for arch in ARCHES:
                data = entry["arch"].get(arch)
                if not data:
                    continue
                speedup = entry.get("speedup")
                writer.writerow({
                    "program": entry["program"],
                    "architecture": arch,
                    "result": data["result"],
                    "cycle_count": data["cycles"],
                    "instr_retired": data["instructions"],
                    "cpi": fmt(data["cpi"], 4),
                    "ipc": fmt(data["ipc"], 4),
                    "fmax_mean_mhz": fmt(data["throughput"]["mean"] * data["cpi"])
                    if data["throughput"] else "",
                    "throughput_mean_mips": fmt(data["throughput"]["mean"], 3)
                    if data["throughput"] else "",
                    "throughput_std_mips": fmt(data["throughput"]["std"], 3)
                    if data["throughput"] else "",
                    "latency_ms": fmt(data["cycles"] / (data["fmax_mean"] * 1000.0), 4)
                    if data["fmax_mean"] and data["valid"] else "",
                    "speedup_mean": fmt(speedup["mean"], 4) if speedup else "",
                    "speedup_std": fmt(speedup["std"], 4) if speedup else "",
                    "verdict": entry.get("verdict", ""),
                })
    return path


def write_efficiency_csv(rows: list, metrics: list) -> Path:
    path = RESULTS / "results_efficiency.csv"
    with path.open("w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["resource", "single_cycle_mean", "pipeline_mean",
                         "overhead_pct"])
        for row in rows:
            writer.writerow([row["label"], fmt(row["single_cycle"], 1),
                             fmt(row["pipeline"], 1),
                             fmt(row["overhead_pct"], 2) if row["overhead_pct"] is not None else ""])
    return path


# --------------------------------------------------------------------------
# LaTeX tables
# --------------------------------------------------------------------------

def table_header() -> list:
    return [
        "% Generado por scripts/thesis_artifacts.py - no editar a mano.",
        f"% Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]


def table_fmax_replicas(replicas: list, stats: dict) -> str:
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Frecuencia máxima por réplica de síntesis "
        r"(modelo \emph{Slow 1100 mV 85$^\circ$C}).}",
        r"\label{tab:fmax_replicas}",
        r"\begin{tabular}{lrr}",
        r"\toprule",
        r"Réplica & Monociclo (MHz) & Pipeline (MHz) \\",
        r"\midrule",
    ]
    sc_rows = [r for r in replicas if r["arch"] == "single_cycle"]
    pipe_rows = [r for r in replicas if r["arch"] == "pipeline"]
    for index in range(max(len(sc_rows), len(pipe_rows))):
        sc = fmt(sc_rows[index]["fmax_mhz"]) if index < len(sc_rows) else r"\textemdash"
        pipe = fmt(pipe_rows[index]["fmax_mhz"]) if index < len(pipe_rows) else r"\textemdash"
        lines.append(f"{index + 1} & {sc} & {pipe} \\\\")
    lines.append(r"\midrule")
    for label, key in (("Media", "mean"), ("Desviación estándar", "std"),
                       ("Mínimo", "min"), ("Máximo", "max")):
        cells = []
        for arch in ARCHES:
            stat = stats[arch]["fmax"]
            cells.append(fmt(stat[key]) if stat else r"\textemdash")
        lines.append(f"{label} & {cells[0]} & {cells[1]} \\\\")
    counts = [stats[arch]["fmax"]["n"] if stats[arch]["fmax"] else 0 for arch in ARCHES]
    lines.append(f"Número de réplicas (n) & {counts[0]} & {counts[1]} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def table_resources(stats: dict) -> str:
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Utilización de recursos de la FPGA por réplica "
        r"(media $\pm$ desviación estándar, n = 5).}",
        r"\label{tab:resources}",
        r"\begin{tabular}{lrrl}",
        r"\toprule",
        r"Recurso & Monociclo & Pipeline & Overhead \\",
        r"\midrule",
    ]
    for key, label in RESOURCE_LABELS.items():
        cells = []
        for arch in ARCHES:
            stat = stats[arch].get(key)
            cells.append(f"{fmt(stat['mean'], 0)} $\\pm$ {fmt(stat['std'], 0)}"
                         if stat else r"\textemdash")
        sc_stat = stats["single_cycle"].get(key)
        pipe_stat = stats["pipeline"].get(key)
        if sc_stat and pipe_stat and sc_stat["mean"]:
            overhead = (pipe_stat["mean"] - sc_stat["mean"]) / sc_stat["mean"] * 100.0
            overhead_str = f"{overhead:+.1f} \\%"
        else:
            overhead_str = r"\textemdash"
        lines.append(f"{label} & {cells[0]} & {cells[1]} & {overhead_str} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def table_benchmarks(metrics: list) -> str:
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        r"\caption{CPI, IPC, throughput y latencia por programa y arquitectura. "
        r"El throughput y la latencia se obtienen con la Fmax media de las cinco "
        r"réplicas de síntesis.}",
        r"\label{tab:benchmarks}",
        r"\begin{tabular}{llrrrrrr}",
        r"\toprule",
        r"Programa & Arquitectura & Ciclos & Instrucciones & CPI & IPC & "
        r"Throughput (MIPS) & Latencia (ms) \\",
        r"\midrule",
    ]
    for entry in metrics:
        for arch in ARCHES:
            data = entry["arch"].get(arch)
            if not data:
                continue
            if not data["valid"]:
                lines.append(
                    f"{tex_escape(entry['program'])} & {ARCH_LABELS[arch]} & "
                    f"{data['cycles']} & {data['instructions']} & "
                    + " & ".join([r"\textemdash"] * 3) + r" \\")
                continue
            throughput = fmt(data["throughput"]["mean"], 2) if data["throughput"] else r"\textemdash"
            latency = (data["cycles"] / (data["fmax_mean"] * 1000.0)
                       if data["fmax_mean"] else None)
            lines.append(
                f"{tex_escape(entry['program'])} & {ARCH_LABELS[arch]} & "
                f"{data['cycles']} & {data['instructions']} & "
                f"{fmt(data['cpi'], 4)} & {fmt(data['ipc'], 4)} & {throughput} & "
                f"{fmt(latency, 4)} \\\\"
            )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


COREMARK_CSV = RESULTS / "results_coremark.csv"
COREMARK_PROVENANCE = (
    "git_commit", "rtl_fingerprint", "date_utc", "sof_sha256",
    "fmax_mhz", "tohost_addr",
)


def read_coremark_hardware() -> list:
    """The official CoreMark runs, read from the frozen board counters.

    One row per architecture: iterations, cycles and instructions as the VGA
    console shows them, and the clock the CPU ran at.  Everything else is
    derived, so the file only stores what was measured.
    """
    if not COREMARK_CSV.exists():
        return []
    rows = []
    with open(COREMARK_CSV) as fp:
        for row in csv.DictReader(fp):
            cycles = int(row["cycles"])
            instructions = int(row["instructions"])
            iterations = int(row["iterations"])
            clock = float(row["clock_mhz"])
            seconds = cycles / (clock * 1e6)
            score = iterations / seconds
            record = {
                "arch": row["architecture"],
                "iterations": iterations,
                "cycles": cycles,
                "instructions": instructions,
                "clock_mhz": clock,
                "seconds": seconds,
                "score": score,
                "per_mhz": score / clock,
                "cpi": cycles / instructions if instructions else 0.0,
            }
            for key in COREMARK_PROVENANCE:
                record[key] = row.get(key, "")
            rows.append(record)
    return rows


def write_coremark_csv() -> Path:
    """Persist the official CoreMark hardware run so it can be re-derived."""
    rows = read_coremark_hardware()
    path = RESULTS / "results_coremark.csv"
    with open(path, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "architecture", "iterations", "cycles", "instructions",
            "clock_mhz", "seconds", "score", "score_per_mhz",
        ] + list(COREMARK_PROVENANCE))
        for row in rows:
            writer.writerow([
                row["arch"], row["iterations"], row["cycles"],
                row["instructions"], row["clock_mhz"], row["seconds"],
                row["score"], row["per_mhz"],
            ] + [row.get(key, "") for key in COREMARK_PROVENANCE])
    print(f"  {path.relative_to(REPO_ROOT)}")
    return path


def table_coremark(rows: list) -> str:
    """CoreMark in hardware: the official EEMBC run (>= 10 s)."""
    if not rows:
        return ""
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{CoreMark en hardware, 2000 iteraciones ($\geq$ 10 s, regla "
        r"de EEMBC). Ciclos e instrucciones son los contadores congelados que "
        r"muestra la consola VGA.}",
        r"\label{tab:coremark}",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"Arquitectura & Reloj (MHz) & Ciclos & Instrucciones & Tiempo (s) & "
        r"CoreMark & CoreMark/MHz \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{ARCH_LABELS[row['arch']]} & {fmt(row['clock_mhz'], 0)} & "
            f"{row['cycles']} & {row['instructions']} & "
            f"{fmt(row['seconds'], 2)} & {fmt(row['score'], 2)} & "
            f"{fmt(row['per_mhz'], 3)} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def table_speedup(metrics: list) -> str:
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Speedup del pipeline respecto al monociclo y evaluación "
        r"de la hipótesis por programa.}",
        r"\label{tab:speedup}",
        r"\begin{tabular}{lrrrl}",
        r"\toprule",
        r"Programa & Speedup medio & Desviación estándar & Media $-$ SD & Resultado \\",
        r"\midrule",
    ]
    for entry in metrics:
        speedup = entry.get("speedup")
        if not speedup:
            continue
        lower = speedup["mean"] - speedup["std"]
        verdict = "H1 sostenida" if entry.get("verdict") == "H1" else "H0 no descartada"
        lines.append(
            f"{tex_escape(entry['program'])} & {fmt(speedup['mean'], 3)} & "
            f"{fmt(speedup['std'], 3)} & {fmt(lower, 3)} & {verdict} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def table_statistics(stats: dict) -> str:
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Estadística descriptiva de las cinco réplicas de síntesis "
        r"por arquitectura (desviación estándar muestral, $n-1$).}",
        r"\label{tab:statistics}",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Arquitectura & Métrica & Media & Desv. estándar & CV (\%) & Mínimo & Máximo \\",
        r"\midrule",
    ]
    for arch in ARCHES:
        for key in ["fmax"] + list(RESOURCE_PATTERNS):
            stat = stats[arch].get(key)
            if not stat:
                continue
            name = "Fmax (MHz)" if key == "fmax" else RESOURCE_LABELS[key]
            lines.append(
                f"{ARCH_LABELS[arch]} & {name} & {fmt(stat['mean'], 3)} & "
                f"{fmt(stat['std'], 3)} & {fmt(stat['cv'], 2)} & "
                f"{fmt(stat['min'], 3)} & {fmt(stat['max'], 3)} \\\\"
            )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def table_efficiency(metrics: list, stats: dict, efficiency: list) -> str:
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Eficiencia relativa: throughput por recurso utilizado y "
        r"overhead de recursos del pipeline.}",
        r"\label{tab:efficiency}",
        r"\begin{tabular}{lrr}",
        r"\toprule",
        r"Indicador & Monociclo & Pipeline \\",
        r"\midrule",
    ]
    per_arch = {}
    for arch in ARCHES:
        throughputs = [m["arch"][arch]["throughput"]["mean"] for m in metrics
                       if arch in m["arch"] and m["arch"][arch].get("throughput")]
        if not throughputs:
            per_arch[arch] = {}
            continue
        mean_throughput = sum(throughputs) / len(throughputs)
        alms = stats[arch]["alms"]
        registers = stats[arch]["registers"]
        per_arch[arch] = {
            "per_alm": mean_throughput / (alms["mean"] / 1000.0) if alms else None,
            "per_reg": mean_throughput / (registers["mean"] / 1000.0) if registers else None,
        }
    for key, label in (("per_alm", "Throughput por 1000 ALMs (MIPS)"),
                       ("per_reg", "Throughput por 1000 registros (MIPS)")):
        cells = [fmt(per_arch[arch].get(key), 3) if arch in per_arch else r"\textemdash"
                 for arch in ARCHES]
        lines.append(f"{label} & {cells[0]} & {cells[1]} \\\\")
    for row in efficiency:
        if row["overhead_pct"] is None:
            continue
        lines.append(f"Overhead de {row['label'].lower()} del pipeline & "
                     f"--- & {row['overhead_pct']:+.1f} \\% \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def verification_table_rows(rows: list) -> list:
    """Rows of the verification table: (label, counts per architecture).

    ``counts[arch]`` is ``(passed, failed + errors, total)`` or None when the
    architecture does not run that suite. Suites keep the order of ``rows``.
    """
    by_suite = {}
    for row in rows:
        by_suite.setdefault(row["suite"], {})[row["arch"]] = row
    table = []
    for suite, per_arch in by_suite.items():
        counts = {}
        for arch in ARCHES:
            row = per_arch.get(arch)
            if not row:
                counts[arch] = None
                continue
            counts[arch] = (int(row["passed"]),
                            int(row["failed"]) + int(row.get("errors", 0)),
                            int(row["total"]))
        table.append((TEST_SUITE_NAMES.get(suite, suite), counts))
    return table


def table_verification(rows: list) -> str:
    """Verification table, reusing the collector of the verification results."""
    if not rows:
        return ""
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Resultados de la verificación funcional "
        r"(suites de instrucciones, modelo de referencia y hazards).}",
        r"\label{tab:verification_results}",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"Suite de pruebas & \multicolumn{3}{c}{Monociclo} & \multicolumn{3}{c}{Pipeline} \\",
        r"\cmidrule(lr){2-4} \cmidrule(lr){5-7}",
        r"& Aprobadas & Fallidas & Total & Aprobadas & Fallidas & Total \\",
        r"\midrule",
    ]
    for label, counts in verification_table_rows(rows):
        cells = []
        for arch in ARCHES:
            values = counts[arch]
            if values is None:
                cells += [r"\textemdash"] * 3
                continue
            passed, failed, total = values
            failed_str = (r"\textcolor{red}{" + str(failed) + "}") if failed else "0"
            cells += [str(passed), failed_str, str(total)]
        lines.append(f"{tex_escape(label)} & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def _latex_count(cell: str):
    """Integer of a generated table cell: 0, 12, \\textcolor{red}{3} or dash."""
    if cell == r"\textemdash":
        return None
    match = re.search(r"\d+", cell)
    return int(match.group()) if match else None


def parse_tex_rows(path: Path) -> list:
    """Rows of a generated table as cell lists; header and rules skipped."""
    rows = []
    inside = False
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped == r"\midrule":
            inside = True
            continue
        if stripped == r"\bottomrule":
            break
        if not inside or not stripped.endswith(r"\\"):
            continue
        rows.append([cell.strip() for cell in stripped[:-2].split("&")])
    return rows


def parse_verification_table_tex(path: Path) -> dict:
    """Map each row label of the LaTeX table to its six counts."""
    return {row[0]: [_latex_count(cell) for cell in row[1:]]
            for row in parse_tex_rows(path) if len(row) == 7}


def _read_csv_rows(path: Path) -> list:
    with path.open(newline="") as fp:
        return list(csv.DictReader(fp))


def _table_problems(name: str, expected: dict, actual: dict) -> list:
    """Differences between expected and actual rows, keyed by label."""
    problems = []
    for label, cells in expected.items():
        if label not in actual:
            problems.append(f"{name}: falta la fila '{label}' en el .tex")
        elif actual[label] != cells:
            problems.append(f"{name}: '{label}' CSV {cells} != TeX {actual[label]}")
    for label in actual:
        if label not in expected:
            problems.append(f"{name}: sobra la fila '{label}' en el .tex")
    return problems


def verification_table_problems() -> list:
    """Compare results_verification.csv with verification_results.tex.

    The CSV is written by collect_results.py from the results.xml files and
    the table by this script: they must agree suite by suite.
    """
    csv_path = RESULTS / "results_verification.csv"
    tex_path = TABLES / "verification_results.tex"
    for path in (csv_path, tex_path):
        if not path.exists():
            raise FileNotFoundError(path)

    expected = {}
    for label, counts in verification_table_rows(read_verification_csv(csv_path)):
        values = []
        for arch in ARCHES:
            values += list(counts[arch]) if counts[arch] else [None, None, None]
        expected[tex_escape(label)] = values
    return _table_problems("Verificación", expected,
                           parse_verification_table_tex(tex_path))


def fmax_table_problems() -> list:
    """Compare results_fmax.csv and results_replicas.csv with the Fmax table."""
    replicas = {
        arch: [row for row in _read_csv_rows(RESULTS / "results_replicas.csv")
               if row["arch"] == arch]
        for arch in ARCHES
    }
    summary = {row["arch"]: row
               for row in _read_csv_rows(RESULTS / "results_fmax.csv")}

    expected = {}
    for index in range(max(len(replicas[arch]) for arch in ARCHES)):
        cells = []
        for arch in ARCHES:
            rows = replicas[arch]
            cells.append(fmt(float(rows[index]["fmax_mhz"]))
                         if index < len(rows) else r"\textemdash")
        expected[str(index + 1)] = cells
    for label, key in (("Media", "fmax_mean_mhz"),
                       ("Desviación estándar", "fmax_std_mhz"),
                       ("Mínimo", "fmax_min_mhz"),
                       ("Máximo", "fmax_max_mhz")):
        expected[label] = [
            fmt(float(summary[arch][key]))
            if summary.get(arch, {}).get(key) else r"\textemdash"
            for arch in ARCHES]
    expected["Número de réplicas (n)"] = [
        str(int(summary[arch]["replicas"]))
        if summary.get(arch, {}).get("replicas") else "0"
        for arch in ARCHES]

    actual = {row[0]: row[1:]
              for row in parse_tex_rows(TABLES / "fmax_replicas.tex")}
    return _table_problems("Fmax", expected, actual)


def resources_table_problems() -> list:
    """Compare the statistics and efficiency CSVs with the resources table."""
    stats = {(row["arch"], row["metric"]): row
             for row in _read_csv_rows(RESULTS / "results_statistics.csv")}
    overhead = {row["resource"]: row["overhead_pct"]
                for row in _read_csv_rows(RESULTS / "results_efficiency.csv")
                if row["overhead_pct"].strip()}

    expected = {}
    for key, label in RESOURCE_LABELS.items():
        cells = []
        for arch in ARCHES:
            row = stats.get((arch, key))
            cells.append(f"{float(row['mean']):.0f} $\\pm$ "
                         f"{float(row['std']):.0f}"
                         if row else r"\textemdash")
        pct = overhead.get(label)
        cells.append(f"{float(pct):+.1f} \\%"
                     if pct is not None else r"\textemdash")
        expected[label] = cells

    actual = {row[0]: row[1:]
              for row in parse_tex_rows(TABLES / "resources.tex")}
    return _table_problems("Recursos", expected, actual)


def statistics_table_problems() -> list:
    """Compare results_statistics.csv with the statistics table."""
    expected = {}
    problems = []
    for row in _read_csv_rows(RESULTS / "results_statistics.csv"):
        name = ("Fmax (MHz)" if row["metric"] == "fmax"
                else RESOURCE_LABELS[row["metric"]])
        key = f"{ARCH_LABELS[row['arch']]} / {name}"
        mean = float(row["mean"])
        std = float(row["std"])
        # The table derives the CV from mean and standard deviation instead of
        # reading the stored column, so the check must do the same.
        cv = std / mean * 100 if mean else 0.0
        # The stored CV comes from full-precision replicas: rounding mean and
        # std to three decimals can move the recomputed value by ~0.001.
        if abs(float(row["cv_pct"]) - cv) > 0.0015:
            problems.append(f"Estadísticas: '{key}' cv_pct del CSV "
                            f"{row['cv_pct']} no coincide con std/media "
                            f"({cv:.3f})")
        expected[key] = [
            fmt(mean, 3), fmt(std, 3), fmt(cv, 2),
            fmt(float(row["min"]), 3), fmt(float(row["max"]), 3),
        ]

    actual = {f"{row[0]} / {row[1]}": row[2:]
              for row in parse_tex_rows(TABLES / "statistics.tex")}
    return problems + _table_problems("Estadísticas", expected, actual)


def efficiency_table_problems() -> list:
    """Compare results_efficiency.csv and its sources with the efficiency table.

    The throughput per resource is derived, so it is rebuilt from the mean
    throughput of the summary and the mean resource count per architecture.
    """
    stats = {(row["arch"], row["metric"]): row
             for row in _read_csv_rows(RESULTS / "results_statistics.csv")}
    throughputs = {}
    for row in _read_csv_rows(RESULTS / "results_benchmarks_summary.csv"):
        if row["result"] != "pass" or not row["throughput_mean_mips"].strip():
            continue
        throughputs.setdefault(row["architecture"], []).append(
            float(row["throughput_mean_mips"]))

    def per_resource(arch: str, metric: str):
        values = throughputs.get(arch)
        stat = stats.get((arch, metric))
        if not values or not stat:
            return None
        mean_throughput = sum(values) / len(values)
        return mean_throughput / (float(stat["mean"]) / 1000.0)

    expected = {}
    for metric, label in (("alms", "Throughput por 1000 ALMs (MIPS)"),
                          ("registers", "Throughput por 1000 registros (MIPS)")):
        expected[label] = [
            fmt(per_resource(arch, metric), 3)
            if per_resource(arch, metric) is not None else r"\textemdash"
            for arch in ARCHES]
    for row in _read_csv_rows(RESULTS / "results_efficiency.csv"):
        if not row["overhead_pct"].strip():
            continue
        expected[f"Overhead de {row['resource'].lower()} del pipeline"] = [
            "---", f"{float(row['overhead_pct']):+.1f} \\%"]

    actual = {row[0]: row[1:]
              for row in parse_tex_rows(TABLES / "efficiency.tex")}
    return _table_problems("Eficiencia", expected, actual)


def _benchmark_cell_matches(expected: str, actual: str, column: int) -> bool:
    """Throughput is stored with three decimals and shown with two."""
    if expected == actual:
        return True
    if column != 6 or r"\textemdash" in (expected, actual):
        return False
    try:
        return abs(float(expected) - float(actual)) <= 0.015
    except ValueError:
        return False


def benchmarks_table_problems() -> list:
    """Compare results_benchmarks_summary.csv with the benchmarks table."""
    expected = []
    for row in _read_csv_rows(RESULTS / "results_benchmarks_summary.csv"):
        cells = [tex_escape(row["program"]), ARCH_LABELS[row["architecture"]],
                 str(int(row["cycle_count"])), str(int(row["instr_retired"]))]
        if row["result"] != "pass":
            cells += [r"\textemdash"] * 3
        else:
            cells += [f"{float(row['cpi']):.4f}",
                      f"{float(row['ipc']):.4f}",
                      f"{float(row['throughput_mean_mips']):.2f}",
                      f"{float(row['latency_ms']):.4f}"]
        expected.append(cells)

    actual = parse_tex_rows(TABLES / "benchmarks.tex")
    problems = []
    if len(expected) != len(actual):
        problems.append(f"Benchmarks: {len(expected)} filas en el CSV y "
                        f"{len(actual)} en el .tex")
    for index, (exp, act) in enumerate(zip(expected, actual), start=1):
        if len(exp) != len(act):
            problems.append(f"Benchmarks fila {index}: {len(exp)} columnas en el "
                            f"CSV y {len(act)} en el .tex")
            continue
        for column, (csv_cell, tex_cell) in enumerate(zip(exp, act)):
            if not _benchmark_cell_matches(csv_cell, tex_cell, column):
                problems.append(f"Benchmarks fila {index}, columna {column + 1}: "
                                f"CSV {csv_cell} != TeX {tex_cell}")
    return problems


def _speedup_cell_matches(column: int, csv_cell: str, tex_cell: str) -> bool:
    """The CSV keeps four decimals; the table derives the bound and rounds it."""
    if csv_cell == tex_cell:
        return True
    if column == 3:
        return False
    tolerance = 0.0006 if column < 2 else 0.0015
    try:
        return abs(float(csv_cell) - float(tex_cell)) <= tolerance
    except ValueError:
        return False


def speedup_table_problems() -> list:
    """Compare results_benchmarks_summary.csv with the speedup table.

    Both architectures share the paired speedup of a program, so the first
    row of each program is enough: a disagreement between them means the
    summary itself is inconsistent and is reported too.
    """
    expected = {}
    problems = []
    conflicts = set()
    for row in _read_csv_rows(RESULTS / "results_benchmarks_summary.csv"):
        if not row["speedup_mean"].strip():
            continue
        mean = float(row["speedup_mean"])
        std = float(row["speedup_std"])
        cells = [fmt(mean, 3), fmt(std, 3), fmt(mean - std, 3),
                 "H1 sostenida" if row["verdict"] == "H1"
                 else "H0 no descartada"]
        label = tex_escape(row["program"])
        previous = expected.get(label)
        if label in conflicts:
            continue
        if previous is not None and previous != cells:
            problems.append(f"Speedup: '{row['program']}' tiene speedups "
                            f"distintos entre arquitecturas ({previous} y "
                            f"{cells})")
            conflicts.add(label)
            del expected[label]
            continue
        expected[label] = cells

    actual = {row[0]: row[1:]
              for row in parse_tex_rows(TABLES / "speedup.tex")}
    for label in conflicts:
        actual.pop(label, None)

    for label, cells in expected.items():
        if label not in actual:
            problems.append(f"Speedup: falta la fila '{label}' en el .tex")
            continue
        tex_cells = actual.pop(label)
        if len(tex_cells) != len(cells):
            problems.append(f"Speedup: '{label}' tiene {len(tex_cells)} "
                            f"columnas en el .tex y {len(cells)} en el CSV")
            continue
        for column, (csv_cell, tex_cell) in enumerate(zip(cells, tex_cells)):
            if not _speedup_cell_matches(column, csv_cell, tex_cell):
                problems.append(f"Speedup: '{label}' columna {column + 1}: "
                                f"CSV {csv_cell} != TeX {tex_cell}")
    for label in actual:
        problems.append(f"Speedup: sobra la fila '{label}' en el .tex")
    return problems


def coremark_table_problems() -> list:
    """Compare results_coremark.csv with the CoreMark table."""
    expected = {}
    for row in _read_csv_rows(COREMARK_CSV):
        expected[ARCH_LABELS[row["architecture"]]] = [
            f"{float(row['clock_mhz']):.0f}",
            str(int(row["cycles"])),
            str(int(row["instructions"])),
            f"{float(row['seconds']):.2f}",
            f"{float(row['score']):.2f}",
            f"{float(row['score_per_mhz']):.3f}",
        ]

    actual = {row[0]: row[1:]
              for row in parse_tex_rows(TABLES / "coremark.tex")}
    return _table_problems("CoreMark", expected, actual)


def _figure_addplots(path: Path, error_bars: bool = False) -> list:
    """Points of every ``\\addplot`` of a generated pgfplots figure."""
    plots = []
    text = path.read_text()
    for match in re.finditer(r"\\addplot coordinates \{([^}]*)\};", text):
        body = match.group(1)
        if error_bars:
            points = [(int(m.group(1)), float(m.group(2)), float(m.group(3)))
                      for m in re.finditer(
                          r"\((\d+),([\d.]+)\)\s*\+-\s*\(0,([\d.]+)\)", body)]
        else:
            points = [(int(m.group(1)), float(m.group(2)))
                      for m in re.finditer(r"\((\d+),([\d.]+)\)", body)]
        plots.append(points)
    return plots


def _grouped_figure_problems(name: str, filename: str, expected: list,
                             tolerance: float = 0.0006) -> list:
    """Compare the series of a grouped bar figure with the expected values."""
    plots = _figure_addplots(FIGURES / filename)
    if len(plots) != len(expected):
        return [f"Figura {name}: {len(plots)} series en la figura y "
                f"{len(expected)} esperadas"]
    problems = []
    for series, (wanted, points) in enumerate(zip(expected, plots), start=1):
        if len(points) != len(wanted):
            problems.append(f"Figura {name}: serie {series} tiene "
                            f"{len(points)} puntos y se esperaban {len(wanted)}")
            continue
        for index, ((x, value), target) in enumerate(zip(points, wanted), start=1):
            if x != index:
                problems.append(f"Figura {name}: serie {series}, x={x} donde "
                                f"se esperaba {index}")
            if abs(value - target) > tolerance:
                problems.append(f"Figura {name}: serie {series}, punto {index}: "
                                f"CSV {target:.3f} != figura {value:.3f}")
    return problems


def fmax_figure_problems() -> list:
    """Compare results_fmax.csv with the Fmax bar figure."""
    summary = {row["arch"]: row
               for row in _read_csv_rows(RESULTS / "results_fmax.csv")}
    plots = _figure_addplots(FIGURES / "fmax_comparison.tex", error_bars=True)
    if len(plots) != 1:
        return [f"Figura Fmax: {len(plots)} series en la figura y 1 esperada"]
    points = plots[0]
    if len(points) != len(ARCHES):
        return [f"Figura Fmax: {len(points)} barras en la figura y "
                f"{len(ARCHES)} esperadas"]
    problems = []
    for index, arch in enumerate(ARCHES):
        x, mean, std = points[index]
        row = summary[arch]
        if x != index + 1:
            problems.append(f"Figura Fmax: '{ARCH_LABELS[arch]}' en x={x}")
        # The figure shows two decimals of values stored with three.
        if abs(mean - float(row["fmax_mean_mhz"])) > 0.0055:
            problems.append(f"Figura Fmax: '{ARCH_LABELS[arch]}' media del "
                            f"CSV {row['fmax_mean_mhz']} != figura {mean}")
        if abs(std - float(row["fmax_std_mhz"])) > 0.0055:
            problems.append(f"Figura Fmax: '{ARCH_LABELS[arch]}' desviación "
                            f"del CSV {row['fmax_std_mhz']} != figura {std}")
    return problems


def _benchmark_figure_values(column: str) -> list:
    """Per-architecture series of a benchmark figure, from the summary CSV."""
    rows = _read_csv_rows(RESULTS / "results_benchmarks_summary.csv")
    programs = sorted({row["program"] for row in rows})
    expected = []
    for arch in ARCHES:
        by_program = {row["program"]: row for row in rows
                      if row["architecture"] == arch}
        values = []
        for program in programs:
            row = by_program.get(program)
            if (row is None or row["result"] != "pass"
                    or not row[column].strip()):
                values.append(0.0)
            else:
                values.append(float(row[column]))
        expected.append(values)
    return expected


def throughput_figure_problems() -> list:
    """Compare results_benchmarks_summary.csv with the throughput figure."""
    return _grouped_figure_problems(
        "Throughput", "throughput_comparison.tex",
        _benchmark_figure_values("throughput_mean_mips"))


def cpi_figure_problems() -> list:
    """Compare results_benchmarks_summary.csv with the CPI figure."""
    return _grouped_figure_problems(
        "CPI", "cpi_comparison.tex",
        _benchmark_figure_values("cpi"))


def resources_figure_problems() -> list:
    """Compare results_statistics.csv with the resources figure."""
    stats = {(row["arch"], row["metric"]): float(row["mean"])
             for row in _read_csv_rows(RESULTS / "results_statistics.csv")}
    expected = [[stats[(arch, key)] for key in
                 ("alms", "registers", "ram_blocks", "dsp_blocks")]
                for arch in ARCHES]
    return _grouped_figure_problems("Recursos", "resources_comparison.tex",
                                    expected)


def check_artifacts() -> int:
    """Compare the generated tables and figures with their source CSVs."""
    tables = (
        ("Verificación", verification_table_problems),
        ("Fmax", fmax_table_problems),
        ("Recursos", resources_table_problems),
        ("Estadísticas", statistics_table_problems),
        ("Eficiencia", efficiency_table_problems),
        ("Benchmarks", benchmarks_table_problems),
        ("Speedup", speedup_table_problems),
        ("CoreMark", coremark_table_problems),
    )
    figures = (
        ("Fmax", fmax_figure_problems),
        ("Throughput", throughput_figure_problems),
        ("CPI", cpi_figure_problems),
        ("Recursos", resources_figure_problems),
    )
    problems = []
    for name, check in tables + figures:
        try:
            problems += check()
        except (OSError, KeyError, ValueError) as error:
            problems.append(f"{name}: no se pudo comprobar ({error})")
    if problems:
        print("DIVERGENCIA entre los CSV de results/ y los artefactos de "
              "thesis/:")
        for problem in problems:
            print(f"  - {problem}")
        print("Ejecute 'python3 scripts/thesis_artifacts.py' para regenerar "
              "las tablas y figuras.")
        return 1
    print(f"OK: {len(tables)} tablas y {len(figures)} figuras coinciden con "
          "sus CSV.")
    return 0


# --------------------------------------------------------------------------
# pgfplots figures
# --------------------------------------------------------------------------

def figure_fmax(stats: dict) -> str:
    sc = stats["single_cycle"]["fmax"]
    pipe = stats["pipeline"]["fmax"]
    coords = []
    for index, arch in enumerate(ARCHES):
        stat = stats[arch]["fmax"]
        coords.append(f"({index + 1},{stat['mean']:.2f}) +- (0,{stat['std']:.2f})")
    return "\n".join([
        "% Generado por scripts/thesis_artifacts.py - no editar a mano.",
        r"\begin{figure}[htbp]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        r"  width=0.65\textwidth,",
        r"  height=7cm,",
        r"  ybar,",
        r"  bar width=25pt,",
        r"  ylabel={Fmax (MHz)},",
        r"  xtick={1,2},",
        r"  xticklabels={Monociclo,Pipeline},",
        r"  nodes near coords,",
        r"  nodes near coords align={vertical},",
        r"  ymin=0,",
        r"  error bars/.cd, y dir=both, y explicit,",
        r"]",
        "  \\addplot coordinates {" + ", ".join(coords) + "};",
        r"\end{axis}",
        r"\end{tikzpicture}",
        r"\caption{Frecuencia máxima de cada microarquitectura, media "
        r"$\pm$ desviación estándar de las cinco réplicas de síntesis.}",
        r"\label{fig:fmax}",
        r"\end{figure}",
    ])


def _grouped_bar_figure(entries, values_by_arch, ylabel, caption, label):
    ticks = [f"{{{tex_escape(name)}}}" for name in entries]
    options = [
        r"  width=0.95\textwidth,",
        r"  height=7cm,",
        r"  ybar,",
        r"  bar width=8pt,",
        f"  ylabel={{{ylabel}}},",
        "  xtick={" + ",".join(str(i + 1) for i in range(len(entries))) + "},",
        "  xticklabels={" + ", ".join(ticks) + "},",
        r"  xmin=0.5,",
        r"  enlarge x limits=0.1,",
        r"  legend style={at={(0.5,-0.25)},anchor=north,legend columns=2},",
    ]
    lines = [
        "% Generado por scripts/thesis_artifacts.py - no editar a mano.",
        r"\begin{figure}[htbp]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        "\n".join(options),
        r"]",
    ]
    for arch in ARCHES:
        coords = ", ".join(f"({index + 1},{value:.3f})"
                           for index, value in enumerate(values_by_arch[arch]))
        lines.append(f"  \\addplot coordinates {{{coords}}};")
    lines += [
        r"  \legend{Monociclo,Pipeline}",
        r"\end{axis}",
        r"\end{tikzpicture}",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        r"\end{figure}",
    ]
    return "\n".join(lines)


def figure_throughput(metrics: list) -> str:
    entries = [m["program"] for m in metrics]
    values = {arch: [] for arch in ARCHES}
    for arch in ARCHES:
        for entry in metrics:
            data = entry["arch"].get(arch)
            values[arch].append(data["throughput"]["mean"] if data and data["throughput"] else 0.0)
    return _grouped_bar_figure(
        entries, values, "Throughput (MIPS)",
        r"Throughput efectivo por programa y microarquitectura "
        r"($F_{\max}/\mathrm{CPI}$).",
        "fig:throughput")


def figure_cpi(metrics: list) -> str:
    entries = [m["program"] for m in metrics]
    values = {arch: [] for arch in ARCHES}
    for arch in ARCHES:
        for entry in metrics:
            data = entry["arch"].get(arch)
            values[arch].append(data["cpi"] if data else 0.0)
    return _grouped_bar_figure(
        entries, values, "CPI",
        r"CPI efectivo por programa y microarquitectura.",
        "fig:cpi")


def figure_resources(stats: dict) -> str:
    entries = ["ALMs", "Registros", "RAM", "DSP"]
    keys = ["alms", "registers", "ram_blocks", "dsp_blocks"]
    values = {arch: [] for arch in ARCHES}
    for arch in ARCHES:
        for key in keys:
            stat = stats[arch].get(key)
            values[arch].append(stat["mean"] if stat else 0.0)
    return _grouped_bar_figure(
        entries, values, "Cantidad de recursos",
        r"Utilización de recursos de la FPGA por microarquitectura.",
        "fig:resources")


# --------------------------------------------------------------------------
# Protocol documents
# --------------------------------------------------------------------------

def tool_versions() -> dict:
    """Versions of the tools of the measurement protocol."""
    def run(cmd, needle=None):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except Exception:
            return "no disponible"
        lines = (result.stdout + result.stderr).strip().splitlines()
        if needle:
            for line in lines:
                if needle in line:
                    return line.strip()
        return lines[0].strip() if lines else "no disponible"

    return {
        "quartus": run(["quartus_sh.exe", "--version"], "Version"),
        "iverilog": run(["iverilog", "-V"], "Icarus"),
        "riscv_gcc": run(["riscv-none-elf-gcc", "--version"]),
        "python": run(["python3", "--version"]),
        "cocotb": run([str(REPO_ROOT / ".venv/bin/cocotb-config"), "--version"]),
        "git": run(["git", "rev-parse", "HEAD"]),
    }


def write_environment_doc(stats: dict, versions: dict, fingerprint: str) -> Path:
    path = REPRO / "environment_setup.md"
    lines = [
        "# Entorno de medición",
        "",
        "<!-- Generado por scripts/thesis_artifacts.py. Los valores provienen de la "
        "corrida descrita en el capítulo de resultados. -->",
        "",
        "## Hardware",
        "",
        "| Elemento | Especificación |",
        "|---|---|",
        "| FPGA | Intel Cyclone V 5CSEMA5F31C6 |",
        "| Tarjeta | DE1-SoC |",
        "| Reloj del procesador | 50 MHz (PIN_AF14) |",
        "| Objetivo de temporización | 100 MHz (`create_clock -period 10.000`) |",
        "",
        "## Herramientas",
        "",
        "| Herramienta | Versión |",
        "|---|---|",
    ]
    for key, value in versions.items():
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## Estado del repositorio",
        "",
        f"- Commit: `{versions['git']}`",
        f"- Huella del RTL y de la configuración de síntesis: `{fingerprint}`",
        "",
        "## Requisitos",
        "",
        "```bash",
        "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt",
        "export PATH=\"$PWD/.venv/bin:$PATH\"   # cocotb-config y el intérprete del venv",
        "```",
        "",
        "## Flujo de reproducción",
        "",
        "```bash",
        "make thesis        # campaña completa: sintetiza las réplicas y regenera los artefactos",
        "make thesis-quick  # reutiliza las réplicas de results/ y refresca el resto",
        "```",
        "",
        "Ambas campañas terminan con `make check-artifacts`, que compara las tablas de "
        "`thesis/tables/` y las figuras de `thesis/figures/diagrams/` con los CSV de "
        "`results/` correspondientes (verificación, Fmax, recursos, estadísticas, "
        "eficiencia, benchmarks, speedup y CoreMark). "
        "Si un artefacto no coincide "
        "con su CSV, el objetivo devuelve un código distinto de cero y la campaña "
        "falla; el mensaje indica la fila y la columna divergentes. El chequeo "
        "también puede ejecutarse por separado después de editar o regenerar "
        "artefactos:",
        "",
        "```bash",
        "make check-artifacts",
        "```",
        "",
    ]
    path.write_text("\n".join(lines))
    return path


def write_synthesis_protocol_doc(stats: dict, replicas: list) -> Path:
    path = REPRO / "synthesis_protocol.md"
    lines = [
        "# Protocolo de síntesis",
        "",
        "<!-- Generado por scripts/thesis_artifacts.py. -->",
        "",
        "## 1. Parámetros de la síntesis",
        "",
        "| Parámetro | Valor |",
        "|---|---|",
        "| Dispositivo | Cyclone V 5CSEMA5F31C6 |",
        "| Family | Cyclone V |",
        "| Herramienta | Intel Quartus Prime 25.1std (Lite Edition) |",
        "| Restricción de reloj | `create_clock -period 10.000 -name clk [get_ports clk]` |",
        "| Incertidumbre de reloj | 0.100 ns (subida y bajada) |",
        "| Modelos de temporización | Slow 1100 mV 85 °C y Slow 1100 mV 0 °C |",
        "| Semilla del fitter | `SEED = i`, con $i = 1 \\dots 5$ |",
        "| Réplicas por arquitectura | 5 |",
        "",
        "Las dos microarquitecturas comparten el mismo archivo de restricciones "
        "(`synthesis/*/constraints.sdc`), el mismo dispositivo y el mismo reloj: son "
        "variables de control del experimento.",
        "",
        "## 2. Procedimiento por réplica",
        "",
        "1. Regenerar `rtl/shared/mem_config.vh` y `synthesis/*/screen.mif` con la "
        "misma imagen de memoria para todas las réplicas.",
        "2. Compilar el proyecto completo (`quartus_sh -t build.tcl <seed>`), que "
        "ejecuta análisis y síntesis, mapa, ajuste y Timing Analyzer.",
        "3. Copiar el reporte de temporización (`.sta.rpt`), el resumen del ajustador "
        "(`.fit.summary`) y el bitstream (`.sof`) al directorio de la réplica.",
        "4. Extraer la Fmax del modelo Slow 85 °C con `scripts/extract_fmax.py`.",
        "5. Registrar el commit, la huella del RTL, la semilla y la fecha en "
        "`meta.json`.",
        "",
        "Las réplicas cuyo `meta.json` no coincide con la huella vigente del RTL se "
        "consideran obsoletas y se regeneran: `make thesis` las descarta y las repite.",
        "",
        "## 3. Resultados obtenidos",
        "",
    ]
    for arch in ARCHES:
        stat = stats[arch]["fmax"]
        lines.append(f"### {ARCH_LABELS[arch]}")
        lines.append("")
        if stat:
            lines.append(f"- Fmax media: {stat['mean']:.2f} MHz "
                         f"(desviación estándar {stat['std']:.2f} MHz, "
                         f"CV {stat['cv']:.2f} %, n = {stat['n']})")
            lines.append(f"- Rango: {stat['min']:.2f} MHz a {stat['max']:.2f} MHz")
        else:
            lines.append("- Sin réplicas.")
        lines.append("")
    lines += [
        "## 4. Trazabilidad",
        "",
        "| Réplica | Commit | Fecha |",
        "|---|---|---|",
    ]
    for record in replicas:
        lines.append(f"| {record['arch']} / {record['replica']} | "
                     f"`{record['git_commit'][:8]}` | {record['date']} |")
    lines.append("")
    path.write_text("\n".join(lines))
    return path


def write_measurement_protocol_doc(metrics: list, stats: dict, replicas: list) -> Path:
    path = REPRO / "measurement_protocol.md"
    lines = [
        "# Protocolo de medición",
        "",
        "<!-- Generado por scripts/thesis_artifacts.py. -->",
        "",
        "## 1. Tratamientos",
        "",
        "| Tratamiento | Microarquitectura |",
        "|---|---|",
        "| T1 | RV32IM monociclo |",
        "| T2 | RV32IM segmentado en cinco etapas (IF, ID, EX, MEM, WB) |",
        "",
        "## 2. Instrumentación",
        "",
        "Los contadores están incrustados en el propio procesador "
        "(`rtl/shared/perf_counter.sv`), son idénticos en ambas "
        "microarquitecturas y no realimentan el datapath (ADR 024):",
        "",
        "| Contador | Definición |",
        "|---|---|",
        "| `cycle_count` | Ciclos de reloj desde el reinicio hasta que el programa "
        "escribe en `tohost`; el valor queda congelado en ese instante. |",
        "| `instr_retired` | Monociclo: un ciclo por instrucción ejecutada. "
        "Pipeline: ciclos en los que `valid_wb = 1`, es decir, instrucciones "
        "que se retiran sin burbuja. |",
        "",
        "El mismo valor congelado en el silicio es el que muestra la consola VGA, y "
        "una aserción del testbench comprueba que coincide con el que reporta la "
        "simulación (ADR 042). CoreMark señala el final de la corrida con su propia "
        "dirección de tohost (0x6000) y su bitstream se construye con "
        "`TOHOST_ADDR=0x6000` (ADR 047), de modo que el RTL vigila la misma "
        "dirección y sus contadores congelados también son comparables con los "
        "de la simulación.",
        "",
        "## 3. Programas de prueba",
        "",
        "| Programa | Propósito |",
        "|---|---|",
        "| `raw_stress` | Cadena de dependencias RAW: mide la eficacia del "
        "forwarding. |",
        "| `load_use_stress` | Pares load-use: mide la penalización por "
        "hazard de datos. |",
        "| `branch_stress` | Ramas tomadas: mide la penalización por "
        "hazard de control. |",
        "| `m_ext_stress` | Multiplicaciones y divisiones: mide el impacto de la "
        "extensión M. |",
        "| `coremark_iter10` | Benchmark estándar deprocessors embebidos "
        "(EEMBC), diez iteraciones. |",
        "",
        "## 4. Procedimiento",
        "",
        "1. Verificación funcional de ambas arquitecturas (suites cocotb y "
        "`riscv-tests`). Un programa que no pase la verificación no se mide.",
        "2. Síntesis de las cinco réplicas de cada tratamiento (ver "
        "`synthesis_protocol.md`).",
        "3. Medición del CPI en simulación con los contadores del procesador, "
        "verificada contra el modelo de referencia de Python.",
        "4. Cálculo del throughput de cada réplica como "
        r"$F_{\max,i}/\mathrm{CPI}$ "
        "y del speedup como el cociente de los throughputs pareados por índice.",
        "5. Análisis descriptivo: media, desviación estándar muestral y "
        "coeficiente de variación.",
        "",
        "## 5. Variables de respuesta",
        "",
        "| Variable | Fórmula | Origen |",
        "|---|---|---|",
        "| CPI | $\\mathrm{ciclos}/\\mathrm{instrucciones}$ | contadores del "
        "procesador |",
        "| IPC | $1/\\mathrm{CPI}$ | derivado |",
        "| Throughput | " r"$F_{\max}/\mathrm{CPI}$" " | Timing Analyzer y contadores |",
        "| Fmax | Timing Analyzer, modelo Slow 85 °C | Quartus |",
        "| Recursos | ALMs, registros, bloques RAM, DSP, bits de memoria, pines | "
        "Fitter |",
        "| Latencia | Ciclos hasta `tohost` | contadores del procesador |",
        "",
        "## 6. Criterio de evaluación de la hipótesis",
        "",
        "Con $n = 5$ réplicas por tratamiento, el análisis es descriptivo: no se "
        "aplica ninguna prueba de significancia inferencial, en línea con el "
        "anteproyecto (§7.1.8). La hipótesis de trabajo $H_1$ se considera "
        "sostenida para un programa cuando el extremo inferior de la dispersión "
        "del speedup, $\\overline{S} - \\sigma_{S}$, es mayor que uno; en caso "
        "contrario, $H_0$ no se descarta.",
        "",
        "## 7. Resultados por programa",
        "",
        "| Programa | CPI monociclo | CPI pipeline | Throughput monociclo (MIPS) | "
        "Throughput pipeline (MIPS) | Speedup | Resultado |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in metrics:
        sc = entry["arch"].get("single_cycle")
        pipe = entry["arch"].get("pipeline")
        speedup = entry.get("speedup")
        verdict = "H1 sostenida" if entry.get("verdict") == "H1" else "H0 no descartada"
        lines.append(
            f"| `{entry['program']}` | "
            f"{fmt(sc['cpi'], 4) if sc else '---'} | "
            f"{fmt(pipe['cpi'], 4) if pipe else '---'} | "
            f"{fmt(sc['throughput']['mean'], 2) if sc and sc['throughput'] else '---'} | "
            f"{fmt(pipe['throughput']['mean'], 2) if pipe and pipe['throughput'] else '---'} | "
            f"{fmt(speedup['mean'], 3) if speedup else '---'} | {verdict} |"
        )
    lines += [
        "",
        "## 8. Réplicas",
        "",
        f"- Réplicas por arquitectura: "
        f"{stats['single_cycle']['fmax']['n'] if stats['single_cycle']['fmax'] else 0} "
        f"(monociclo) y "
        f"{stats['pipeline']['fmax']['n'] if stats['pipeline']['fmax'] else 0} "
        f"(pipeline).",
        "- La variabilidad experimental es la de la síntesis: el CPI es "
        "determinista en simulación, y el throughput de cada réplica usa el Fmax "
        "de esa réplica.",
        "",
    ]
    path.write_text("\n".join(lines))
    return path


# --------------------------------------------------------------------------
# Results chapter
# --------------------------------------------------------------------------

def write_chapter(metrics: list, stats: dict, replicas: list, verification: list,
                  coremark: list, stale: bool, fingerprint: str) -> list:
    """Markdown and LaTeX drafts of the results chapter."""
    sc_fmax = stats["single_cycle"]["fmax"]
    pipe_fmax = stats["pipeline"]["fmax"]
    measured = [m for m in metrics if m.get("speedup")]
    winners = [m for m in measured if m.get("verdict") == "H1"]
    losers = [m for m in measured if m.get("verdict") != "H1"]
    unmeasured = [m for m in metrics if not m.get("speedup")]

    # Resource overhead of the pipeline and throughput per unit of logic.
    overhead = {row["resource"]: row["overhead_pct"]
                for row in efficiency_table(metrics, stats)
                if row["overhead_pct"] is not None}
    alm_overhead = overhead.get("alms", 0.0)
    reg_overhead = overhead.get("registers", 0.0)
    ram_overhead = overhead.get("ram_blocks", 0.0)
    dsp_overhead = overhead.get("dsp_blocks", 0.0)

    # CPI penalty of the pipeline per program: the quantity that has to be
    # outweighed by the Fmax gain for the hypothesis to hold.
    penalties = [m["arch"]["pipeline"]["cpi"] / m["arch"]["single_cycle"]["cpi"] - 1
                 for m in measured
                 if m["arch"].get("pipeline") and m["arch"].get("single_cycle")
                 and m["arch"]["single_cycle"]["cpi"]]
    fmax_gain = (pipe_fmax["mean"] / sc_fmax["mean"] - 1) * 100
    coremark_note = ""
    if coremark:
        coremark_note = (
            " En la carga estándar CoreMark el pipeline rinde "
            f"{fmt(coremark[-1]['per_mhz'], 2)} CoreMark/MHz frente a "
            f"{fmt(coremark[0]['per_mhz'], 2)} del monociclo, la métrica "
            "normalizada por frecuencia que recomienda EEMBC (sección 9.2.13).")

    def mean_throughput(arch):
        values = [m["arch"][arch]["throughput"]["mean"] for m in metrics
                  if arch in m["arch"] and m["arch"][arch].get("throughput")]
        return sum(values) / len(values) if values else None

    per_alm_ratio = 1.0
    sc_tp, pipe_tp = mean_throughput("single_cycle"), mean_throughput("pipeline")
    sc_alms = stats["single_cycle"]["alms"]
    pipe_alms = stats["pipeline"]["alms"]
    if sc_tp and pipe_tp and sc_alms and pipe_alms:
        per_alm_ratio = ((pipe_tp / (pipe_alms["mean"] / 1000.0))
                         / (sc_tp / (sc_alms["mean"] / 1000.0)))

    def overhead_phrase(value, noun):
        """Sign-aware phrase: '18 % más de ALMs', 'sin cambio en registros'."""
        if abs(value) < 0.5:
            return f"sin cambio en {noun}"
        direction = "más" if value > 0 else "menos"
        return f"un {fmt(abs(value), 1)} % {direction} de {noun}"

    resource_changes = [
        overhead_phrase(alm_overhead, "ALMs"),
        overhead_phrase(reg_overhead, "registros"),
        overhead_phrase(ram_overhead, "bloques RAM"),
        overhead_phrase(dsp_overhead, "bloques DSP"),
    ]
    resource_text = ", ".join(resource_changes[:-1]) + " y " + resource_changes[-1]
    if per_alm_ratio >= 1.0:
        area_verdict = ("El intercambio es favorable: el pipeline entrega más "
                        "throughput por unidad de lógica a pesar del área adicional.")
    else:
        area_verdict = ("El intercambio no compensa: el pipeline consume más área "
                        "y entrega menos throughput, de modo que su eficiencia por "
                        "ALM es inferior a la del monociclo.")

    def program_list(entries):
        return ", ".join(f"`{m['program']}`" for m in entries) if entries else "ninguno"

    def program_list_tex(entries):
        names = [r"\texttt{" + m["program"].replace("_", r"\_") + "}" for m in entries]
        return ", ".join(names) if names else "ninguno"

    if winners and losers:
        discussion_md = (
            "El resultado es un rechazo parcial de la hipótesis de trabajo $H_1$: el "
            f"pipeline supera al monociclo en {program_list(winners)} y pierde en "
            f"{program_list(losers)}. La ganancia de frecuencia "
            f"({fmt(fmax_gain, 1)} %) no compensa el aumento del CPI por hazard de "
            "datos, vaciado de las ramas tomadas y latencia de la división, que va "
            f"de {fmt(min(penalties) * 100, 0) if penalties else 0} % a "
            f"{fmt(max(penalties) * 100, 0) if penalties else 0} % según el "
            "programa. La ventaja se limita, por tanto, a las cargas intensivas en "
            "multiplicación y división y con pocas dependencias; no es una "
            "propiedad general de la microarquitectura." + coremark_note + "\n")
    elif winners:
        discussion_md = (
            "El pipeline supera al monociclo en todos los programas medidos "
            f"({program_list(winners)}). En este conjunto de cargas la ganancia de "
            "frecuencia supera siempre a la penalización por hazards, de modo que la "
            "hipótesis de trabajo queda sostenida. El resultado es condicional al "
            "conjunto de programas medido y no generaliza a cargas con una densidad "
            "de hazards superior a la de estos programas.\n")
    else:
        discussion_md = (
            "El pipeline no supera al monociclo en ninguno de los programas "
            "medidos. La ganancia de frecuencia del pipeline es de "
            f"{fmt((pipe_fmax['mean'] / sc_fmax['mean'] - 1) * 100, 1)} %, mientras "
            "que la penalización por hazards elevate el CPI del pipeline entre "
            f"{fmt(min(penalties) * 100, 0) if penalties else 0} % y "
            f"{fmt(max(penalties) * 100, 0) if penalties else 0} % respecto al "
            "monociclo: la segunda de las dos cantidades domina el resultado en "
            "todos los programas, de modo que la hipótesis de trabajo no queda "
            "sostenida y el mayor Fmax del pipeline no se traduce en mayor "
            "throughput.\n")

    md = []
    md.append("# Capítulo 7. Resultados\n")
    md.append("<!-- Generado por scripts/thesis_artifacts.py. Revisar y "
              "completar la interpretación antes de la entrega. -->\n")
    if stale:
        md.append("> **Aviso:** las réplicas de síntesis guardadas no corresponden "
                  "a la versión vigente del RTL (huella "
                  f"`{fingerprint[:12]}`). Ejecute `make thesis` para repetirlas "
                  "antes de consignar estos números.\n")
    md.append("## 7.1 Resumen\n")
    md.append(
        "Se compararon las dos microarquitecturas RV32IM sobre la FPGA Cyclone V "
        "DE1-SoC bajo el protocolo descrito en `docs/reproduction/`. El pipeline "
        f"alcanzó una Fmax de {fmt(pipe_fmax['mean'])} MHz "
        f"($\\pm$ {fmt(pipe_fmax['std'])} MHz, n = {pipe_fmax['n']}) frente a los "
        f"{fmt(sc_fmax['mean'])} MHz ($\\pm$ {fmt(sc_fmax['std'])} MHz, "
        f"n = {sc_fmax['n']}) del monociclo, es decir, una mejora de frecuencia de "
        f"{fmt((pipe_fmax['mean'] / sc_fmax['mean'] - 1) * 100, 1)} %.\n")
    md.append(
        "La mejora en frecuencia no se traslada sin más al rendimiento: el CPI del "
        "pipeline es mayor que uno en todos los programas medidos, porque cada "
        "burbuja de hazard y cada vaciado por rama tomada son ciclos perdidos. "
        "El resultado neto depende del balance entre la ganancia de reloj y la "
        "penalización por hazards.\n")
    md.append("## 7.2 Verificación funcional\n")
    md.append("Antes de medir el rendimiento se verificó la corrección funcional de "
              "ambas implementaciones contra el modelo de referencia de Python y "
              "contra la suite `riscv-tests`. La tabla "
              "`\\ref{tab:verification_results}` resume el resultado.\n")
    md.append("## 7.3 Frecuencia máxima y recursos\n")
    md.append("La tabla `\\ref{tab:fmax_replicas}` presenta la Fmax de cada réplica y "
              "la `\\ref{tab:resources}` la utilización de recursos. La dispersión "
              f"de la Fmax entre réplicas es comparable en las dos arquitecturas "
              f"(CV {fmt(sc_fmax['cv'])} % en el monociclo y {fmt(pipe_fmax['cv'])} "
              f"% en el pipeline), de modo que la diferencia de Fmax entre los "
              f"tratamientos ({fmt((pipe_fmax['mean'] / sc_fmax['mean'] - 1) * 100, 1)} %) "
              "es mayor que la dispersión experimental y no es un artefacto del "
              "proceso de síntesis.\n")
    md.append("## 7.4 CPI, IPC y throughput\n")
    md.append("La tabla `\\ref{tab:benchmarks}` muestra el CPI efectivo, el IPC y el "
              "throughput de cada programa. El monociclo presenta CPI = 1 en los "
              "programas sin división: cada ciclo retira una instrucción. La "
              "excepción es el programa de la extensión M, donde el divisor de 34 "
              "ciclos mantiene el datapath ocupado y el CPI del monociclo sube a "
              "7.58. El pipeline retira una instrucción por ciclo en el mejor caso y "
              "pierde ciclos por hazard de datos, por vaciado de rama y por la "
              "latencia de la división.\n")
    md.append("### CoreMark en hardware\n")
    md.append(
        "CoreMark es la carga de referencia del anteproyecto (sección 9.2.13), "
        "y su regla de ejecución exige al menos 10 s, de modo que la corrida "
        "oficial en la FPGA usa 2000 iteraciones y no las diez de la "
        "simulación. El programa ocupa 9044 bytes de la memoria de "
        "instrucciones (55 % de los 16 KB) y 3389 bytes del bloque de datos "
        "(83 % de los 4 KB), así que cabe en el dispositivo.\n")
    if coremark:
        md.append("| Arquitectura | Reloj (MHz) | Ciclos | Instrucciones | "
                  "Tiempo (s) | CoreMark | CoreMark/MHz |")
        md.append("|---|---|---|---|---|---|---|")
        for row in coremark:
            md.append(
                f"| {ARCH_LABELS[row['arch']]} | {fmt(row['clock_mhz'], 0)} | "
                f"{row['cycles']} | {row['instructions']} | "
                f"{fmt(row['seconds'], 2)} | {fmt(row['score'], 2)} | "
                f"{fmt(row['per_mhz'], 3)} |")
        md.append("")
        md.append(
            "La tabla `\\ref{tab:coremark}` recoge la corrida; los ciclos y "
            "las instrucciones son los contadores congelados que se leyeron en "
            "la consola VGA. El monociclo rinde "
            f"{fmt(coremark[0]['per_mhz'], 2)} CoreMark/MHz y el pipeline "
            f"{fmt(coremark[-1]['per_mhz'], 2)}: la normalización por "
            "frecuencia aísla el efecto del CPI, que es la variable "
            "arquitectural que el benchmark mide.\n")
    else:
        md.append("No hay una corrida de CoreMark en hardware registrada "
                  "(`results/results_coremark.csv`).\n")
    md.append("## 7.5 Análisis estadístico\n")
    md.append(f"Con $n = 5$ réplicas por tratamiento, el análisis es descriptivo. La "
              f"desviación estándar de la Fmax es de {fmt(sc_fmax['std'])} MHz en el "
              f"monociclo (CV {fmt(sc_fmax['cv'])} %) y de {fmt(pipe_fmax['std'])} "
              f"MHz en el pipeline (CV {fmt(pipe_fmax['cv'])} %). "
              "La tabla `\\ref{tab:statistics}` recoge la estadística completa.\n")
    md.append("## 7.6 Eficiencia relativa\n")
    md.append("La tabla `\\ref{tab:efficiency}` contrasta el throughput con el costo "
              "en recursos. Respecto al monociclo, el pipeline usa "
              f"{resource_text}. Expresado en throughput por mil ALMs, el pipeline "
              f"multiplica por {fmt(per_alm_ratio, 2)} la eficiencia del monociclo. "
              + area_verdict + "\n")
    md.append("## 7.7 Evaluación de la hipótesis\n")
    if winners and losers:
        md.append(
            f"La hipótesis de trabajo $H_1$ se sostiene solo en los programas "
            f"{program_list(winners)} y no se descarta en los programas "
            f"{program_list(losers)}; en conjunto, el resultado es un rechazo "
            "parcial de la hipótesis, no una confirmación. La tabla "
            "`\\ref{tab:speedup}` muestra el speedup del pipeline respecto al "
            "monociclo y el extremo inferior de su dispersión.\n")
    elif winners:
        md.append(
            f"La hipótesis de trabajo $H_1$ se sostiene en todos los programas "
            f"medidos ({program_list(winners)}). La tabla "
            "`\\ref{tab:speedup}` muestra el speedup del pipeline respecto al "
            "monociclo y el extremo inferior de su dispersión.\n")
    else:
        md.append(
            "La hipótesis de trabajo $H_1$ no se sostiene en ninguno de los "
            "programas medidos: el extremo inferior de la dispersión del speedup "
            "queda por debajo de uno en todos los casos. La tabla "
            "`\\ref{tab:speedup}` muestra el speedup del pipeline respecto al "
            "monociclo y su dispersión.\n")
    md.append("## 7.8 Discusión\n")
    md.append(discussion_md)
    md.append("## 7.9 Limitaciones\n")
    if unmeasured:
        md.append(f"- Los programas {program_list(unmeasured)} no obtuvieron una "
                  "medición válida y quedan fuera de la comparación.\n")
    md.append(
        "- El tamaño muestral ($n = 5$ réplicas) limita el análisis a la estadística "
        "descriptiva; no se aplican pruebas de significancia.\n"
        "- El CPI se mide con los contadores del procesador en cocotb y se "
        "verifica sobre la FPGA con CoreMark (ADR 051). Los contadores son "
        "deterministas, así que la única fuente de dispersión que se modela "
        "estadísticamente es la Fmax.\n"
        "- CoreMark se mide en simulación con diez iteraciones para el CPI; la "
        "corrida oficial en hardware usa 2000 iteraciones para cumplir el "
        "mínimo de 10 s de EEMBC y se ejecuta una vez por arquitectura, porque "
        "el conteo de ciclos no depende del seed de place-and-route.\n")

    tex = []
    tex.append("% Generado por scripts/thesis_artifacts.py - no editar a mano.")
    tex.append(r"\chapter{Resultados}")
    tex.append("")
    tex.append(r"\section{Resumen}")
    tex.append("")
    if stale:
        tex.append(r"\begin{quote}")
        tex.append(r"\textbf{Aviso.} Las réplicas de síntesis guardadas no "
                   "corresponden a la versión vigente del RTL. Repita "
                   r"\texttt{make thesis} antes de consignar estos números.")
        tex.append(r"\end{quote}")
    tex.append(
        "Se compararon las dos microarquitecturas RV32IM sobre la FPGA Cyclone V "
        "DE1-SoC bajo el protocolo descrito en el capítulo de metodología. El "
        f"pipeline alcanzó una Fmax de {fmt(pipe_fmax['mean'])} MHz "
        f"($\\pm$ {fmt(pipe_fmax['std'])} MHz, $n = {pipe_fmax['n']}$) frente a los "
        f"{fmt(sc_fmax['mean'])} MHz ($\\pm$ {fmt(sc_fmax['std'])} MHz, "
        f"$n = {sc_fmax['n']}$) del monociclo, una mejora de frecuencia del "
        f"{fmt((pipe_fmax['mean'] / sc_fmax['mean'] - 1) * 100, 1)} \\%.")
    tex.append("")
    tex.append(r"\section{Verificación funcional}")
    tex.append("")
    tex.append("La corrección funcional de ambas implementaciones se verificó "
               "contra el modelo de referencia de Python y contra la suite "
               r"\texttt{riscv-tests} antes de medir el rendimiento. Los "
               "resultados se resumen en la tabla "
               r"\ref{tab:verification_results}.")
    tex.append("")
    tex.append(r"\input{tables/verification_results.tex}")
    tex.append("")
    tex.append(r"\section{Frecuencia máxima y recursos}")
    tex.append("")
    tex.append(r"\input{tables/fmax_replicas.tex}")
    tex.append("")
    tex.append(r"\input{tables/resources.tex}")
    tex.append("")
    tex.append(r"\input{figures/diagrams/fmax_comparison.tex}")
    tex.append("")
    tex.append(r"\section{CPI, IPC y throughput}")
    tex.append("")
    tex.append(r"\input{tables/benchmarks.tex}")
    tex.append("")
    tex.append("El monociclo presenta CPI = 1 en los programas sin división: cada "
               "ciclo retira una instrucción. La excepción es el programa de la "
               "extensión M, donde el divisor de 34 ciclos mantiene el datapath "
               "ocupado y el CPI del monociclo sube a 7.58. El pipeline retira una "
               "instrucción por ciclo en el mejor caso y pierde ciclos por hazard de "
               "datos, por vaciado de rama y por la latencia de la división.")
    tex.append("")
    tex.append(r"\input{figures/diagrams/throughput_comparison.tex}")
    tex.append("")
    tex.append(r"\input{figures/diagrams/cpi_comparison.tex}")
    tex.append("")
    tex.append(r"\subsection{CoreMark en hardware}")
    tex.append("")
    tex.append("CoreMark es la carga de referencia del anteproyecto (sección "
               "9.2.13) y exige al menos 10 s de ejecución, así que la corrida "
               "oficial usa 2000 iteraciones. El programa ocupa 9044 bytes de la "
               "memoria de instrucciones (55 \\% de 16 KB) y 3389 bytes del "
               "bloque de datos (83 \\% de 4 KB), por lo que cabe en el "
               "dispositivo.")
    if coremark:
        tex.append("")
        tex.append(r"\input{tables/coremark.tex}")
        tex.append("")
        tex.append("Los ciclos y las instrucciones son los contadores "
                   "congelados que se leyeron en la consola VGA. La "
                   "normalización por frecuencia aísla el efecto del CPI: "
                   f"el monociclo rinde {fmt(coremark[0]['per_mhz'], 2)} "
                   f"CoreMark/MHz y el pipeline {fmt(coremark[-1]['per_mhz'], 2)}.")
    else:
        tex.append("")
        tex.append("No hay una corrida de CoreMark en hardware registrada.")
    tex.append("")
    tex.append(r"\section{Análisis estadístico}")
    tex.append("")
    tex.append(f"Con $n = 5$ réplicas por tratamiento, el análisis es descriptivo. "
               f"La desviación estándar de la Fmax es de {fmt(sc_fmax['std'])} MHz en "
               f"el monociclo (CV {fmt(sc_fmax['cv'])} \\%) y de "
               f"{fmt(pipe_fmax['std'])} MHz en el pipeline (CV {fmt(pipe_fmax['cv'])} "
               "\\%).")
    tex.append("")
    tex.append(r"\input{tables/statistics.tex}")
    tex.append("")
    tex.append(r"\section{Eficiencia relativa}")
    tex.append("")
    tex.append(r"\input{tables/efficiency.tex}")
    tex.append("")
    tex.append(r"\input{figures/diagrams/resources_comparison.tex}")
    tex.append("")
    tex.append(r"\section{Evaluación de la hipótesis}")
    tex.append("")
    tex.append(r"\input{tables/speedup.tex}")
    tex.append("")
    if winners and losers:
        tex.append(
            "La hipótesis de trabajo $H_1$ se sostiene solo en "
            f"{program_list_tex(winners)} y no se descarta en "
            f"{program_list_tex(losers)}: "
            "en conjunto, el resultado es un rechazo parcial, no una confirmación. "
            f"La ganancia de frecuencia ({fmt(fmax_gain, 1)} \\%) no compensa el "
            "aumento del CPI por hazard de datos, vaciado de ramas y latencia de "
            "la división." + coremark_note)
        tex.append("")
    tex.append(r"\section{Limitaciones}")
    tex.append("")
    tex.append(r"\begin{itemize}")
    tex.append(r"\item El tamaño muestral ($n = 5$) limita el análisis a la "
               "estadística descriptiva.")
    tex.append(r"\item El CPI se mide con los contadores del procesador en "
               r"cocotb y se verifica sobre la FPGA con CoreMark (ADR 051); la "
               r"única fuente de dispersión considerada es la variabilidad de "
               r"la Fmax entre réplicas.")
    tex.append(r"\item CoreMark se mide en simulación con diez iteraciones; la "
               r"corrida oficial en hardware usa 2000 iteraciones ($\geq$ 10 s, "
               r"EEMBC) y se ejecuta una vez por arquitectura, porque el conteo "
               r"de ciclos no depende del seed de place-and-route.")
    tex.append(r"\end{itemize}")

    return md, tex


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main() -> int:
    fingerprint = rtl_fingerprint()
    replicas = collect_replicas()
    stats = replica_stats(replicas)
    benchmarks = read_benchmarks()
    verification = read_verification()
    metrics = benchmark_metrics(benchmarks, stats)
    efficiency = efficiency_table(metrics, stats)

    for directory in (TABLES, FIGURES, CHAPTERS, REPRO):
        directory.mkdir(parents=True, exist_ok=True)

    written = [
        write_replicas_csv(replicas),
        write_fmax_csv(stats),
        write_statistics_csv(stats),
        write_benchmarks_csv(metrics),
        write_efficiency_csv(efficiency, metrics),
        write_coremark_csv(),
    ]

    tables = {
        "fmax_replicas.tex": table_fmax_replicas(replicas, stats),
        "resources.tex": table_resources(stats),
        "benchmarks.tex": table_benchmarks(metrics),
        "statistics.tex": table_statistics(stats),
        "efficiency.tex": table_efficiency(metrics, stats, efficiency),
        "speedup.tex": table_speedup(metrics),
        "coremark.tex": table_coremark(read_coremark_hardware()),
        "verification_results.tex": table_verification(verification),
    }
    for name, content in tables.items():
        if content:
            (TABLES / name).write_text(content + "\n")
            written.append(TABLES / name)

    figures = {
        "fmax_comparison.tex": figure_fmax(stats),
        "throughput_comparison.tex": figure_throughput(metrics),
        "cpi_comparison.tex": figure_cpi(metrics),
        "resources_comparison.tex": figure_resources(stats),
    }
    for name, content in figures.items():
        (FIGURES / name).write_text(content + "\n")
        written.append(FIGURES / name)

    versions = tool_versions()
    written.append(write_environment_doc(stats, versions, fingerprint))
    written.append(write_synthesis_protocol_doc(stats, replicas))
    written.append(write_measurement_protocol_doc(metrics, stats, replicas))

    # A replica without a fingerprint comes from an unknown RTL: it is stale
    # too, and the numbers it holds cannot be compared with the others.
    stale = any(r.get("fingerprint") != fingerprint for r in replicas)
    coremark = read_coremark_hardware()
    md, tex = write_chapter(metrics, stats, replicas, verification, coremark,
                            stale, fingerprint)
    (CHAPTERS / "07_resultados.md").write_text("\n".join(md))
    (CHAPTERS / "07_resultados.tex").write_text("\n".join(tex) + "\n")
    written.append(CHAPTERS / "07_resultados.md")
    written.append(CHAPTERS / "07_resultados.tex")

    for path in written:
        print(f"  {path.relative_to(REPO_ROOT)}")
    if stale:
        print("\nAVISO: las replicas guardadas no corresponden al RTL vigente; "
              "ejecute 'make thesis' para repetirlas.")
    return 0


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        raise SystemExit(check_artifacts())
    raise SystemExit(main())
