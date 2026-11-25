"""Formatea en LaTeX los resultados auditados de la campaña de frecuencia."""

from collections import Counter
from math import ceil, nan
from statistics import mean, stdev

from physical_campaign_report import LABELS


ARCHES = {"single_cycle": "Monociclo", "pipeline": "Segmentada"}
ARCH_STYLES = {
    "single_cycle": ("fcmono", "*", "o", -0.23),
    "pipeline": ("fcseg", "square*", "square", 0.23),
}
PALETTE = (
    r"\definecolor{fcmono}{HTML}{24557B}",
    r"\definecolor{fcseg}{HTML}{B65536}",
    r"\definecolor{fcgrid}{HTML}{E1E7EC}",
)
GENERATED = "% Generado por scripts/frequency_latex.py a partir de la exportación auditada."
X_ERROR = "error bars/.cd,x dir=both,x explicit,error bar style={line width=.85pt}"
SPEED_LABEL = r"Aceleración \(S=T_{\mathrm{mono}}/T_{\mathrm{seg}}\)"

# Reconstrucción de los cuatro ejecutables sintéticos para la revisión verificada.
# Los valores son redirecciones en la segmentada, esperas de carga y uso en la
# segmentada y retenciones del divisor compartido. El llenado segmentado añade
# cuatro ciclos. Cada balance se contrasta con los contadores de placa.
BALANCE_RTL = "e42120a82a3c48cc588c8a053810e91db8f8a3b24ff5073c3fbc9afc3d7988f0"
BALANCE_INPUTS = {
    "raw_stress": ("436b5ea23c52dd4dc6f3f6f5e2f7cb02e46c2dc22107cd3bdf15843f979c01b4", 142, 0, 0),
    "load_use_stress": ("fb0f7225235e2b30e86e9d284975dab5b2d40990c333de3fe196c2d05e8c2673", 110, 888, 0),
    "branch_stress": ("dd0230a5feddf7c463cf11092643c5add99b459482e703f25602987ddb112d97", 1999, 0, 0),
    "m_ext_stress": ("d6dc47bddf1de31c556c57a3f4220b686a26bf461af1247e08ee538c7fdc2ccd", 29, 0, 1020),
}


def num(value, digits=0):
    return rf"\num{{{value:.{digits}f}}}"


def relative_change(mono, segmented):
    return 100 * (segmented / mono - 1)


def percent(value, digits=1):
    literal = f"{value:+.{digits}f}" if value else "0"
    return rf"\num[retain-explicit-plus=true]{{{literal}}}\,\%"


def deviation(values):
    return stdev(values) if len(values) > 1 else 0


def stat_cell(values, digits, sd_digits=None):
    if not values:
        return "--"
    center = num(mean(values), digits)
    if len(values) == 1 or min(values) == max(values):
        return center
    sd_digits = digits if sd_digits is None else sd_digits
    return rf"{center} \(\pm\) {num(stdev(values), sd_digits)}"


def count_cell(values):
    if not values:
        return "--"
    low, high = min(values), max(values)
    return num(low) if low == high else f"{num(low)}--{num(high)}"


