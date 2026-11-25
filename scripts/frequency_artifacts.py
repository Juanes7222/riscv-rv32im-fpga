"""Publish a portable academic package from the audited frequency observations."""
import csv
import math
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import frequency_build as build
from frequency_campaign import exclusive
from frequency_latex import academic_figures, thesis_table_rows
from frequency_observation import metrics, paired_results, report
from physical_campaign_report import LABELS
from vga_timing import tool_path

ARCHES = {"single_cycle": "Monociclo", "pipeline": "Segmentado"}
RESOURCE_KEYS = ("alms", "registers", "ram_blocks", "dsp_blocks", "memory_bits", "pins")
HELP = r"""# Campaña de frecuencias de operación

Consulte data/results.json para obtener las observaciones, los hashes originales,
las comparaciones por semilla y los estadísticos con su precisión original.
Los CSV permiten analizar y filtrar los mismos datos. Las celdas vacías
representan datos ausentes o comprobaciones sin resultado numérico.

Las frecuencias validadas provienen del reloj configurado del SOF empleado en
placa. El tiempo nominal se calcula a partir de los ciclos y esa frecuencia.
La Fmax de TimeQuest corresponde al modelo lento a 85 °C. Consulte el archivo
candidates.csv para conocer las comprobaciones aplicables y su decisión.

Las frecuencias y tiempos de la campaña original provienen de sus
observaciones archivadas. Los resultados históricos proyectados a Fmax son
estimaciones derivadas de ciclos y de la Fmax restringida archivada.
comparison.csv contiene las tres condiciones con el mismo programa y semilla.

Cada configuración validada aporta una observación aunque se haya comprobado
en dos arranques. Se informa la desviación estándar muestral entre semillas.
El criterio descriptivo exige que la media de las aceleraciones menos la
desviación estándar muestral supere uno en al menos tres de cinco programas.
La evaluación global requiere los 25 pares.

Para incorporar una tabla o una figura, copie el archivo .tex al manuscrito e
inclúyalo mediante \input. Las tablas usan booktabs y longtable. Las figuras usan
PGFPlots con compat=1.18 e incluyen sus coordenadas. Los archivos de tabla cuyo
nombre termina en _filas.tex se insertan dentro de las tablas del manuscrito y
usan siunitx para las cifras. preview.tex reúne las tablas completas y las
figuras y puede compilarse desde la raíz de este paquete. La vista previa en
PDF, cuando está presente, se genera con LaTeX.
"""


def csv_file(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)


def format_number(value, digits=3):
    if value is None:
        return "--"
    if isinstance(value, float) and 0 < abs(value) < 10 ** -digits:
        mantissa, exponent = f"{value:.{digits}e}".split("e")
        return rf"\ensuremath{{{mantissa}\times10^{{{int(exponent)}}}}}"
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def table(directory, name, headers, rows, *, long=False):
    spec = "@{}ll" + "r" * (len(headers) - 2) + "@{}"
    env = "longtable" if long else "tabular"
    lines = [r"\begingroup\small\setlength{\tabcolsep}{4pt}", rf"\begin{{{env}}}{{{spec}}}",
             r"\toprule", " & ".join(headers) + r" \\", r"\midrule"]
    if long:
        lines.extend([r"\endfirsthead", r"\toprule", " & ".join(headers) + r" \\", r"\midrule",
                      r"\endhead", r"\bottomrule", r"\endfoot"])
    lines.extend(" & ".join(format_number(x) for x in row) + r" \\" for row in rows)
    if not long:
        lines.append(r"\bottomrule")
    lines.extend([rf"\end{{{env}}}", r"\endgroup"])
    (directory / (name + ".tex")).write_text("\n".join(lines) + "\n", encoding="utf-8")


def historical_comparisons(data, tie):
    original, projected = {}, {}
    for item in data["observations"]:
        row = item["historical_reference"]
        key = (item["program"], item["architecture"], item["seed"])
        base = dict(elf_sha256=row["elf_sha256"], cycle_count=int(row["cycle_count"]),
                    instr_retired=int(row["instr_retired"]))
        original[key] = dict(base, clock_mhz=float(row["clock_mhz"]))
        projected[key] = dict(base, clock_mhz=float(row["fmax_mhz"]))
    old, _, _ = paired_results(original, tie)
    estimates, _, _ = paired_results(projected, tie)
    before = {(item["program"], item["seed"]): item for item in old}
    projection = {(item["program"], item["seed"]): item for item in estimates}
    comparison = []
    for item in data["paired"]:
        key = (item["program"], item["seed"])
        measured, estimated = before.get(key, {}), projection.get(key, {})
        comparison.append(dict(
            program=item["program"], seed=item["seed"],
            original_40_50_speedup=measured.get("speedup"),
            projected_historical_fmax_speedup=estimated.get("speedup"),
            validated_frequency_speedup=item["speedup"],
        ))
    return comparison


