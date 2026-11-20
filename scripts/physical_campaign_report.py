"""Render the verified physical captures and paired comparisons."""

import csv
from statistics import mean, stdev


LABELS = {
    "raw_stress": "Dependencias",
    "load_use_stress": "Carga y uso",
    "branch_stress": "Saltos",
    "m_ext_stress": "Extensión M",
    "coremark": "CoreMark (2000)",
}


def write_csv(path, records):
    if not records:
        return
    fields = list(dict.fromkeys(field for row in records for field in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def write_physical_results(output, captures, issues):
    observations = {}
    for key, row in captures.items():
        cycles = int(row["cycle_count"])
        instructions = int(row["instr_retired"])
        seconds = cycles / (float(row["clock_mhz"]) * 1e6)
        observations[key] = {
            **row, "seconds_nominal": seconds, "cpi_exact": cycles / instructions,
            "ipc": instructions / cycles, "instructions_per_second": instructions / seconds,
        }
    write_csv(output / "results/physical_observations.csv",
              [row for _, row in sorted(observations.items())])
    lines = ["", "## Campaña física por programa y semilla", "",
             f"Observaciones aceptadas: {len(observations)}/50.", ""]
    if issues:
        return lines

    summaries = {}
    pairs = []
    for program in LABELS:
        group = []
        for seed in range(1, 6):
            mono = observations["single_cycle", program, seed]
            seg = observations["pipeline", program, seed]
            ratio = int(seg["cycle_count"]) / int(mono["cycle_count"])
            group.append({
                "program": program, "seed": seed,
                "mono_seconds": mono["seconds_nominal"], "seg_seconds": seg["seconds_nominal"],
                "required_clock_ratio": ratio,
                "nominal_speedup": mono["seconds_nominal"] / seg["seconds_nominal"],
                "projected_speedup": float(seg["fmax_mhz"]) / float(mono["fmax_mhz"]) / ratio,
            })
        pairs.extend(group)
        nominal = [row["nominal_speedup"] for row in group]
        projected = [row["projected_speedup"] for row in group]
        summaries[program] = (
            mean(row["mono_seconds"] for row in group),
            mean(row["seg_seconds"] for row in group),
            mean(row["required_clock_ratio"] for row in group),
            mean(nominal), stdev(nominal), mean(projected), stdev(projected),
        )
    write_csv(output / "results/physical_seed_pairs.csv", pairs)

    lines += ["| Programa | Mono. (s) | Seg. (s) | Reloj de empate seg./mono. | Acel. a 40/50 MHz | Acel. a Fmax |",
              "|---|---:|---:|---:|---:|---:|"]
    for program, (mono, seg, ratio, nominal, nominal_std, projected, projected_std) in summaries.items():
        lines.append(f"| {LABELS[program]} | {mono:.8g} | {seg:.8g} | {ratio:.4f} | "
                     f"{nominal:.4f} ± {nominal_std:.4f} | {projected:.4f} ± {projected_std:.4f} |")

    mono, seg, ratio, nominal, nominal_std, _, _ = summaries["coremark"]
    favorable = nominal - nominal_std > 1
    outcome = ("El resultado cumple el criterio descriptivo de ventaja segmentada."
               if favorable else "El resultado queda por debajo del umbral de ventaja segmentada."
               if nominal - nominal_std < 1 else "El resultado coincide con el umbral de la regla descriptiva.")
    lines += ["", f"CoreMark a 40/50 MHz. {outcome}", "",
              "La dispersión corresponde a cinco semillas. El tiempo nominal se deriva de los "
              "contadores de la placa y la proyección a Fmax usa el informe del bitstream del mismo programa.",
              "Los CSV physical_observations.csv y physical_seed_pairs.csv conservan los datos por semilla."]

    prose = (
        rf"En CoreMark de 2000 iteraciones, el tiempo derivado de los contadores fue "
        rf"\SI{{{mono:.6f}}}{{\second}} en monociclo a \SI{{40}}{{\mega\hertz}} y "
        rf"\SI{{{seg:.6f}}}{{\second}} en segmentada a \SI{{50}}{{\mega\hertz}}. "
        rf"La aceleración media fue \num{{{nominal:.4f}}} y el cociente de frecuencias "
        rf"necesario para igualar el tiempo fue \num{{{ratio:.4f}}}. {outcome}"
    )
    english = (
        f"For 2000-iteration CoreMark, the counter-derived execution times were "
        f"{mono:.6f} s at 40 MHz for the single-cycle processor and "
        f"{seg:.6f} s at 50 MHz for the five-stage processor. "
        f"The mean speedup was {nominal:.4f}."
    )
    (output / "thesis/tables/physical_coremark.tex").write_text(
        rf"\renewcommand{{\ResultadoCoreMarkFisico}}{{{prose}}}" + "\n"
        + rf"\newcommand{{\CoreMarkBoardResult}}{{{english}}}" + "\n", encoding="utf-8")
    latex = [
        r"\begin{table}[H]", r"\centering", r"\small",
        r"\caption{Resultados de cinco semillas por carga. Los tiempos se derivan "
        r"de los contadores a 40 y 50 MHz. Las aceleraciones indican media y "
        r"desviación estándar muestral.}",
        r"\label{tab:resultados_placa_final}",
        r"\resizebox{\linewidth}{!}{%", r"\begin{tabular}{lrrrrr}", r"\toprule",
        r"Carga & Mono. (s) & Seg. (s) & $f_\mathrm{seg}/f_\mathrm{mono}$ de empate "
        r"& Acel. en placa & Acel. a Fmax \\", r"\midrule",
    ]
    for program, values in summaries.items():
        mono, seg, ratio, nominal, nominal_std, projected, projected_std = values
        cells = [LABELS[program], rf"\num{{{mono:.8g}}}", rf"\num{{{seg:.8g}}}",
                 rf"\num{{{ratio:.4f}}}", rf"\num{{{nominal:.4f}}} $\pm$ \num{{{nominal_std:.4f}}}",
                 rf"\num{{{projected:.4f}}} $\pm$ \num{{{projected_std:.4f}}}"]
        latex.append(" & ".join(cells) + r" \\")
    latex += [r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table}"]
    (output / "thesis/tables/physical_campaign.tex").write_text(
        "\n".join(latex) + "\n", encoding="utf-8")
    return lines
