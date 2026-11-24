"""Generate conservative PLL requests and evaluate fitted TimeQuest evidence."""
import csv
import math
import re
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from vga_timing import CORNERS, summarize

REFERENCE_MHZ = 50
ANALYSES = {
    "setup", "hold", "recovery", "removal", "payload_setup", "dac_setup",
    "dac_hold", "sync_setup", "sync_hold", "pulse_width",
}


@lru_cache(maxsize=1)
def legal_ratios() -> set[Fraction]:
    # Integer-mode Cyclone V C6: PFD >= 5 MHz, VCO 600–1600 MHz.
    # An even output counter permits a 50% waveform without rounding.
    return {
        Fraction(m, n * c)
        for n in range(1, 11)
        for m in range(12 * n, 32 * n + 1)
        for c in range(10, 42, 2)
        if 39 <= Fraction(50 * m, n * c) <= 63
    }


def clock_request(requested: int) -> dict:
    if type(requested) is not int or not 40 <= requested <= 63:
        raise ValueError("Expected a frequency request in 40–63 MHz")
    valid = [ratio for ratio in legal_ratios()
             if requested - 1 < REFERENCE_MHZ * ratio <= requested]
    if not valid:
        return {"requested_mhz": requested, "realizable": False}
    ratio = max(valid)
    return {
        "requested_mhz": requested, "realizable": True,
        "reference_mhz": REFERENCE_MHZ, "multiply_by": ratio.numerator,
        "divide_by": ratio.denominator, "nominal_ratio": str(ratio),
        "expected_mhz": float(REFERENCE_MHZ * ratio),
        "phase_ps": 0, "duty_cycle_percent": 50,
    }


def clock_rows(path: Path) -> dict:
    result = {}
    for raw in path.read_text(errors="replace").splitlines():
        fields = [x.strip() for x in raw.strip().strip(";").split(";")]
        if raw.startswith(";") and len(fields) >= 7 and fields[1] in ("Base", "Generated"):
            result[fields[0]] = fields[1:]
    return result


def fitted_clock(path: Path, request: dict) -> dict:
    clocks = clock_rows(path)
    names = [name for name in clocks if "u_cpu_pll" in name and name.endswith("|divclk")]
    if len(names) != 1 or "clk" not in clocks or "vga_dac_clock" not in clocks:
        raise ValueError("Missing, ambiguous or underconstrained fitted CPU/VGA clocks")
    name = names[0]
    row = clocks[name]
    period, rise, fall = map(float, (row[1], row[3], row[4]))
    if abs(float(clocks["clk"][1]) - 20) > .001:
        raise ValueError("Fitted clock reference differs from 50 MHz")
    # Nested generated clocks express the physical counter ratios. Use those
    # ratios for the nominal frequency, and independently check the waveform.
    parent = name
    ratio = Fraction(1)
    visited = set()
    chain = []
    while parent != "clk":
        if parent in visited or parent not in clocks:
            raise ValueError("Invalid TimeQuest generated-clock chain")
        visited.add(parent)
        fields = clocks[parent]
        divide, multiply = int(fields[6]), int(fields[7])
        chain.append({"clock": parent, "multiply": multiply, "divide": divide})
        ratio *= Fraction(multiply, divide)
        parent = fields[13]
    if ratio != Fraction(request["nominal_ratio"]):
        raise ValueError(f"Fitted PLL ratio {ratio} differs from request {request['nominal_ratio']}")
    frequency = REFERENCE_MHZ * ratio
    if (abs(period - float(1000 / frequency)) > .002 or abs(rise) > .002
            or abs(fall - period / 2) > .002):
        raise ValueError("Fitted PLL period, phase or duty cycle differs from the clock configuration")
    return {"effective_mhz": float(frequency), "period_ns": period, "rise_ns": rise,
            "fall_ns": fall, "fitted_clock": name, "derived_clock_chain": chain}


