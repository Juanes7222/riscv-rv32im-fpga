#!/usr/bin/env python3
"""Turn the collected measurements into thesis-ready artifacts.

Reads the raw data of the experiment (the replica directories and the
benchmark CSV) and writes the statistics, the LaTeX tables, the pgfplots
figures, the protocol documents and the results chapter.

Usage:
    python3 scripts/thesis_artifacts.py
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
    by_suite = {}
    for row in rows:
        by_suite.setdefault(row["suite"], {})[row["arch"]] = row
    for suite, per_arch in by_suite.items():
        cells = []
        for arch in ARCHES:
            row = per_arch.get(arch)
            if not row:
                cells += [r"\textemdash"] * 3
                continue
            failed = int(row["failed"]) + int(row["errors"])
            failed_str = (r"\textcolor{red}{" + str(failed) + "}") if failed else "0"
            cells += [str(row["passed"]), failed_str, str(row["total"])]
        lines.append(f"{tex_escape(TEST_SUITE_NAMES.get(suite, suite))} & "
                     + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


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
        "simulación (ADR 042). CoreMark es la excepción: señala el final de la "
        "corrida con su propia dirección de tohost (0x5000), distinta de la que "
        "vigila el RTL (0x708), y por tanto sus contadores congelados no son "
        "comparables con los de la simulación.",
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
                  stale: bool, fingerprint: str) -> list:
    """Markdown and LaTeX drafts of the results chapter."""
    sc_fmax = stats["single_cycle"]["fmax"]
    pipe_fmax = stats["pipeline"]["fmax"]
    measured = [m for m in metrics if m.get("speedup")]
    winners = [m for m in measured if m.get("verdict") == "H1"]
    losers = [m for m in measured if m.get("verdict") != "H1"]
    unmeasured = [m for m in metrics if not m.get("speedup")]

    def program_list(entries):
        return ", ".join(f"`{m['program']}`" for m in entries) if entries else "ninguno"

    if winners and losers:
        discussion_md = (
            "El resultado no es uniforme: el pipeline supera al monociclo en los "
            f"programas {program_list(winners)} y no lo hace en {program_list(losers)}. "
            "La ganancia de reloj se compensa con la penalización por hazards de "
            "datos, por el vaciado de las ramas tomadas y por la latencia de la "
            "división, de modo que la hipótesis de trabajo, enunciada de forma "
            "general, queda confirmada solo bajo la condición de carga del programa "
            "medido: es un resultado condicional, no una propiedad de la "
            "microarquitectura.\n")
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
            "El pipeline no supera al monociclo en ninguno de los programas medidos. "
            "En este conjunto de cargas la penalización por hazards supera siempre a "
            "la ganancia de frecuencia, de modo que la hipótesis de trabajo no queda "
            "sostenida: el mayor Fmax del pipeline no se traduce en mayor "
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
              "la `\\ref{tab:resources}` la utilización de recursos. La "
              "dispersión de la Fmax entre réplicas es baja en el monociclo y "
              "moderada en el pipeline, lo que es coherente con la mayor libertad "
              "de placement que deja una ruta crítica repartida en cinco "
              "etapas.\n")
    md.append("## 7.4 CPI, IPC y throughput\n")
    md.append("La tabla `\\ref{tab:benchmarks}` muestra el CPI efectivo, el IPC y el "
              "throughput de cada programa. El monociclo presenta CPI = 1 en los "
              "programas sin división: cada ciclo retira una instrucción. La "
              "excepción es el programa de la extensión M, donde el divisor de 34 "
              "ciceles mantiene el datapath ocupado y el CPI del monociclo sube a "
              "7.58. El pipeline retira una instrucción por ciclo en el mejor caso y "
              "pierde ciclos por hazard de datos, por vaciado de rama y por la "
              "latencia de la división.\n")
    md.append("## 7.5 Análisis estadístico\n")
    md.append(f"Con $n = 5$ réplicas por tratamiento, el análisis es descriptivo. La "
              f"desviación estándar de la Fmax es de {fmt(sc_fmax['std'])} MHz en el "
              f"monociclo (CV {fmt(sc_fmax['cv'])} %) y de {fmt(pipe_fmax['std'])} "
              f"MHz en el pipeline (CV {fmt(pipe_fmax['cv'])} %). "
              "La tabla `\\ref{tab:statistics}` recoge la estadística completa.\n")
    md.append("## 7.6 Eficiencia relativa\n")
    md.append("La tabla `\\ref{tab:efficiency}` contrasta el throughput con el costo "
              "en recursos. El pipeline mejora el throughput con un número de "
              "recursos que depende del tipo de recurso considerado, de modo que "
              "la evaluación del intercambio entre rendimiento y área debe "
              "hacerse recurso a recurso.\n")
    md.append("## 7.7 Evaluación de la hipótesis\n")
    md.append(
        f"La hipótesis de trabajo $H_1$ se sostiene en los programas "
        f"{program_list(winners)} y no se descarta en los programas "
        f"{program_list(losers)}. La tabla `\\ref{{tab:speedup}}` muestra el speedup "
        "del pipeline respecto al monociclo y el extremo inferior de su "
        "dispersión.\n")
    md.append("## 7.8 Discusión\n")
    md.append(discussion_md)
    md.append("## 7.9 Limitaciones\n")
    if unmeasured:
        md.append(f"- Los programas {program_list(unmeasured)} no obtuvieron una "
                  "medición válida y quedan fuera de la comparación.\n")
    md.append(
        "- El tamaño muestral ($n = 5$ réplicas) limita el análisis a la estadística "
        "descriptiva; no se aplican pruebas de significancia.\n"
        "- El CPI se mide en simulación, no sobre la FPGA: es el mismo valor que "
        "congela el hardware, pero la variabilidad de la Fmax es la única fuente "
        "de dispersión considerada.\n"
        "- CoreMark se mide con diez iteraciones para que la corrida termine en "
        "minutos; la mezcla de instrucciones, y por tanto el CPI, es la misma "
        "que con la corrida completa.\n"
        "- CoreMark no cabe en la memoria de instrucciones de la FPGA, por lo que "
        "no se midió en hardware (ADR 042).\n")

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
    tex.append(r"\section{Limitaciones}")
    tex.append("")
    tex.append(r"\begin{itemize}")
    tex.append(r"\item El tamaño muestral ($n = 5$) limita el análisis a la "
               "estadística descriptiva.")
    tex.append(r"\item El CPI se mide en simulación; la única fuente de dispersión "
               "considerada es la variabilidad de la Fmax entre réplicas.")
    tex.append(r"\item CoreMark se mide con diez iteraciones; la mezcla de "
               "instrucciones, y por tanto el CPI, es la de la corrida completa.")
    tex.append(r"\item CoreMark no cabe en la memoria de instrucciones de la FPGA, "
               "por lo que no se midió en hardware.")
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
    ]

    tables = {
        "fmax_replicas.tex": table_fmax_replicas(replicas, stats),
        "resources.tex": table_resources(stats),
        "benchmarks.tex": table_benchmarks(metrics),
        "statistics.tex": table_statistics(stats),
        "efficiency.tex": table_efficiency(metrics, stats, efficiency),
        "speedup.tex": table_speedup(metrics),
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
    md, tex = write_chapter(metrics, stats, replicas, verification, stale, fingerprint)
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
    raise SystemExit(main())