def content(directory, data, tie):
    for name in ("data", "tables", "figures"):
        (directory / name).mkdir()
    out = directory / "data"
    results = data | {"comparisons": historical_comparisons(data, tie)}
    build.save_json(out / "results.json", results)

    kind = "Completa" if len(results["paired"]) == 25 else "Parcial"
    caption = f"{kind}: {len(results['observations'])}/50 configuraciones y {len(results['paired'])}/25 pares"
    (directory / "README.md").write_text(HELP + f"\n**{caption}.**\n", encoding="utf-8")
    if data["candidates"]:
        csv_file(out / "candidates.csv", data["candidates"][0], data["candidates"])
    pair_columns = ("program", "seed", "speedup", "cycle_ratio", "frequency_ratio", "single_cycle_mhz",
                    "pipeline_mhz", "required_frequency_increase_pct", "achieved_frequency_increase_pct",
                    "time_reduction_pct")
    csv_file(out / "paired.csv", pair_columns, ({k: item[k] for k in pair_columns} for item in data["paired"]))
    comparison_columns = ("program", "seed", "original_40_50_speedup", "projected_historical_fmax_speedup",
                          "validated_frequency_speedup")
    csv_file(out / "comparison.csv", comparison_columns, results["comparisons"])
    stats = ("mean", "sample_sd", "minimum", "maximum")
    descriptors = [dict(program=program, architecture=arch, pairs=summary["pairs"], metric=metric, **values)
                   for program, summary in data["by_program"].items()
                   for arch, descriptors in summary["by_architecture"].items()
                   for metric, values in descriptors.items()]
    csv_file(out / "descriptive.csv", ("program", "architecture", "pairs", "metric", *stats), descriptors)
    stages = data.get("timing_profile", {}).get("new_candidates_by_stage", {})
    csv_file(out / "profile.csv", ("stage", "samples", "median_seconds", "total_job_seconds"),
             (dict(stage=stage, **values) for stage, values in stages.items()))

    observations = []
    for item in results["observations"]:
        candidate = item["candidate"]
        observations.append(dict(
            program=item["program"], architecture=item["architecture"], seed=item["seed"],
            requested_mhz=candidate["requested_mhz"], effective_mhz=candidate["effective_mhz"],
            fmax_mhz=candidate["fmax_mhz"], restricted_mhz=candidate["restricted_mhz"],
            **item["metrics"], **{k: item["resources"].get(k) for k in RESOURCE_KEYS},
        ))
    fields = ("program", "architecture", "seed", "requested_mhz", "effective_mhz", "fmax_mhz",
              "restricted_mhz", "cycles", "instructions_retired", "cpi", "ipc", "nominal_seconds",
              "instructions_per_second", *RESOURCE_KEYS)
    csv_file(out / "observations.csv", fields, observations)
    academic_tables(directory / "tables", data, observations, results["comparisons"])
    thesis_table_rows(directory / "tables", data, observations)
    academic_figures(directory / "figures", data, observations, results["comparisons"])
    wrapper(directory, caption, results["descriptive_support"])