def clock_transfer_coverage(directory: Path, clock: str, architecture: str) -> dict:
    """Check the fitted CPU, crossing and DAC relationships in setup and hold."""
    sections = {}
    name = None
    for line in (directory / "transfers.rpt").read_text(errors="replace").splitlines():
        if not line.startswith(";"):
            continue
        fields = [value.strip() for value in line.strip().strip(";").split(";")]
        if len(fields) == 1 and fields[0].endswith("Transfers"):
            name = fields[0].split()[0].lower()
            if name not in {"setup", "hold"}:
                break
            sections[name] = {}
        if name is None or len(fields) != 6 or fields[0] == "From Clock":
            continue
        source, target, rr, fr, rf, ff = fields
        if source == clock and target == clock:
            sections[name]["cpu"] = {"rr": rr, "fr": int(fr), "rf": int(rf), "ff": int(ff)}
        elif source == clock and "u_vga_pll" in target:
            sections[name]["cpu_to_vga"] = int(rr)
        elif target == clock and "u_vga_pll" in source:
            sections[name]["vga_to_cpu"] = int(rr)
        elif target == "vga_dac_clock" and "u_vga_pll" in source:
            sections[name]["dac"] = int(rr)
    if sections.keys() != {"setup", "hold"}:
        raise ValueError("Missing setup/hold clock-transfer evidence")
    for name, edges in sections.items():
        cpu_edges = edges.get("cpu", {})
        if (cpu_edges.get("rr", "0") == "0" or edges.get("dac") != 25
                or not edges.get("cpu_to_vga") or not edges.get("vga_to_cpu")):
            raise ValueError(f"Missing CPU, CPU–VGA or DAC paths in {name} transfers")
        if architecture == "single_cycle" and (not cpu_edges["fr"] or not cpu_edges["rf"]):
            raise ValueError(f"Missing single-cycle half-period paths in {name} transfers")
    return sections


def fmax_rows(report: Path, name: str) -> dict:
    values = {}
    corner = None
    for line in report.read_text(errors="replace").splitlines():
        match = re.match(r"; (Slow|Fast) 1100mV (0|85)C [Mm]odel Fmax Summary", line)
        if match:
            corner = f"{match[1].lower()}_{match[2]}C"
        match = re.match(r";\s*([\d.]+) MHz\s*;\s*([\d.]+) MHz\s*;\s*([^;]+?)\s*;", line)
        if corner and match and match[3] == name:
            values[corner] = {"fmax_mhz": float(match[1]), "restricted_mhz": float(match[2])}
    if "slow_85C" not in values:
        raise ValueError("Missing CPU Fmax at slow 85 C")
    return values


def physical_timing(directory: Path) -> tuple[dict, list[str]]:
    log = (directory / "timequest.log").read_text(errors="replace")
    if "PHYSICAL_TIMING_REPORT_COMPLETE" not in log:
        raise ValueError("TimeQuest did not complete")
    if "No ignored assignments to report" not in log:
        if (directory / "constraints.rpt").stat().st_size == 0:
            raise ValueError("Missing ignored SDC evidence")
        raise ValueError("Review ignored SDC assignments")
    counts = re.findall(
        r"; (?:Illegal Clocks|Unconstrained [^;]+?)\s*;\s*(\d+)\s*;\s*(\d+)\s*;",
        (directory / "unconstrained.rpt").read_text(),
    )
    if len(counts) != 6:
        raise ValueError("Incomplete unconstrained-path report")
    violations = ["Illegal or unconstrained endpoints"] if any(
        (a, b) != ("0", "0") for a, b in counts) else []
    checks = {}
    expected = {f"{model}_{temp}C/{analysis}" for model, temp in CORNERS for analysis in ANALYSES}
    with (directory / "summary.tsv").open() as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            analysis = row["analysis"]
            key = f"{row['corner']}/{analysis}"
            if key in checks or key not in expected:
                raise ValueError(f"Unexpected or duplicate TimeQuest analysis: {key}")
            paths, slack = row["result"].split()
            count = int(paths)
            value = float(slack)
            if count < 0 or not math.isfinite(value):
                raise ValueError(f"Invalid TimeQuest analysis: {key}")
            if analysis not in {"recovery", "removal"} and count == 0:
                raise ValueError(f"Missing timed paths: {key}")
            if analysis.startswith("dac_") and count != 25:
                raise ValueError(f"Missing DAC endpoints: {key}")
            if analysis.startswith("sync_") and count != 2:
                raise ValueError(f"Missing monitor sync endpoints: {key}")
            checks[key] = {"paths_reported": count, "slack_ns": value if count else None}
            if count and value < 0:
                violations.append(f"{key}: {value} ns")
    if checks.keys() != expected:
        raise ValueError("Incomplete timing corners or analyses")
    return checks, violations


def vga_evidence(directory: Path, *, write_summary=True) -> tuple[list, list[str]]:
    from vga_timing import TimingViolation
    try:
        return summarize(directory, write_summary=write_summary), []
    except TimingViolation as error:
        return [], [str(error)]