def write_rows(directory, name, rows):
    lines = [GENERATED, *rows]
    (directory / f"{name}.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def row(cells, suffix=""):
    return " & ".join(cells) + r" \\" + suffix


def by_architecture(observations):
    grouped = {(program, arch): [] for program in LABELS for arch in ARCHES}
    for item in observations:
        grouped[item["program"], item["architecture"]].append(item)
    return grouped


def group_values(grouped, program, arch, field, scale=1):
    return [item[field] * scale for item in grouped[program, arch] if item[field] is not None]


def coremark_means(grouped, field):
    values = [group_values(grouped, "coremark", arch, field) for arch in ARCHES]
    return tuple(mean(group) for group in values) if all(values) else None


def synthetic_balances(data):
    verified = {(program, arch): [] for program in BALANCE_INPUTS for arch in ARCHES}
    for item in data["observations"]:
        key = item["program"], item["architecture"]
        if key in verified:
            verified[key].append(item["boot_evidence"])
    balances = {}
    for program, (elf, jumps, loads, division) in BALANCE_INPUTS.items():
        components = {}
        for arch, extra in (
            ("single_cycle", (0, 0, division, 0)),
            ("pipeline", (jumps, loads, division, 4)),
        ):
            rows = verified[program, arch]
            if not rows or any((item["elf_sha256"], item["rtl_sha256"]) != (elf, BALANCE_RTL) for item in rows):
                break
            totals = {(item["instr_retired"], item["cycle_count"]) for item in rows}
            if len(totals) != 1:
                raise ValueError(f"Los contadores del balance difieren entre semillas: {program}/{arch}")
            retired, cycles = totals.pop()
            components[arch] = (retired, *extra)
            if sum(components[arch]) != cycles:
                raise ValueError(f"El balance reconstruido no coincide con el contador: {program}/{arch}")
        if len(components) == len(ARCHES):
            balances[program] = components
    return balances


def aligned_count(values):
    return str(values[0]) if values and min(values) == max(values) else "{" + count_cell(values) + "}"


def aligned_stat(values, digits, uncertainty=False):
    if not values:
        return "{--}"
    center = f"{mean(values):.{digits}f}"
    if uncertainty and len(values) > 1 and min(values) != max(values):
        return f"{center}({deviation(values) * 10 ** digits:.0f})"
    return center


def coremark_summary(directory, data, grouped):
    lines = []
    for field, name, precision in (
        ("fmax_mhz", "Fmax", 3), ("effective_mhz", "Clock", 2), ("nominal_seconds", "Time", 3),
    ):
        values = coremark_means(grouped, field)
        if values:
            lines.extend(rf"\newcommand{{\FcCoremark{name}{arch}}}{{{value:.{precision}f}}}"
                         for arch, value in zip(("Mono", "Seg"), values))
    if "coremark" in data["by_program"]:
        speedup = data["by_program"]["coremark"]["mean"]
        lines.append(rf"\newcommand{{\FcCoremarkSpeedup}}{{{speedup:.4f}}}")
    write_rows(directory, "coremark_resumen", lines)


def thesis_table_rows(directory, data, observations):
    grouped = by_architecture(observations)

    def values(program, arch, field, scale=1):
        return group_values(grouped, program, arch, field, scale)

    hardware, times, metrics, hypothesis, pairs, balance = [], [], [], [], [], []
    for field, label, digits, sd_digits in (
        ("fmax_mhz", "Fmax (MHz)", 3, 3), ("alms", "ALM", 1, 1),
        ("registers", "Registros", 1, 1), ("ram_blocks", "Bloques M10K", 0, 1),
        ("dsp_blocks", "Bloques DSP", 0, 1),
    ):
        cells = [stat_cell(values("coremark", arch, field), digits, sd_digits) for arch in ARCHES]
        values_by_arch = coremark_means(grouped, field)
        variation = percent(relative_change(*values_by_arch), 2) if values_by_arch else "--"
        hardware.append(row([label, *cells, variation]))

    for program, components in synthetic_balances(data).items():
        retired, jumps, loads, divisor, fill = components["pipeline"]
        mono, segmented = (sum(components[a]) for a in ARCHES)
        balance.append(row([LABELS[program], *map(num, (retired, jumps, loads, divisor, fill,
                                                       mono, segmented, segmented - mono)),
                            percent(relative_change(mono, segmented), 2)]))

    for program, label in LABELS.items():
        scale, unit = (1, r"\si{\second}") if program == "coremark" else (1e6, r"\si{\micro\second}")
        if any(grouped[program, arch] for arch in ARCHES):
            frequency = [stat_cell(values(program, arch, "effective_mhz"), 2) for arch in ARCHES]
            duration = [stat_cell(values(program, arch, "nominal_seconds", scale), 3) for arch in ARCHES]
            times.append(row([label, *frequency, *duration, unit]))
            retired = aligned_count([n for arch in ARCHES for n in values(program, arch, "instructions_retired")])
            cycles = [aligned_count(values(program, arch, "cycles")) for arch in ARCHES]
            cpi = [aligned_stat(values(program, arch, "cpi"), 4) for arch in ARCHES]
            rate = [aligned_stat(values(program, arch, "instructions_per_second", 1e-6), 2, uncertainty=True)
                    for arch in ARCHES]
            metrics.append(row([label, retired, *cycles, *cpi, *rate]))

        if program in data["by_program"]:
            stats = data["by_program"][program]
            sd = stats["sample_sd"]
            verdict = stats["meets_descriptive_rule"]
            winner = max(ARCHES, key=lambda arch: stats[arch])
            favored = ARCHES[winner] if stats["pipeline"] != stats["single_cycle"] else "Sin mayoría"
            hypothesis.append(row([
                label, num(stats["mean"], 4), "--" if sd is None else num(sd, 4),
                num(stats["minimum"], 4), num(stats["maximum"], 4),
                "--" if sd is None else num(stats["mean"] - sd, 4),
                "--" if verdict is None else ("Sí" if verdict else "No"), favored,
            ]))

        selected = sorted((item for item in data["paired"] if item["program"] == program),
                          key=lambda item: item["seed"])
        if selected and pairs:
            pairs.append(r"\addlinespace[0.35em]")
        for i, item in enumerate(selected):
            pairs.append(row([
                label if i == 0 else "", str(item["seed"]),
                *[num(item[f"{arch}_mhz"], 3 if item[f"{arch}_mhz"] % 1 else 0) for arch in ARCHES],
                *[num(item[arch]["nominal_seconds"] * scale, 3) for arch in ARCHES],
                unit, num(item["speedup"], 4),
            ], suffix="*" if i < len(selected) - 1 else ""))

    for name, rows in (
        ("resumen_recursos_filas", hardware), ("resumen_tiempos_filas", times),
        ("resumen_metricas_filas", metrics), ("criterio_descriptivo_filas", hypothesis),
        ("pares_filas", pairs), ("balance_ciclos_filas", balance),
    ):
        write_rows(directory, name, rows)
    coremark_summary(directory, data, grouped)


def axis_options(labels, xlabel, extra=""):
    ticks = ",".join(str(i) for i in range(1, len(labels) + 1))
    texts = ",".join("{" + item + "}" for item in labels)
    return (
        r"width=.72\linewidth,height=5.5cm,scale only axis,"
        r"axis lines=left,axis line style={gray!70},tick align=outside,"
        r"tick label style={font=\small},label style={font=\small},"
        r"xmajorgrids,grid style={fcgrid},ytick style={draw=none},y dir=reverse,"
        rf"ytick={{{ticks}}},yticklabels={{{texts}}},ymin=.5,ymax={len(labels) + .5},"
        r"scaled x ticks=false,xticklabel style={/pgf/number format/use comma,"
        r"/pgf/number format/1000 sep={\,}},"
        r"legend style={at={(0,1.06)},anchor=south west,legend columns=2,"
        r"column sep=5pt,cells={anchor=west},draw=none,font=\small,fill=none},"
        rf"xlabel={{{xlabel}}},{extra}"
    )


def plot(directory, name, *axes):
    lines = [GENERATED, r"\begin{tikzpicture}", *PALETTE]
    for options, series, *annotations in axes:
        lines.append(rf"\begin{{axis}}[{options}]")
        for style, legend, points in series:
            data = " ".join(
                f"({x:.12g},{y:.12g})" + (f" +- ({spread[0]:.12g},0)" if spread else "")
                for x, y, *spread in points
            )
            lines.append(rf"  \addplot[{style}] coordinates {{{data}}};")
            if legend:
                lines.append(rf"  \addlegendentry{{{legend}}}")
        if annotations:
            lines.extend(annotations[0])
        lines.append(r"\end{axis}")
    lines.append(r"\end{tikzpicture}")
    (directory / f"{name}.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def label_at(x, y, text, style="anchor=west"):
    return rf"  \node[font=\scriptsize,inner sep=2pt,{style}] at (axis cs:{x:.10g},{y:.10g}) {{{text}}};"


def bars_by_arch(grouped, groups, field, scale=1, precision=2, spread=False):
    series, notes = [], []
    for arch, label in ARCHES.items():
        color, _, _, offset = ARCH_STYLES[arch]
        points = []
        for program, i in groups.items():
            values = group_values(grouped, program, arch, field, scale)
            if values:
                center = (mean(values), i + offset)
                points.append((*center, deviation(values)) if spread else center)
                notes.append(label_at(center[0] + (deviation(values) if spread else 0), center[1],
                                      num(center[0], precision), f"anchor=west,text={color}"))
        if points:
            style = f"fill={color},draw=none,bar shift=0pt"
            error_style = X_ERROR + ",error bar style/.append style={draw=black!75}"
            series.append((f"{style},{error_style}" if spread else style, label, points))
    return series, notes


def frequency_figure(directory, grouped, groups, labels):
    frequencies = [item[key] for entries in grouped.values() for item in entries
                   for key in ("effective_mhz", "restricted_mhz") if item[key] is not None]
    common = (f"height=3.85cm,xmin={min(frequencies) - 1:.5f},xmax={max(frequencies) + 1:.5f},"
              r"title style={at={(0,1.02)},anchor=south west,font=\small\bfseries},"
              r"legend style={at={(1,1.04)},anchor=south east}")
    axes = []
    for arch, title in ARCHES.items():
        color, solid, hollow, _ = ARCH_STYLES[arch]
        validated, restricted, links = [], [], []
        for program, i in groups.items():
            for item in grouped[program, arch]:
                y = i + (item["seed"] - 3) * .145
                val, est = item["effective_mhz"], item["restricted_mhz"]
                if val is not None:
                    validated.append((val, y))
                if est is not None:
                    restricted.append((est, y))
                if val is not None and est is not None:
                    links.extend([(val, y), (est, y), (nan, nan)])
        top = arch == "single_cycle"
        options = common + (r",name=mono,xticklabel={\phantom{0}}" if top else
                            r",at={(mono.south west)},anchor=north west,yshift=-1.15cm")
        series = [
            (f"{color}!55,no marks,forget plot,line width=.55pt,unbounded coords=jump", None, links),
            (f"{color},only marks,mark={solid},mark size=1.65pt", "Validada en placa" if top else None, validated),
            (f"{color},only marks,mark={hollow},mark size=1.75pt",
             r"$f_{\max}$ restringida" if top else None, restricted),
        ]
        axes.append((axis_options(labels, "" if top else "Frecuencia (MHz)", f"{options},title={{{title}}}"),
                     [entry for entry in series if entry[2]]))
    plot(directory, "frecuencias", *axes)


def resources_figure(directory, grouped):
    metrics = ("alms", "registers")
    groups = {key: i for i, key in enumerate(metrics, 1)}
    series, notes = [], []
    for arch, label in ARCHES.items():
        color, _, _, offset = ARCH_STYLES[arch]
        points = []
        for field, i in groups.items():
            values = group_values(grouped, "coremark", arch, field)
            if values:
                center = mean(values)
                points.append((center, i + offset))
                text = rf"\num[group-digits=integer,group-minimum-digits=4,group-separator={{\,}}]{{{center:.1f}}}"
                if arch == "pipeline" and (pair := coremark_means(grouped, field)):
                    text += rf"\quad ({percent(relative_change(*pair))})"
                notes.append(label_at(center, i + offset, text, f"anchor=west,text={color}"))
        if points:
            series.append((f"fill={color},draw=none,bar shift=0pt", label, points))
    if series:
        plot(directory, "recursos", (
            axis_options(["ALM", "Registros"], "Cantidad utilizada",
                         "xbar,bar width=10pt,xmin=0,height=3cm,xtick distance=2000,"
                         "enlarge x limits={upper,value=.38}"),
            series, notes,
        ))


def performance_figure(directory, grouped, groups, labels):
    bar_options = r"xbar,bar width=5.8pt,width=.31\linewidth,xmin=0,enlarge x limits={upper,value=.24}"
    cpi = axis_options(labels, "Ciclos por instrucción", bar_options + ",name=cpi")
    rate = axis_options(labels, "Millones de instrucciones/s", bar_options +
                        r",at={(cpi.east)},anchor=west,xshift=1.05cm,ytick=\empty")
    cpi_series, cpi_labels = bars_by_arch(grouped, groups, "cpi")
    rate_series, rate_labels = bars_by_arch(grouped, groups, "instructions_per_second", 1e-6, spread=True)
    plot(directory, "rendimiento", (cpi, cpi_series, cpi_labels),
         (rate, [(style, None, points) for style, _, points in rate_series], rate_labels))


def balance_figure(directory, balances):
    if not balances:
        return
    series, notes = [], []
    for component, label, color in (
        (0, "Ejecución base", "fcmono!45"), (1, "Saltos", "fcseg!80"),
        (2, "Carga y uso", "fcmono!85"), (3, "División", "fcseg!48"),
        (4, "Llenado", "black!55"),
    ):
        points = []
        for i, parts in enumerate(balances.values(), 1):
            for arch in ARCHES:
                arch_color, _, _, offset = ARCH_STYLES[arch]
                values = parts[arch]
                y = i + offset
                points.append((values[component] / values[0], y))
                if component == 0:
                    total = sum(values) / values[0]
                    notes.append(label_at(total, y, num(total, 2), f"anchor=west,text={arch_color}"))
        series.append((f"fill={color},draw=none,bar shift=0pt", label, points))
    ticks, names = [], []
    for i, program in enumerate(balances, 1):
        for arch, abbreviation in (("single_cycle", "Mono."), ("pipeline", "Seg.")):
            ticks.append(f"{i + ARCH_STYLES[arch][3]:.2f}")
            names.append(f"{{{LABELS[program]} ({abbreviation})}}")
    options = axis_options(
        [LABELS[p] for p in balances], "Ciclos por instrucción retirada",
        r"xbar stacked,bar width=10pt,xmin=0,width=.67\linewidth,height=6.5cm,"
        r"legend style={legend columns=5,font=\footnotesize,column sep=4pt},"
        f"ytick={{{','.join(ticks)}}},yticklabels={{{','.join(names)}}},"
        "enlarge x limits={upper,value=.13}",
    )
    plot(directory, "composicion_cpi", (options, series, notes))


def cycle_increase_figure(directory, pairs):
    values = [mean(row["required_frequency_increase_pct"] for row in rows) for rows in pairs.values()]
    coords = list(zip(values, range(1, len(values) + 1)))
    notes = [label_at(value, i, percent(value, 2), "anchor=west,text=fcseg") for value, i in coords]
    options = axis_options([LABELS[p] for p in pairs], r"Incremento de ciclos respecto al monociclo (\%)",
                           "xbar,bar width=11pt,height=4.4cm,xmin=0,enlarge x limits={upper,value=.17}")
    plot(directory, "incremento_ciclos", (options, [("fill=fcseg,draw=none", None, coords)], notes))


def compensation_figure(directory, pairs):
    # The two axes use percentages of the paired single-cycle baseline.
    points = {p: [(r["required_frequency_increase_pct"], r["achieved_frequency_increase_pct"])
                  for r in rows] for p, rows in pairs.items()}
    flat = [point for group in points.values() for point in group]
    xmin = min(0, 10 * int(min(x for x, _ in flat) // 10))
    ymin = min(0, 10 * int(min(y for _, y in flat) // 10))
    xmax = max(40, 10 * ceil((max(x for x, _ in flat) + 5) / 10))
    ymax = max(50, 10 * ceil((max(y for _, y in flat) + 8) / 10))
    high = min(xmax, ymax)
    low = max(xmin, ymin)
    north = [(xmin, ymax), (high, ymax), (high, high), (low, low), (xmin, ymin), (xmin, ymax)]
    south = [(xmin, ymin), (low, low), (high, high), (xmax, ymax), (xmax, ymin), (xmin, ymin)]
    series = [
        ("draw=none,fill=fcseg!11,fill opacity=.82,forget plot", None, north),
        ("draw=none,fill=fcmono!10,fill opacity=.82,forget plot", None, south),
        ("gray!80,dashed,no marks,line width=.8pt", "Igual tiempo", [(low, low), (high, high)]),
    ]
    scatter_styles = ("mark=*", "mark=square*", "mark=triangle*", "mark=diamond*", "mark=pentagon*")
    notes = [
        label_at(xmin + 1, ymax - 3, "Menor tiempo en segmentada", "anchor=west,text=fcseg,font=\\small\\bfseries"),
        label_at(xmax - 2, ymin + 3, "Menor tiempo en monociclo", "anchor=east,text=fcmono,font=\\small\\bfseries"),
    ]
    for (program, group), style in zip(points.items(), scatter_styles):
        series.append((f"only marks,black!83,mark size=2.1pt,{style}", LABELS[program], group))
        for (x, y), count in Counter(group).items():
            if count > 1:
                notes.append(label_at(x + .6, y, rf"\(\times {count}\)", "anchor=west,text=black!78"))
    # The verified campaign is nonnegative in both axes. If a future campaign
    # crosses zero, use the equality line without shading to keep regions exact.
    if xmin or ymin:
        series = series[2:]
        notes = notes[2:]
    options = (
        r"width=.81\linewidth,height=6.8cm,scale only axis,axis lines=left,"
        r"tick label style={font=\small,/pgf/number format/use comma},"
        r"label style={font=\small},grid=major,grid style={fcgrid},"
        r"legend style={at={(.5,1.06)},anchor=south,legend columns=3,column sep=5pt,"
        r"cells={anchor=west},draw=none,font=\footnotesize},"
        r"xlabel={Incremento de ciclos (\%)},ylabel={Incremento de frecuencia (\%)},"
        f"xmin={xmin},xmax={xmax},ymin={ymin},ymax={ymax}"
    )
    plot(directory, "compensacion", (options, series, notes))


def speedup_figures(directory, data, pairs, comparisons):
    labels = [LABELS[p] for p in pairs]
    groups = {program: i for i, program in enumerate(pairs, 1)}
    equality_line = [(1, .5), (1, len(labels) + .5)]
    equality = ("gray!75,dashed,no marks,line width=.8pt", "Igual tiempo", equality_line)
    pair_points = [(item["speedup"], i - .19 + (item["seed"] - 3) * .119)
                   for program, i in groups.items() for item in pairs[program]]
    centers = [(data["by_program"][program]["mean"], i + .25,
                data["by_program"][program]["sample_sd"] or 0) for program, i in groups.items()]
    plot(directory, "aceleracion", (
        axis_options(labels, SPEED_LABEL, "height=6.8cm,enlarge x limits=.12"),
        [equality, ("only marks,black!53,mark=*,mark size=1.9pt", "Pares por semilla", pair_points),
         (f"only marks,fcseg,mark=diamond*,mark size=3pt,{X_ERROR}", r"Media \(\pm\) 1 DE", centers)],
    ))

    comparison_series, notes = [equality], []
    for key, label, offset, style in (
        ("original_40_50_speedup", "Relojes fijos", -.27, "fcmono,mark=square*"),
        ("projected_historical_fmax_speedup", r"Proyección preliminar a \(f_{\max}\)", 0, "black!55,mark=o"),
        ("validated_frequency_speedup", "Relojes validados", .27, "fcseg,mark=diamond*"),
    ):
        points = []
        for program, i in groups.items():
            values = [item[key] for item in comparisons if item["program"] == program and item[key] is not None]
            if values:
                center, spread = mean(values), deviation(values)
                points.append((center, i + offset, spread))
                if program == "coremark":
                    notes.append(label_at(center + spread + .008, i + offset, num(center, 4)))
        if points:
            comparison_series.append((f"only marks,{style},mark size=2.4pt,{X_ERROR}", label, points))
    plot(directory, "condiciones", (
        axis_options(labels, SPEED_LABEL, "height=6.1cm,enlarge x limits=.11"), comparison_series, notes,
    ))


def coremark_tradeoff(directory, grouped, pairs):
    if "coremark" not in pairs:
        return
    fields = ("fmax_mhz", "effective_mhz", "alms", "registers")
    values = [coremark_means(grouped, field) for field in fields]
    if not all(values):
        return
    fmax, clock, alms, registers = (relative_change(*group) for group in values)
    rows = pairs["coremark"]
    cycles = mean(row["required_frequency_increase_pct"] for row in rows)
    speedup = 100 * (mean(row["speedup"] for row in rows) - 1)
    metrics = ("Frecuencia máxima estimada", "Frecuencia validada media", "Aceleración media",
               "Ciclos de ejecución", "ALM", "Registros")
    gains = [(value, i) for i, value in enumerate((fmax, clock, speedup), 1)]
    costs = [(value, i) for i, value in enumerate((cycles, alms, registers), 4)]
    notes = [label_at(value, i, percent(value, 2)) for value, i in (*gains, *costs)]
    plot(directory, "compromiso_coremark", (
        axis_options(metrics, r"Variación respecto al monociclo (\%)",
                     r"xbar,bar width=10pt,width=.61\linewidth,height=5.25cm,xmin=0,"
                     "enlarge x limits={upper,value=.20}"),
        [("fill=fcseg,draw=none,bar shift=0pt", "Frecuencia y desempeño", gains),
         ("fill=black!42,draw=none,bar shift=0pt", "Ciclos y recursos", costs)], notes,
    ))


def academic_figures(directory, data, observations, comparisons):
    if not observations:
        return
    grouped = by_architecture(observations)
    programs = [program for program in LABELS if any(grouped[program, arch] for arch in ARCHES)]
    labels = [LABELS[program] for program in programs]
    groups = {program: i for i, program in enumerate(programs, 1)}
    frequency_figure(directory, grouped, groups, labels)
    resources_figure(directory, grouped)
    performance_figure(directory, grouped, groups, labels)
    balance_figure(directory, synthetic_balances(data))
    if data["paired"]:
        pairs = {p: [row for row in data["paired"] if row["program"] == p]
                 for p in LABELS if p in data["by_program"]}
        cycle_increase_figure(directory, pairs)
        compensation_figure(directory, pairs)
        speedup_figures(directory, data, pairs, comparisons)
        coremark_tradeoff(directory, grouped, pairs)