def academic_tables(directory, data, observations, comparison):
    def values(*keys):
        return [[LABELS[item["program"]], ARCHES[item["architecture"]], item["seed"],
                 *(item[key] for key in keys)] for item in observations]

    table(directory, "frecuencias", ["Programa", "Arquitectura", "Sem.", "Sol. (MHz)", "Val. (MHz)",
                                   r"$f_\mathrm{max}$ (MHz)", "Restr. (MHz)"],
          values("requested_mhz", "effective_mhz", "fmax_mhz", "restricted_mhz"), long=True)
    table(directory, "metricas", ["Programa", "Arquitectura", "Sem.", "Ciclos", "Instr.", "CPI", "IPC"],
          values("cycles", "instructions_retired", "cpi", "ipc"), long=True)
    record = [[*row[:3], row[3], row[4] / 1e6] for row in values("nominal_seconds", "instructions_per_second")]
    table(directory, "tiempos", ["Programa", "Arquitectura", "Sem.", "Tiempo nominal (s)", "MIPS"],
          record, long=True)
    table(directory, "recursos", ["Programa", "Arquitectura", "Sem.", "ALM", "Reg.", "RAM", "DSP", "Bits", "Pines"],
          values(*RESOURCE_KEYS), long=True)
    margins = ("setup_ns", "hold_ns", "pulse_width_ns", "recovery_ns", "removal_ns")
    table(directory, "margenes", ["Programa", "Arquitectura", "Sem.", "Setup (ns)", "Hold (ns)",
                                  "Pulso (ns)", "Recup. (ns)", "Remoc. (ns)"],
          [[LABELS[item["program"]], ARCHES[item["architecture"]], item["seed"],
            *(item["candidate"][key] for key in margins)] for item in data["observations"]], long=True)
    table(directory, "comparacion", ["Programa", "Sem.", "Original", "Proyección", "Validada"],
          [[LABELS[item["program"]], *(item[key] for key in ("seed", "original_40_50_speedup",
                                   "projected_historical_fmax_speedup", "validated_frequency_speedup"))]
           for item in comparison], long=True)
    table(directory, "umbral", ["Programa", "Sem.", r"Necesario (\%)", r"Alcanzado (\%)",
                              r"Reducción de tiempo (\%)"],
          [[LABELS[item["program"]], *(item[key] for key in ("seed", "required_frequency_increase_pct",
                                   "achieved_frequency_increase_pct", "time_reduction_pct"))]
           for item in data["paired"]], long=True)
    table(directory, "estadisticos",
          ["Programa", "Pares", r"$\overline{S}$", r"$s$", "Mín.", "Máx.",
           "Seg.", "Mono.", "Emp.", r"$\overline{S}-s>1$"],
          [[LABELS[program], item["pairs"], *(item[key] for key in ("mean", "sample_sd", "minimum", "maximum",
            "pipeline", "single_cycle", "ties")), verdict(item["meets_descriptive_rule"])]
           for program, item in data["by_program"].items()])


def verdict(value):
    return "--" if value is None else ("Sí" if value else "No")


