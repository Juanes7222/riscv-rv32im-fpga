#!/usr/bin/env python3
"""Turn the collected measurements into thesis-ready artifacts.

Reads the raw data of the experiment (the replica directories and the
benchmark CSV) and writes the statistics, the LaTeX tables, the pgfplots
figures. The report orchestrator publishes these in an isolated bundle.
It does not rewrite methodology prose: the chapter text is
written by hand around the generated tables and figures.

Usage:
    python3 scripts/thesis_artifacts.py            # regenerate every artifact
    python3 scripts/thesis_artifacts.py --check    # tables vs CSV check
"""

import csv
import math
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
from campaign_state import source_fingerprint  # noqa: E402
INPUT_RESULTS = REPO_ROOT / "results"
RESULTS = INPUT_RESULTS
TABLES = REPO_ROOT / "thesis" / "tables"
FIGURES = REPO_ROOT / "thesis" / "figures" / "diagrams"
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
    """SHA-256 of the hand-written RTL and of the synthesis configuration.

    Program-dependent artifacts (mem_config.vh, screen.mif) are excluded, so
    flashing another program does not invalidate the synthesis replicas.  Two
    synthesis runs of the same fingerprint are comparable; a different
    fingerprint means the design changed and the old measurements are stale.
    """
    return source_fingerprint()


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
        for replica_dir in sorted((INPUT_RESULTS / arch).glob("replica_*"),
                                  key=lambda p: int(p.name.split("_")[-1])):
            meta_path = replica_dir / "meta.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            fmax = None
            fmax_file = replica_dir / "fmax.txt"
            if fmax_file.exists():
                try:
                    fmax = float(fmax_file.read_text().strip())
                    if not math.isfinite(fmax) or fmax <= 0:
                        fmax = None
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
    path = INPUT_RESULTS / "results_benchmarks.csv"
    if not path.exists():
        return []
    with path.open() as fp:
        rows = list(csv.DictReader(fp))
    keys = [(r["program"], r["architecture"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate benchmark (program, architecture) rows")
    return rows


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
            cycles, instructions = int(row["cycle_count"]), int(row["instr_retired"])
            valid = row["result"] == "pass" and cycles > 0 and instructions > 0
            cpi = cycles / instructions if valid else None
            fmax_replicas = stats[arch]["fmax"]["values"] if stats[arch]["fmax"] else []
            # A run that did not finish leaves the counters frozen at an
            # arbitrary point: it has no valid throughput and no speedup.
            throughputs = [f / cpi for f in fmax_replicas] if valid else []
            entry["arch"][arch] = {
                "row": row,
                "valid": valid,
                "cpi": cpi,
                "fmax_mean": (sum(fmax_replicas) / len(fmax_replicas))
                if fmax_replicas else None,
                "ipc": 1.0 / cpi if cpi else None,
                "cycles": int(row["cycle_count"]),
                "instructions": int(row["instr_retired"]),
                "result": row["result"] if valid or row["result"] != "pass" else "invalid-counts",
                "note": row.get("note", ""),
                "throughputs": throughputs,
                "throughput": describe(throughputs),
            }
        sc = entry["arch"].get("single_cycle")
        pipe = entry["arch"].get("pipeline")
        if sc and pipe and sc["valid"] and pipe["valid"] and sc["throughputs"] and pipe["throughputs"]:
            # Pairing by index is a descriptive convention, not a variance claim.
            # Compare the duration of the same workload, independent of NOP counts.
            if all("replicas" in stats[a] for a in ARCHES):
                keyed = {a: {str(r.get("seed") or r["replica"]): r["fmax_mhz"]
                             for r in stats[a]["replicas"] if r["fmax_mhz"]}
                         for a in ARCHES}
                pairs = [(keyed["single_cycle"][key], keyed["pipeline"][key])
                         for key in sorted(keyed["single_cycle"].keys()
                                           & keyed["pipeline"].keys())]
            else:
                pairs = zip(stats["single_cycle"]["fmax"]["values"],
                            stats["pipeline"]["fmax"]["values"])
            speedups = [(sc["cycles"] / s) / (pipe["cycles"] / p)
                        for s, p in pairs if s and p]
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
            overhead = ((pipe_stat["mean"] - sc_stat["mean"]) / sc_stat["mean"] * 100.0
                        if sc_stat["mean"] else None)
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
                stat["mean"] if stat else "",
                stat["std"] if stat else "",
                stat["cv"] if stat else "",
                stat["min"] if stat else "",
                stat["max"] if stat else "",
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


def benchmark_summary_rows(metrics: list):
    """Derived summary records, preserving original counters as the authority."""
    for entry in metrics:
        for arch in ARCHES:
            data = entry["arch"].get(arch)
            if not data:
                continue
            speedup = entry.get("speedup")
            yield {
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
            }


def write_benchmarks_csv(metrics: list) -> Path:
    path = RESULTS / "results_benchmarks_summary.csv"
    fields = ["program", "architecture", "result", "cycle_count", "instr_retired",
              "cpi", "ipc", "fmax_mean_mhz", "throughput_mean_mips",
              "throughput_std_mips", "latency_ms", "speedup_mean", "speedup_std",
              "verdict"]
    with path.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(benchmark_summary_rows(metrics))
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


TIMING_PATHS_TXT = {arch: RESULTS / f"timing_paths_{arch}.txt" for arch in ARCHES}

# constraints.sdc declares the pin clock at 10 ns and the single-cycle CPU PLL
# at 12.5 ns, both half of the real board periods, with 0.1 ns of uncertainty.
DOMAIN_PERIOD_NS = {"single_cycle": 12.5, "pipeline": 10.0}


def _timing_field(block: str, name: str) -> str:
    match = re.search(rf"{name}\s*:\s*(\S+)", block)
    return match.group(1) if match else ""


def read_timing_paths() -> dict:
    """Worst setup paths of each architecture, from the archived STA reports.

    The report gives the slack of each path against the period it was
    constrained with.  The period the path really needs follows from that
    slack: it is the constrained period plus what the slack is short by.  A
    path constrained at half the period is scaled back to a full one, so the
    periods of both architectures are comparable.
    """
    out = {}
    for arch in ARCHES:
        path = TIMING_PATHS_TXT[arch]
        if not path.exists():
            continue
        rows = []
        for block in path.read_text().split("Path #")[1:]:
            start, target = _timing_field(block, "From Node"), _timing_field(block, "To Node")
            try:
                relation = float(_timing_field(block, "Relationship"))
                skew = float(_timing_field(block, "Clock Skew"))
                delay = float(_timing_field(block, "Data Delay"))
                slack = float(_timing_field(block, "Slack"))
            except ValueError:
                continue
            required = relation - slack
            period = required * (DOMAIN_PERIOD_NS[arch] / relation)
            rows.append({
                "from": start,
                "to": target,
                "relation_ns": relation,
                "delay_ns": delay,
                "skew_ns": skew,
                "period_ns": period,
                "fmax_mhz": 1000.0 / period,
            })
        # The report repeats the same transfer once per byte lane (and once per
        # duplicated register), so only the first of each is kept.  What
        # identifies a path here is which two blocks it joins and with which
        # period it was constrained.
        seen, unique = set(), []
        for row in sorted(rows, key=lambda r: -r["period_ns"]):
            key = (row["from"].split("|")[0], row["to"].split("|")[0],
                   row["relation_ns"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        out[arch] = unique[:3]
    return out


def _short_node(node: str) -> str:
    """Drop the generated hierarchy of a node name, keep what identifies it.

    The M10K lane names (``ram_block1a20``) are noise: every lane carries the
    same signal, so only the block instance matters.
    """
    parts = node.split("|")
    leaf = parts[-1].replace("~DUPLICATE", "")
    if re.match(r"ram_block\d+a\d+", leaf):
        leaf = ""
    if len(parts) < 2:
        return tex_escape(leaf)
    return " ".join(tex_escape(part) for part in (parts[0], leaf) if part)


def table_critical_path(paths: dict) -> str:
    """The paths that fix the Fmax of each design."""
    if not paths:
        return ""
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        r"\caption{Caminos de datos que fijan la frecuencia máxima, ordenados "
        r"por periodo exigido (proyecto de la última réplica, modelo "
        r"\emph{Slow 1100 mV 85$^\circ$C}). La relación es el periodo con el "
        r"que se restringió el camino: 6.25 ns es medio ciclo.}",
        r"\label{tab:critical_path}",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Arquitectura & Camino (origen $\to$ destino) & Relación (ns) & "
        r"Retardo (ns) & Skew (ns) & Periodo exigido (ns) \\",
        r"\midrule",
    ]
    for arch in ARCHES:
        for row in paths.get(arch, []):
            source = _short_node(row["from"])
            target = _short_node(row["to"])
            # A path that stays inside one block is better read as
            # "block -> its output register" than as the block twice.
            if row["from"].split("|")[0] == row["to"].split("|")[0]:
                target = tex_escape(
                    row["to"].split("|")[-1].replace("~DUPLICATE", ""))
            lines.append(
                f"{ARCH_LABELS[arch]} & {source} $\\to$ {target} & "
                f"{fmt(row['relation_ns'], 3)} & "
                f"{fmt(row['delay_ns'], 3)} & {fmt(row['skew_ns'], 3)} & "
                f"{fmt(row['period_ns'], 2)} \\\\")
        lines.append(r"\midrule")
    lines = lines[:-1]
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def replica_frequency_rows(replicas: list):
    """Keep replica identities visible when either architecture has gaps."""
    indexed = {(r["arch"], int(r["replica"])): r for r in replicas}
    for identity in sorted({int(r["replica"]) for r in replicas}):
        cells = []
        for arch in ARCHES:
            value = indexed.get((arch, identity), {}).get("fmax_mhz")
            cells.append(fmt(float(value)) if value not in (None, "") else r"\textemdash")
        yield str(identity), cells


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
    for identity, cells in replica_frequency_rows(replicas):
        lines.append(f"{identity} & {cells[0]} & {cells[1]} " + r"\\")
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
        r"(media $\pm$ desviación estándar; n por recurso en el CSV).}",
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
            overhead = ((pipe_stat["mean"] - sc_stat["mean"]) / sc_stat["mean"] * 100.0
                        if sc_stat["mean"] else None)
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
        r"El throughput y la latencia se obtienen con la Fmax media de las "
        r"réplicas disponibles de síntesis.}",
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
                    + " & ".join([r"\textemdash"] * 4) + r" \\")
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


COREMARK_INPUT_CSV = INPUT_RESULTS / "results_coremark.csv"
COREMARK_CSV = RESULTS / "results_coremark.csv"
COREMARK_PROVENANCE = (
    "git_commit", "rtl_fingerprint", "date_utc", "sof_sha256",
    "fmax_mhz", "tohost_addr", "coremark_functional_valid", "elf_sha256", "counter_protocol",
)


def read_coremark_hardware() -> list:
    """The recorded CoreMark workload runs, read from the frozen board counters.

    One row per architecture: iterations, cycles and instructions as the VGA
    console shows them, and the clock the CPU ran at.  Everything else is
    derived, so the file only stores what was measured.
    """
    if not COREMARK_INPUT_CSV.exists():
        return []
    rows = []
    with open(COREMARK_INPUT_CSV) as fp:
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
    """Persist the recorded CoreMark hardware run so it can be re-derived."""
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
    print(f"  {path}")
    return path


def table_coremark(rows: list) -> str:
    """CoreMark workload rates; legacy runs have no CRC evidence."""
    if not rows:
        return ""
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Carga CoreMark en hardware. Tasas derivadas de contadores; "
        r"la validación funcional se identifica en el manifiesto. Los contadores "
        r"proceden de la consola VGA.}",
        r"\label{tab:coremark}",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"Arquitectura & Reloj (MHz) & Ciclos & Instrucciones & Tiempo (s) & "
        r"Iteraciones/s & Iteraciones/s/MHz \\",
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


def table_coremark_scenarios(rows: list, stats: dict) -> str:
    """CoreMark read at the three frequencies the comparison admits.

    The CPI is the measured one; the scenarios differ only in the clock each
    design is given, so the table isolates the frequency term of the speedup.
    """
    by_arch = {row["arch"]: row for row in rows}
    if len(by_arch) < 2 or any(not stats[a]["fmax"] for a in ARCHES):
        return ""
    sc, pipe = by_arch["single_cycle"], by_arch["pipeline"]
    sc_fmax = stats["single_cycle"]["fmax"]["mean"]
    pipe_fmax = stats["pipeline"]["fmax"]["mean"]
    # The lowest Fmax of every replica is still above 40 MHz, so 40 MHz is the
    # highest board clock that both designs meet in all five replicas.
    common = sc["clock_mhz"]
    scenarios = [
        (f"Frecuencia común hipotética ({fmt(common, 0)} MHz en ambos)",
         common, common,
         common * sc["per_mhz"], common * pipe["per_mhz"]),
        (f"Frecuencia desplegada ({fmt(sc['clock_mhz'], 0)} / "
         f"{fmt(pipe['clock_mhz'], 0)} MHz)",
         sc["clock_mhz"], pipe["clock_mhz"], sc["score"], pipe["score"]),
        (f"Fmax estimada ({fmt(sc_fmax)} / {fmt(pipe_fmax)} MHz, no validada "
         "en placa)",
         sc_fmax, pipe_fmax,
         sc_fmax * sc["per_mhz"], pipe_fmax * pipe["per_mhz"]),
    ]
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{CoreMark según la frecuencia asignada a cada diseño. El CPI "
        r"medido es el mismo en las tres filas; solo cambia el reloj.}",
        r"\label{tab:coremark_scenarios}",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Escenario & \multicolumn{2}{c}{Reloj (MHz)} & "
        r"\multicolumn{2}{c}{Iteraciones/s} & Speedup \\",
        r"\cmidrule(lr){2-3} \cmidrule(lr){4-5}",
        r" & Monociclo & Pipeline & Monociclo & Pipeline & \\",
        r"\midrule",
    ]
    for label, sc_mhz, pipe_mhz, sc_score, pipe_score in scenarios:
        lines.append(
            f"{label} & {fmt(sc_mhz, 2)} & {fmt(pipe_mhz, 2)} & "
            f"{fmt(sc_score, 1)} & {fmt(pipe_score, 1)} & "
            f"{fmt(pipe_score / sc_score, 3)} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


def table_speedup(metrics: list) -> str:
    lines = table_header()
    lines += [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Speedup del pipeline respecto al monociclo y evaluación "
        r"descriptiva por programa; media de cocientes temporales pareados.}",
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
        r"\caption{Estadística descriptiva de las réplicas disponibles de síntesis "
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
            "per_alm": mean_throughput / (alms["mean"] / 1000.0) if alms and alms["mean"] else None,
            "per_reg": mean_throughput / (registers["mean"] / 1000.0) if registers and registers["mean"] else None,
        }
    for key, label in (("per_alm", "Throughput por 1000 ALMs (MIPS)"),
                       ("per_reg", "Throughput por 1000 registros (MIPS)")):
        cells = [fmt(per_arch[arch].get(key), 3, dash=r"\textemdash") if arch in per_arch else r"\textemdash"
                 for arch in ARCHES]
        lines.append(f"{label} & {cells[0]} & {cells[1]} \\\\")
    for row in efficiency:
        if row["overhead_pct"] is None:
            continue
        lines.append(f"Overhead de {row['label']} del pipeline & "
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
    for identity, cells in replica_frequency_rows([r for rows in replicas.values() for r in rows]):
        expected[identity] = cells
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
        if not values or not stat or not float(stat["mean"]):
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
        expected[f"Overhead de {row['resource']} del pipeline"] = [
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
            cells += [r"\textemdash"] * 4
        else:
            cells += [f"{float(row['cpi']):.4f}",
                      f"{float(row['ipc']):.4f}",
                      fmt(float(row["throughput_mean_mips"]), 2) if row["throughput_mean_mips"] else r"\textemdash",
                      fmt(float(row["latency_ms"]), 4) if row["latency_ms"] else "---"]
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


def coremark_scenarios_table_problems() -> list:
    """Compare the three-frequency CoreMark table with both CSVs."""
    setup = {row["architecture"]: row for row in _read_csv_rows(COREMARK_CSV)}
    fmax = {row["arch"]: float(row["fmax_mean_mhz"])
            for row in _read_csv_rows(RESULTS / "results_fmax.csv")}
    if len(setup) < 2 or len(fmax) < 2:
        return []
    sc, pipe = setup["single_cycle"], setup["pipeline"]
    clocks = [
        (float(sc["clock_mhz"]), float(sc["clock_mhz"])),
        (float(sc["clock_mhz"]), float(pipe["clock_mhz"])),
        (fmax["single_cycle"], fmax["pipeline"]),
    ]
    scores = [
        (float(sc["clock_mhz"]) * float(sc["score_per_mhz"]),
         float(sc["clock_mhz"]) * float(pipe["score_per_mhz"])),
        (float(sc["score"]), float(pipe["score"])),
        (fmax["single_cycle"] * float(sc["score_per_mhz"]),
         fmax["pipeline"] * float(pipe["score_per_mhz"])),
    ]
    rows = parse_tex_rows(TABLES / "coremark_scenarios.tex")
    if len(rows) != len(clocks):
        return [f"CoreMark escenarios: {len(rows)} filas en el .tex y "
                f"{len(clocks)} esperadas"]
    problems = []
    for index, (row, (sc_mhz, pipe_mhz), (sc_score, pipe_score)) in enumerate(
            zip(rows, clocks, scores), start=1):
        for column, (tex_cell, target) in enumerate(
                zip(row[1:], (sc_mhz, pipe_mhz, sc_score, pipe_score,
                              pipe_score / sc_score))):
            if abs(float(tex_cell) - target) > 0.05 * max(1.0, abs(target)):
                problems.append(
                    f"CoreMark escenarios: fila {index}, columna {column + 1}: "
                    f"CSV {target:.3f} != TeX {tex_cell}")
    return problems


def critical_path_table_problems() -> list:
    """The implied Fmax of each table must match the measured one.

    The project state of ``synthesis/`` is one replica, so the path that
    fixes its period reproduces the Fmax of that replica, not the mean.
    """
    problems = []
    fmax = {row["arch"]: row for row in _read_csv_rows(RESULTS / "results_fmax.csv")}
    rows = parse_tex_rows(TABLES / "critical_path.tex")
    by_arch = {label: [] for label in ARCH_LABELS.values()}
    for row in rows:
        by_arch.setdefault(row[0], []).append(row)
    for arch, label in ARCH_LABELS.items():
        paths = by_arch.get(label, [])
        if not paths:
            problems.append(f"Camino crítico: no hay filas de {label}")
            continue
        implied = 1000.0 / float(paths[0][-1])
        lowest = float(fmax[arch]["fmax_min_mhz"])
        highest = float(fmax[arch]["fmax_max_mhz"])
        if not 0.95 * lowest <= implied <= 1.05 * highest:
            problems.append(
                f"Camino crítico: {label} implica {implied:.2f} MHz, fuera del "
                f"rango medido {lowest:.2f}-{highest:.2f} MHz")
    return problems


def _figure_addplots(path: Path, error_bars: bool = False) -> list:
    """Points of every ``\\addplot`` of a generated pgfplots figure."""
    plots = []
    text = path.read_text()
    for match in re.finditer(r"\\addplot(?:\[[^\]]*\])? coordinates \{([^}]*)\};", text):
        body = match.group(1)
        if error_bars:
            points = [(int(m.group(1)), float(m.group(2)), float(m.group(3)))
                      for m in re.finditer(
                          r"\((\d+),([\d.]+|nan)\)\s*\+-\s*\(0,([\d.]+)\)", body)]
        else:
            points = [(int(m.group(1)), float(m.group(2)))
                      for m in re.finditer(r"\((\d+),([\d.]+|nan)\)", body)]
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
            if (math.isnan(value) != math.isnan(target)
                    or (not math.isnan(target) and abs(value - target) > tolerance)):
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
        target = float(row["fmax_mean_mhz"]) if row["fmax_mean_mhz"] else math.nan
        if math.isnan(mean) != math.isnan(target) or (not math.isnan(target) and abs(mean - target) > 0.0055):
            problems.append(f"Figura Fmax: '{ARCH_LABELS[arch]}' media del "
                            f"CSV {row['fmax_mean_mhz']} != figura {mean}")
        if abs(std - float(row["fmax_std_mhz"] or 0)) > 0.0055:
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
                values.append(math.nan)
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


def speedup_figure_problems() -> list:
    """Compare the speedup bars with results_benchmarks_summary.csv."""
    programs, means, stds = [], [], []
    for row in _read_csv_rows(RESULTS / "results_benchmarks_summary.csv"):
        if not row["speedup_mean"].strip() or row["program"] in programs:
            continue
        programs.append(row["program"])
        means.append(float(row["speedup_mean"]))
        stds.append(float(row["speedup_std"]))
    plots = _figure_addplots(FIGURES / "speedup.tex", error_bars=True)
    if len(plots) < 2:
        return [f"Figura Speedup: {len(plots)} series y se esperaban 2"]
    points = plots[0]
    if len(points) != len(programs):
        return [f"Figura Speedup: {len(points)} barras y {len(programs)} "
                "programas"]
    problems = []
    for index, ((x, mean, std), wanted, wanted_std) in enumerate(
            zip(points, means, stds), start=1):
        if x != index:
            problems.append(f"Figura Speedup: '{programs[index - 1]}' en x={x}")
        if abs(mean - wanted) > 0.0006:
            problems.append(f"Figura Speedup: '{programs[index - 1]}' media "
                            f"{wanted:.3f} != figura {mean:.3f}")
        if abs(std - wanted_std) > 0.0006:
            problems.append(f"Figura Speedup: '{programs[index - 1]}' "
                            f"desviación {wanted_std:.3f} != figura {std:.3f}")
    if any(abs(y - 1.0) > 1e-9 for _, y in plots[1]):
        problems.append("Figura Speedup: la línea de referencia no está en 1")
    return problems


def resources_figure_problems() -> list:
    """Compare results_statistics.csv with the resources figure."""
    stats = {(row["arch"], row["metric"]): float(row["mean"])
             for row in _read_csv_rows(RESULTS / "results_statistics.csv")}
    expected = [[stats.get((arch, key), math.nan) for key in
                 ("alms", "registers")]
                for arch in ARCHES]
    return _grouped_figure_problems("Recursos", "resources_comparison.tex",
                                    expected)


def derived_metric_problems() -> list:
    """Recompute metrics from counters and replicas, independently of plots."""
    replicas = _read_csv_rows(RESULTS / "results_replicas.csv")
    for row in replicas:
        for key in ("fmax_mhz", *RESOURCE_PATTERNS):
            row[key] = float(row[key]) if row.get(key) else None
    stats = replica_stats(replicas)
    benchmarks = _read_csv_rows(RESULTS / "results_benchmarks.csv")
    wanted = [{k: str(v) for k, v in row.items()}
              for row in benchmark_summary_rows(benchmark_metrics(benchmarks, stats))]
    actual = _read_csv_rows(RESULTS / "results_benchmarks_summary.csv")
    problems = []
    if wanted != actual:
        problems.append("Métricas: el resumen no se deriva de los contadores y réplicas publicados")
    for row in _read_csv_rows(RESULTS / "results_fmax.csv"):
        expected = stats[row["arch"]]["fmax"]
        for field, key in (("fmax_mean_mhz", "mean"), ("fmax_std_mhz", "std"),
                           ("fmax_min_mhz", "min"), ("fmax_max_mhz", "max")):
            if expected is None:
                if row[field]:
                    problems.append(f"Métricas: {row['arch']} tiene frecuencia sin réplicas")
            elif not math.isclose(float(row[field]), expected[key], rel_tol=1e-10):
                problems.append(f"Métricas: {row['arch']}/{field} no concuerda con sus réplicas")
    for row in _read_csv_rows(RESULTS / "results_statistics.csv"):
        expected = stats[row["arch"]].get(row["metric"])
        if not expected or int(row["n"]) != expected["n"]:
            problems.append(f"Métricas: n incompatible en {row['arch']}/{row['metric']}")
            continue
        for field in ("mean", "std", "min", "max"):
            if abs(float(row[field]) - expected[field]) > 0.00051:
                problems.append(f"Métricas: {row['arch']}/{row['metric']}/{field} incompatible")
    return problems


def check_artifacts() -> int:
    """Compare the generated tables and figures with their source CSVs."""
    tables = (
        ("Métricas", derived_metric_problems),
        ("Verificación", verification_table_problems),
        ("Fmax", fmax_table_problems),
        ("Recursos", resources_table_problems),
        ("Estadísticas", statistics_table_problems),
        ("Eficiencia", efficiency_table_problems),
        ("Benchmarks", benchmarks_table_problems),
        ("Speedup", speedup_table_problems),
        ("CoreMark", coremark_table_problems),
        ("CoreMark escenarios", coremark_scenarios_table_problems),
        ("Camino crítico", critical_path_table_problems),
    )
    figures = (
        ("Fmax", fmax_figure_problems),
        ("Throughput", throughput_figure_problems),
        ("CPI", cpi_figure_problems),
        ("Speedup", speedup_figure_problems),
        ("Recursos", resources_figure_problems),
    )
    problems = []
    checked = 0
    for name, check in tables + figures:
        if name == "CoreMark" and not _read_csv_rows(COREMARK_CSV):
            continue
        if name == "CoreMark escenarios" and not (TABLES / "coremark_scenarios.tex").exists():
            continue
        if name == "Camino crítico" and not (TABLES / "critical_path.tex").exists():
            continue
        checked += 1
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
    print(f"OK: {checked} comprobaciones de tablas y figuras coinciden con sus CSV.")
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
        coords.append(f"({index + 1},{(stat['mean'] if stat else math.nan):.2f}) +- (0,{(stat['std'] if stat else 0):.2f})")
    return "\n".join([
        "% Generado por scripts/thesis_artifacts.py - no editar a mano.",
        r"\begin{figure}[htbp]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        r"  width=0.65\textwidth,",
        r"  height=7cm,",
        r"  ybar,",
        r"  unbounded coords=jump,",
        r"  bar width=25pt,",
        r"  ylabel={Fmax (MHz)},",
        r"  xtick={1,2},",
        r"  xticklabels={Monociclo,Pipeline},",
        r"  nodes near coords,",
        r"  nodes near coords align={vertical},",
        r"  ymin=0,",
        r"  xmin=0.5, xmax=2.5,",
        r"  enlarge y limits={upper,value=0.18},",
        r"  every node near coord/.append style={anchor=south,yshift=2pt},",
        r"  error bars/y dir=both, error bars/y explicit,",
        r"]",
        "  \\addplot coordinates {" + " ".join(coords) + "};",
        r"\end{axis}",
        r"\end{tikzpicture}",
        r"\caption{Frecuencia máxima de cada microarquitectura, media "
        r"$\pm$ desviación estándar de las réplicas disponibles de síntesis.}",
        r"\label{fig:fmax}",
        r"\end{figure}",
    ])


def _grouped_bar_figure(entries, values_by_arch, ylabel, caption, label, value_labels=False):
    ticks = [f"{{{tex_escape(name)}}}" for name in entries]
    options = [
        r"  width=0.95\textwidth,",
        r"  height=7cm,",
        r"  ybar,",
        r"  unbounded coords=jump,",
        r"  bar width=8pt,",
        f"  ylabel={{{ylabel}}},",
        "  xtick={" + ",".join(str(i + 1) for i in range(len(entries))) + "},",
        "  xticklabels={" + ", ".join(ticks) + "},",
        r"  xmin=0.5,",
        "  xmax=" + str(max(1, len(entries)) + 0.5) + ",",
        r"  ymin=0,",
        r"  enlarge y limits={upper,value=0.18},",
        r"  legend style={at={(0.5,-0.25)},anchor=north,legend columns=2},",
    ]
    if value_labels:
        options += [
            r"  width=10cm,",
            r"  bar width=22pt,",
            r"  nodes near coords,",
            r"  nodes near coords align={vertical},",
            r"  every node near coord/.append style={font=\scriptsize,anchor=south,yshift=2pt,text=black,/pgf/number format/fixed,/pgf/number format/precision=1},",
            r"  x tick label style={font=\small,align=center,text width=3.6cm},",
            r"  legend style={at={(0.5,-0.23)},anchor=north,legend columns=2},",
        ]
    else:
        options += [
            r"  x tick label style={rotate=45,anchor=east,font=\small},",
            r"  legend style={at={(0.5,-0.43)},anchor=north,legend columns=2},",
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
        coords = " ".join(f"({index + 1},{value:.3f})"
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
            values[arch].append(data["throughput"]["mean"] if data and data["throughput"] else math.nan)
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
            values[arch].append(data["cpi"] if data and data["valid"] else math.nan)
    return _grouped_bar_figure(
        entries, values, "CPI",
        r"CPI efectivo por programa y microarquitectura.",
        "fig:cpi")


def figure_speedup(metrics: list) -> str:
    """Speedup per program with the H1 threshold, so the verdict is visible."""
    measured = [m for m in metrics if m.get("speedup")]
    entries = [m["program"] for m in measured]
    ticks = [f"{{{tex_escape(name)}}}" for name in entries]
    coords = " ".join(
        f"({index + 1},{m['speedup']['mean']:.3f}) +- "
        f"(0,{m['speedup']['std']:.3f})"
        for index, m in enumerate(measured))
    options = [
        r"  width=0.95\textwidth,",
        r"  height=7cm,",
        r"  ybar,",
        r"  unbounded coords=jump,",
        r"  bar width=14pt,",
        r"  ylabel={Speedup temporal del pipeline},",
        "  xtick={" + ",".join(str(i + 1) for i in range(len(entries))) + "},",
        "  xticklabels={" + ", ".join(ticks) + "},",
        r"  xmin=0.5,",
        r"  ymin=0,",
        r"  x tick label style={rotate=45,anchor=east,font=\small},",
        r"  enlarge y limits={upper,value=0.18},",
        r"  xmax=" + str(max(1, len(entries)) + 0.5) + ",",
        r"  ymajorgrids,",
        r"  legend style={at={(0.5,-0.43)},anchor=north,legend columns=1},",
        r"  error bars/y dir=both, error bars/y explicit,",
    ]
    lines = [
        "% Generado por scripts/thesis_artifacts.py - no editar a mano.",
        r"\begin{figure}[htbp]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        "\n".join(options),
        r"]",
        "  \\addplot coordinates {" + coords + "};",
        "  \\addplot[black, dashed, sharp plot, update limits=false] "
        "coordinates {(0.5,1) (" + str(len(entries) + 0.5) + ",1)};",
        r"  \legend{Speedup medio $\pm$ desviación estándar,Paridad ($S=1$)}",
        r"\end{axis}",
        r"\end{tikzpicture}",
        r"\caption{Speedup temporal por programa, media de cocientes pareados. La "
        r"línea en 1 separa la ganancia de la pérdida; $H_1$ exige además que "
        r"la media menos una desviación estándar supere ese umbral.}",
        r"\label{fig:speedup}",
        r"\end{figure}",
    ]
    return "\n".join(lines)


def figure_resources(stats: dict) -> str:
    entries = ["Elementos lógicos adaptativos (ALM)", "Registros"]
    keys = ["alms", "registers"]
    values = {arch: [] for arch in ARCHES}
    for arch in ARCHES:
        for key in keys:
            stat = stats[arch].get(key)
            values[arch].append(stat["mean"] if stat else math.nan)
    return _grouped_bar_figure(
        entries, values, "Cantidad de recursos",
        r"Utilización de los recursos lógicos de la FPGA por microarquitectura.",
        "fig:resources", value_labels=True)


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
        "> Instrumentación vigente: retire-inclusive-v2 (ADR 053). Los CSV "
        "históricos usan la ventana anterior y no acreditan CRC físicos. "
        "Las proyecciones que siguen no sustituyen la nueva campaña.",
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
        "retira la escritura a `tohost`, incluida; el valor queda congelado. |",
        "| `instr_retired` | Monociclo: un ciclo por instrucción ejecutada. "
        "Pipeline: ciclos en los que `valid_wb = 1`, es decir, instrucciones "
        "que se retiran sin burbuja. La validez es independiente del opcode NOP. |",
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
        "con comparación de registros, memoria y conteo contra el modelo de Python "
        "cuando VALIDATION_REFERENCE=1. El registro histórico original no incluye "
        "esta validación para todos los benchmarks.",
        "4. Cálculo del throughput de cada réplica como "
        r"$F_{\max,i}/\mathrm{CPI}$ "
        "y del speedup temporal como media de T_monociclo/T_pipeline "
        "pareados por índice; T = ciclos/(frecuencia en MHz × 10^6). "
        "El emparejamiento es descriptivo y no garantiza menor varianza.",
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
        "Con $n = 5$ implementaciones por tratamiento, el análisis es descriptivo. "
        "La siguiente regla adicional no es un intervalo de confianza ni se "
        "atribuye retrospectivamente al anteproyecto. La hipótesis $H_1$ se considera "
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
        "- La campaña histórica conserva una lectura CoreMark por arquitectura; "
        "no acredita cinco ejecuciones físicas ni CRC correctos. La proyección "
        "de ciclos deterministas sobre cinco frecuencias es una adaptación "
        "metodológica y no sustituye comprobar cada bitstream en placa.",
        "",
    ]
    path.write_text("\n".join(lines))
    return path


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def generate_artifacts() -> int:
    fingerprint = rtl_fingerprint()
    replicas = collect_replicas()
    stats = replica_stats(replicas)
    benchmarks = read_benchmarks()
    verification = read_verification()
    metrics = benchmark_metrics(benchmarks, stats)
    efficiency = efficiency_table(metrics, stats)

    for directory in (TABLES, FIGURES, REPRO):
        directory.mkdir(parents=True, exist_ok=True)

    from collect_results import ArchitectureResults, generate_csv_report
    import collect_results
    all_results = {arch: ArchitectureResults(name=arch, suites=
                   collect_results.collect_verification_results(arch)) for arch in ARCHES}
    (RESULTS / "results_verification.csv").write_text(generate_csv_report(all_results) + "\n")
    (RESULTS / "results_benchmarks.csv").write_text(
        (INPUT_RESULTS / "results_benchmarks.csv").read_text()
        if (INPUT_RESULTS / "results_benchmarks.csv").exists() else
        "architecture,program,result,cycle_count,instr_retired,cpi\n")
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
        "critical_path.tex": table_critical_path(read_timing_paths()),
        "resources.tex": table_resources(stats),
        "benchmarks.tex": table_benchmarks(metrics),
        "statistics.tex": table_statistics(stats),
        "efficiency.tex": table_efficiency(metrics, stats, efficiency),
        "speedup.tex": table_speedup(metrics),
        "coremark.tex": table_coremark(read_coremark_hardware()),
        "coremark_scenarios.tex": table_coremark_scenarios(
            read_coremark_hardware(), stats),
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
        "speedup.tex": figure_speedup(metrics),
        "resources_comparison.tex": figure_resources(stats),
    }
    for name, content in figures.items():
        (FIGURES / name).write_text(content + "\n")
        written.append(FIGURES / name)

    # A replica without a fingerprint comes from an unknown RTL: it is stale
    # too, and the numbers it holds cannot be compared with the others.
    stale = any(r.get("fingerprint") != fingerprint for r in replicas)

    for path in written:
        print(f"  {path}")
    if stale:
        print("\nAVISO: las replicas guardadas no corresponden al RTL vigente; "
              "ejecute 'make thesis' para repetirlas.")
    return 0


def main() -> int:
    from generate_reports import main as generate_reports
    return generate_reports()


if __name__ == "__main__":
    raise SystemExit(main())