def wrapper(directory, caption, support):
    start = r"""\documentclass[a4paper,11pt]{article}
\usepackage[margin=1.9cm]{geometry}
\usepackage[T1]{fontenc}
\usepackage{lmodern,booktabs,longtable,pgfplots,siunitx}
\sisetup{output-decimal-marker={,},group-separator={\,}}
\pgfplotsset{compat=1.18}
\begin{document}
"""
    lines = [start, r"\section*{Campaña de frecuencias de operación}", caption + r"\par"]
    lines.append("Valoración descriptiva pendiente de los 25 pares." if support is None
                 else f"Respaldo descriptivo de la hipótesis. {verdict(support)}.")
    for name, heading in (
        ("frecuencias", "Frecuencias nominales y estimadas"),
        ("metricas", "Métricas arquitectónicas"),
        ("tiempos", "Desempeño nominal"),
        ("recursos", "Recursos de la FPGA"),
        ("margenes", "Márgenes del análisis temporal"),
        ("comparacion", "Aceleración por condición experimental"),
        ("umbral", "Compensación de ciclos y reducción del tiempo nominal"),
        ("estadisticos", "Estadísticos descriptivos"),
    ):
        lines.extend([r"\clearpage", rf"\section*{{{heading}}}", rf"\input{{tables/{name}.tex}}"])
    for figure in sorted((directory / "figures").glob("*.tex")):
        lines.extend([r"\clearpage", r"\centering", rf"\input{{figures/{figure.name}}}"])
    lines.append(r"\end{document}")
    (directory / "preview.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def compile_pdf(directory, executable):
    if not shutil.which(executable):
        raise ValueError(f"LaTeX executable not found: {executable}")
    with (directory / "latex-build.log").open("wb") as log:
        command = [executable, "-interaction=nonstopmode", "-halt-on-error",
                   tool_path(directory / "preview.tex", executable)]
        for _ in range(2):
            subprocess.run(command, cwd=directory, stdout=log, stderr=subprocess.STDOUT, check=True)
    if not (directory / "preview.pdf").is_file():
        raise ValueError("LaTeX did not create the vector preview PDF")
    for name in ("preview.aux", "preview.log"):
        (directory / name).unlink(missing_ok=True)


def audit_metrics(data, tie):
    accepted = {}
    for item in data["observations"]:
        row = item["boot_evidence"]
        key = (item["program"], item["architecture"], item["seed"])
        if key in accepted or metrics(row) != item["metrics"]:
            raise ValueError(f"Duplicate or inconsistent academic observation: {key}")
        accepted[key] = row
    pairs, summaries, support = paired_results(accepted, tie)
    if (pairs != data["paired"] or summaries != data["by_program"]
            or support != data["descriptive_support"]
            or any(not math.isclose(x["speedup"], x["frequency_ratio"] / x["cycle_ratio"], rel_tol=1e-12)
                   for x in pairs)):
        raise ValueError("Inconsistent paired metrics or descriptive criterion")


def output_path(directory, output):
    target = output or directory / "academic"
    source = directory.resolve()
    resolved = target.resolve()
    if source.is_relative_to(resolved) or (resolved.is_relative_to(source)
                                            and resolved != source / "academic"):
        raise ValueError("Export target conflicts with campaign evidence")
    return target


def export(directory, config, state, output=None, latex=None):
    target = output_path(directory, output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with exclusive(target.parent / f".{target.name}.export-lock"):
        previous = target.with_name(f".{target.name}.previous")
        if previous.exists() and not target.exists():
            previous.rename(target)
        if target.exists():
            old = build.load_json(target / "manifest.json")
            if old.get("schema") != "frequency-academic-1" or old.get("campaign_id") != config["id"]:
                raise ValueError("Export target already holds another package")
        data = report(directory, config, state, save=False, verbose=False)
        data["schema"] = "frequency-results-1"
        data["evidence_manifest_sha256"] = build.file_fingerprint(directory / "campaign_manifest.json")
        data["workflow_sessions"] = [build.load_json(path) for path in sorted((directory / "sessions").glob("*.json"))]
        tie = config["tie_absolute_speedup"]
        audit_metrics(data, tie)
        with TemporaryDirectory(prefix=".frequency-export-", dir=target.parent) as temporary:
            staged = Path(temporary)
            content(staged, data, tie)
            latex_error = None
            if latex:
                try:
                    compile_pdf(staged, latex)
                except (ValueError, OSError, subprocess.SubprocessError) as error:
                    latex_error = str(error)
            manifest = {
                "schema": "frequency-academic-1", "campaign_id": config["id"],
                "paired": len(data["paired"]), "selected": len(data["observations"]),
                "expected_pairs": 25, "expected_observations": 50,
                "complete": len(data["paired"]) == 25, "tie_absolute_speedup": tie,
                "evidence_manifest_sha256": data["evidence_manifest_sha256"],
                "latex_error": latex_error,
                "files": build.hashes(staged, (path for path in staged.rglob("*") if path.is_file())),
            }
            build.save_json(staged / "manifest.json", manifest)
            if previous.exists():
                shutil.rmtree(previous)
            if target.exists():
                target.rename(previous)
            try:
                staged.rename(target)
            except OSError:
                if previous.exists():
                    previous.rename(target)
                raise
            if previous.exists():
                shutil.rmtree(previous)
    print(f"Academic export: {target} ({manifest['paired']}/25 pairs; {manifest['selected']}/50 configurations)")
    if latex_error:
        raise ValueError(f"LaTeX compilation failed. Review {target / 'latex-build.log'}: {latex_error}")


def verify(directory, output=None, *, portable=False):
    target = output_path(directory, output)
    manifest = build.load_json(target / "manifest.json")
    files = manifest["files"]
    if (manifest.get("schema") != "frequency-academic-1"
            or any(Path(name).is_absolute() or ".." in Path(name).parts for name in files)
            or not build.verify_files(target, files)):
        raise ValueError("Academic package integrity check failed")
    data = build.load_json(target / "data" / "results.json")
    tie = manifest["tie_absolute_speedup"]
    audit_metrics(data, tie)
    if (manifest["paired"] != len(data["paired"]) or manifest["selected"] != len(data["observations"])
            or manifest["complete"] != (len(data["paired"]) == 25)):
        raise ValueError("Academic package completeness is inconsistent")
    with TemporaryDirectory(prefix="frequency-verify-") as temporary:
        expected = Path(temporary)
        content(expected, data, tie)
        rebuilt = build.hashes(expected, (path for path in expected.rglob("*") if path.is_file()))
        if any(files.get(name) != digest for name, digest in rebuilt.items()):
            raise ValueError("Tables, figures and data do not agree with the consolidated observations")
    if not portable:
        config = build.load_json(directory / "campaign_manifest.json")
        state_path = directory / "campaign_state.json"
        state = build.load_json(state_path) if state_path.exists() else {}
        if build.file_fingerprint(directory / "campaign_manifest.json") != manifest["evidence_manifest_sha256"]:
            raise ValueError("Frozen campaign manifest differs from the export")
        live = report(directory, config, state, save=False, verbose=False)
        if any(data[key] != live[key] for key in ("campaign_id", "observations", "paired", "by_program",
                                                 "descriptive_support", "candidates", "selections")):
            raise ValueError("Campaign evidence changed since export; audit and regenerate the academic package")
        if any(row["status"] == "integrity_error" or row["invalid_boot_records"]
               for row in live["candidates"]):
            raise ValueError("The campaign contains candidates with invalid sealed evidence")
    print(f"Verified {len(files)} academic files and {manifest['paired']} paired results.")
