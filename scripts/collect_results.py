#!/usr/bin/env python3
"""
collect_results.py — Run verification tests and collect synthesis/verification
results for the RV32IM thesis. Generates LaTeX tables and Markdown reports.

Usage:
  python3 scripts/collect_results.py              # report from existing data
  python3 scripts/collect_results.py --run-tests  # run tests first, then report
  python3 scripts/collect_results.py --latex      # generate LaTeX tables only
  python3 scripts/collect_results.py --markdown   # generate Markdown report only
  python3 scripts/collect_results.py --all        # run tests + both outputs
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
RESULTS_DIR = REPO_ROOT / "results"
SYNTH_DIR = REPO_ROOT / "synthesis"
VERIF_DIR = REPO_ROOT / "verification" / "cocotb"

ARCHITECTURES = ["single_cycle", "pipeline"]

# Test suites per architecture
TEST_SUITES = {
    "single_cycle": {
        "common": [
            "test_rv32i",      # 37 RV32I ISA tests
            "test_rv32m",      # 8 M-extension tests
            "test_rv32mi",     # 15 machine-mode tests
            "test_alu_rv32i",  # ALU unit tests
            "test_branch",     # Branch unit tests
            "test_model_vs_dut", # Reference model comparison
        ],
        "arch": [
            "test_cpi_one",    # CPI=1 architectural invariant
        ],
    },
    "pipeline": {
        "arch": [
            "test_pipeline_smoke",    # 4 smoke tests
            "test_pipeline_debug",    # Debug/forwarding
            "test_pipeline_rv32i",    # 37 RV32I ISA tests
            "test_pipeline_rv32m",    # 8 M-extension tests
            "test_pipeline_rv32mi",   # 15 machine-mode tests
            "test_pipeline_hazards",  # 7 hazard/forwarding tests
            "test_pipeline_control",  # 5 control hazard tests
            "test_pipeline_cpi",      # 4 CPI performance tests
        ],
    },
}

# Pretty names for LaTeX
TEST_SUITE_NAMES = {
    "test_rv32i":            "RV32I ISA (37 tests)",
    "test_rv32m":            "RV32M M-Extension (8 tests)",
    "test_rv32mi":           "RV32MI Machine-Mode (15 tests)",
    "test_alu_rv32i":        "ALU Unit Tests",
    "test_branch":           "Branch Unit Tests",
    "test_model_vs_dut":     "Model vs DUT Comparison",
    "test_cpi_one":          "CPI=1 Invariant (45 tests)",
    "test_pipeline_smoke":   "Pipeline Smoke Tests (4 tests)",
    "test_pipeline_debug":   "Pipeline Debug/Forwarding",
    "test_pipeline_rv32i":   "Pipeline RV32I ISA (37 tests)",
    "test_pipeline_rv32m":   "Pipeline RV32M (8 tests)",
    "test_pipeline_rv32mi":  "Pipeline RV32MI (15 tests)",
    "test_pipeline_hazards": "Pipeline Hazard/Forwarding (7 tests)",
    "test_pipeline_control": "Pipeline Control Hazards (5 tests)",
    "test_pipeline_cpi":     "Pipeline CPI Counters (4 tests)",
}



@dataclass
class TestResult:
    """Results from a single test case in results.xml"""
    name: str
    suite: str
    status: str  # "passed", "failed", "skipped", "error"
    time: float = 0.0
    sim_time_ns: float = 0.0
    error_type: str = ""
    error_msg: str = ""


@dataclass
class SuiteSummary:
    """Aggregated results for one test suite"""
    name: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    total: int = 0
    total_time: float = 0.0
    tests: List[TestResult] = field(default_factory=list)


@dataclass
class ReplicaStats:
    """Fmax statistics across synthesis replicas (n=5)."""
    fmax_values: List[float] = field(default_factory=list)
    mean: float = 0.0
    stddev: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    count: int = 0


@dataclass
class SynthesisMetrics:
    """Synthesis resource usage and timing"""
    fmax_85c: float = 0.0        # MHz, Slow 85C model
    fmax_0c: float = 0.0          # MHz, Slow 0C model
    alms: int = 0                  # Adaptive Logic Modules
    registers: int = 0
    dsp_blocks: int = 0
    memory_bits: int = 0
    pins: int = 0
    setup_slack: float = 0.0       # ns
    hold_slack: float = 0.0        # ns
    total_power: float = 0.0       # mW (if available)
    replicas: Optional[ReplicaStats] = None  # replica Fmax statistics


@dataclass
class ArchitectureResults:
    """All results for one architecture"""
    name: str
    suites: Dict[str, SuiteSummary] = field(default_factory=dict)
    synthesis: Optional[SynthesisMetrics] = None



def parse_results_xml(xml_path: Path) -> Dict[str, SuiteSummary]:
    """Parse a cocotb results.xml file and return per-suite summaries."""
    if not xml_path.exists():
        return {}

    tree = ET.parse(xml_path)
    root = tree.getroot()

    suites: Dict[str, SuiteSummary] = {}

    for suite_elem in root.findall(".//testsuite"):
        # We only have one testsuite in cocotb output
        pass

    for testcase in root.findall(".//testcase"):
        name = testcase.get("classname", "unknown")
        test_name = testcase.get("name", "unknown")
        time = float(testcase.get("time", "0"))
        sim_time = float(testcase.get("sim_time_ns", "0"))

        if name not in suites:
            suites[name] = SuiteSummary(name=name)

        failure = testcase.find("failure")
        error = testcase.find("error")
        skipped = testcase.find("skipped")

        if skipped is not None:
            status = "skipped"
        elif failure is not None:
            status = "failed"
        elif error is not None:
            status = "error"
        else:
            status = "passed"

        result = TestResult(
            name=test_name,
            suite=name,
            status=status,
            time=time,
            sim_time_ns=sim_time,
            error_type=failure.get("error_type", "") if failure is not None else "",
            error_msg=failure.get("error_msg", "") if failure is not None else "",
        )

        s = suites[name]
        s.tests.append(result)
        s.total += 1
        s.total_time += time

        if status == "passed":
            s.passed += 1
        elif status == "failed":
            s.failed += 1
        elif status == "error":
            s.errors += 1
        elif status == "skipped":
            s.skipped += 1

    return suites



def parse_fmax_from_sta(sta_path: Path) -> Tuple[float, float]:
    """Extract Fmax (MHz) from a Quartus .sta.rpt file.
    Returns (fmax_85c, fmax_0c). Returns 0.0 for missing data.
    """
    if not sta_path.exists():
        return 0.0, 0.0

    text = sta_path.read_text()
    fmax_85c = 0.0
    fmax_0c = 0.0

    # Pattern matches the Fmax table row:
    #   ; 389.86 MHz ; 389.86 MHz      ; clk        ;      ;
    pattern = r';\s*([\d.]+)\s*MHz\s*;\s*([\d.]+)\s*MHz\s*;\s*clk\s*;'

    # Split on the boxed section header (the one starting with ";")
    sections = text.split("; Slow 1100mV 85C Model Fmax Summary")
    if len(sections) > 1:
        match = re.search(pattern, sections[1])
        if match:
            fmax_85c = float(match.group(1))

    sections = text.split("; Slow 1100mV 0C Model Fmax Summary")
    if len(sections) > 1:
        match = re.search(pattern, sections[1])
        if match:
            fmax_0c = float(match.group(1))

    return fmax_85c, fmax_0c


def parse_slack_from_sta(sta_path: Path) -> Tuple[float, float]:
    """Extract setup and hold slack (ns) from .sta.rpt."""
    if not sta_path.exists():
        return 0.0, 0.0

    text = sta_path.read_text()
    setup_slack = 0.0
    hold_slack = 0.0

    # Setup slack
    setup_match = re.search(
        r'Slow 1100mV 85C Model Setup Summary.*?clk\s*;\s*([-\d.]+)\s*;\s*([-\d.]+)',
        text, re.DOTALL
    )
    if setup_match:
        setup_slack = float(setup_match.group(1))

    # Hold slack
    hold_match = re.search(
        r'Slow 1100mV 85C Model Hold Summary.*?clk\s*;\s*([-\d.]+)\s*;',
        text, re.DOTALL
    )
    if hold_match:
        hold_slack = float(hold_match.group(1))

    return setup_slack, hold_slack


def parse_fit_summary(fit_path: Path) -> Dict[str, int]:
    """Extract resource usage from .fit.summary."""
    metrics = {
        "alms": 0,
        "registers": 0,
        "dsp_blocks": 0,
        "memory_bits": 0,
        "pins": 0,
    }

    if not fit_path.exists():
        return metrics

    patterns = {
        "alms": r"Logic utilization.*?:\s*([\d,]+)\s*/\s*[\d,]+\s*\(.*?\)",
        "registers": r"Total registers\s*:\s*([\d,]+)",
        "dsp_blocks": r"Total DSP Blocks\s*:\s*([\d,]+)\s*/\s*[\d,]+\s*",
        "memory_bits": r"Total block memory bits\s*:\s*([\d,]+)\s*/\s*[\d,]+\s*",
        "pins": r"Total pins\s*:\s*([\d,]+)\s*/\s*[\d,]+\s*",
    }

    text = fit_path.read_text()
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            metrics[key] = int(match.group(1).replace(",", ""))

    return metrics


def parse_replica_fmax(arch: str) -> ReplicaStats:
    """Scan results/<arch>/replica_*/fmax.txt and compute statistics.

    Returns ReplicaStats with all individual Fmax values and statistics.
    If no replicas found, returns an empty ReplicaStats (count=0).
    """
    stats = ReplicaStats()
    replica_dir = RESULTS_DIR / arch

    if not replica_dir.exists():
        return stats

    for d in sorted(replica_dir.glob("replica_*")):
        fmax_file = d / "fmax.txt"
        if fmax_file.exists():
            try:
                val = float(fmax_file.read_text().strip())
                stats.fmax_values.append(val)
            except (ValueError, OSError):
                continue

    stats.count = len(stats.fmax_values)
    if stats.count > 0:
        vals = stats.fmax_values
        stats.mean = sum(vals) / stats.count
        stats.minimum = min(vals)
        stats.maximum = max(vals)
        if stats.count > 1:
            variance = sum((x - stats.mean) ** 2 for x in vals) / stats.count
            stats.stddev = variance ** 0.5

    return stats


def get_synthesis_metrics(arch: str) -> SynthesisMetrics:
    """Collect all synthesis metrics for a given architecture."""
    synth_dir = SYNTH_DIR / arch / "output_files"
    project = f"rv32im_{arch}"

    sta_path = synth_dir / f"{project}.sta.rpt"
    fit_path = synth_dir / f"{project}.fit.summary"

    metrics = SynthesisMetrics()

    if sta_path.exists():
        fmax_85c, fmax_0c = parse_fmax_from_sta(sta_path)
        metrics.fmax_85c = fmax_85c
        metrics.fmax_0c = fmax_0c
        setup_slack, hold_slack = parse_slack_from_sta(sta_path)
        metrics.setup_slack = setup_slack
        metrics.hold_slack = hold_slack

    if fit_path.exists():
        resources = parse_fit_summary(fit_path)
        metrics.alms = resources["alms"]
        metrics.registers = resources["registers"]
        metrics.dsp_blocks = resources["dsp_blocks"]
        metrics.memory_bits = resources["memory_bits"]
        metrics.pins = resources["pins"]

    # Parse replica Fmax statistics
    metrics.replicas = parse_replica_fmax(arch)

    return metrics



def run_make_target(target: str, arch: str, cwd: Optional[Path] = None) -> bool:
    """Run a make target. Returns True on success."""
    if cwd is None:
        cwd = REPO_ROOT

    env = os.environ.copy()
    env["ARCH"] = arch

    cmd = ["make", target]
    print(f"  Running: {' '.join(cmd)} (ARCH={arch})")

    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min timeout per suite
    )

    if result.returncode != 0:
        print(f"  WARNING: make returned {result.returncode}")
        print(f"  stderr: {result.stderr[-500:]}")
        return False
    return True


def run_all_tests(timeout_per_suite: int = 600) -> bool:
    """Run all verification test suites for both architectures."""
    print("=" * 60)
    print("Running all verification tests...")
    print("=" * 60)

    all_ok = True

    # Common tests for single-cycle
    print(f"\n{'─' * 60}")
    print("Phase 1: Single-cycle common tests")
    print(f"{'─' * 60}")
    ok = run_make_target("verify-common", "single_cycle")
    if not ok:
        print("  FAILED: single-cycle common tests")
        all_ok = False

    # Single-cycle arch-specific tests
    print(f"\n{'─' * 60}")
    print("Phase 2: Single-cycle arch-specific tests")
    print(f"{'─' * 60}")
    ok = run_make_target("verify", "single_cycle")
    if not ok:
        print("  FAILED: single-cycle arch-specific tests")
        all_ok = False

    # Pipeline arch-specific tests (includes common via its own Makefile)
    print(f"\n{'─' * 60}")
    print("Phase 3: Pipeline tests")
    print(f"{'─' * 60}")
    ok = run_make_target("verify", "pipeline")
    if not ok:
        print("  FAILED: pipeline tests")
        all_ok = False

    # Pipeline common tests
    print(f"\n{'─' * 60}")
    print("Phase 4: Pipeline common tests")
    print(f"{'─' * 60}")
    ok = run_make_target("verify-common", "pipeline")
    if not ok:
        print("  FAILED: pipeline common tests")
        all_ok = False

    print(f"\n{'─' * 60}")
    print(f"All tests {'PASSED' if all_ok else 'had SOME FAILURES'}")
    print(f"{'─' * 60}")
    return all_ok



def collect_verification_results(arch: str) -> Dict[str, SuiteSummary]:
    """Collect verification results from results.xml files.

    For single_cycle: reads common/ results (ISA tests, ALU, branch, model)
    and arch/ results (CPI=1 invariant).

    For pipeline: reads only arch/ results (which include adapted ISA tests,
    smoke, debug, hazards, control, CPI). The common/ results are generated
    with single_cycle as TOPLEVEL and do not apply to pipeline.
    """
    suites = {}

    if arch == "single_cycle":
        # Common tests: ISA, ALU, branch, model-vs-dut — run with top_single_cycle
        common_xml = VERIF_DIR / "common" / "results.xml"
        common_suites = parse_results_xml(common_xml)
        suites.update(common_suites)

    # Arch-specific tests (CPI for single_cycle; all pipeline tests)
    arch_xml = VERIF_DIR / arch / "results.xml"
    arch_suites = parse_results_xml(arch_xml)
    suites.update(arch_suites)

    return suites


def collect_all_results() -> Dict[str, ArchitectureResults]:
    """Collect all results for both architectures."""
    all_results: Dict[str, ArchitectureResults] = {}

    for arch in ARCHITECTURES:
        print(f"Collecting results for {arch}...")
        arch_results = ArchitectureResults(name=arch)

        # Verification
        suites = collect_verification_results(arch)
        arch_results.suites = suites

        # Synthesis
        arch_results.synthesis = get_synthesis_metrics(arch)

        all_results[arch] = arch_results

    return all_results



def escape_latex(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def generate_latex_verification_table(
    all_results: Dict[str, ArchitectureResults]
) -> str:
    """Generate a LaTeX table with verification results."""
    lines = []
    lines.append(r"% Automatically generated by collect_results.py")
    lines.append(r"% Date: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"\centering")
    lines.append(r"\caption{Verification Results Summary}")
    lines.append(r"\label{tab:verification}")
    lines.append(r"\begin{tabular}{lrrrrrr}")
    lines.append(r"\toprule")
    lines.append(r"Test Suite & \multicolumn{3}{c}{Single-Cycle} & \multicolumn{3}{c}{Pipeline} \\")
    lines.append(r"\cmidrule(lr){2-4} \cmidrule(lr){5-7}")
    lines.append(r"& Passed & Failed & Total & Passed & Failed & Total \\")
    lines.append(r"\midrule")

    # Determine all suite names across both architectures
    all_suite_names = set()
    for arch_results in all_results.values():
        all_suite_names.update(arch_results.suites.keys())

    # Order: common tests first, then arch-specific
    common_suites = [
        "test_rv32i", "test_rv32m", "test_rv32mi",
        "test_alu_rv32i", "test_branch", "test_model_vs_dut",
    ]
    arch_suites_sc = ["test_cpi_one"]
    arch_suites_pipe = [
        "test_pipeline_smoke", "test_pipeline_debug",
        "test_pipeline_rv32i", "test_pipeline_rv32m", "test_pipeline_rv32mi",
        "test_pipeline_hazards", "test_pipeline_control", "test_pipeline_cpi",
    ]

    ordered = common_suites + arch_suites_sc + arch_suites_pipe

    for suite_name in ordered:
        if suite_name not in all_suite_names:
            continue

        pretty = TEST_SUITE_NAMES.get(suite_name, suite_name)

        # Single-cycle data
        sc = all_results.get("single_cycle", ArchitectureResults(name=""))
        sc_suite = sc.suites.get(suite_name)
        if sc_suite and sc_suite.total > 0:
            sc_pass = sc_suite.passed
            sc_fail = sc_suite.failed + sc_suite.errors
            sc_total = sc_suite.total
        else:
            sc_pass_str = r"\textemdash"
            sc_fail_str = r"\textemdash"
            sc_total_str = r"\textemdash"

        if sc_suite and sc_suite.total > 0:
            sc_pass_str = str(sc_pass)
            sc_fail_str = str(sc_fail)
            sc_total_str = str(sc_total)

        # Pipeline data
        pipe = all_results.get("pipeline", ArchitectureResults(name=""))
        pipe_suite = pipe.suites.get(suite_name)
        if pipe_suite and pipe_suite.total > 0:
            pipe_pass_str = str(pipe_suite.passed)
            pipe_fail_str = str(pipe_suite.failed + pipe_suite.errors)
            pipe_total_str = str(pipe_suite.total)
        else:
            pipe_pass_str = r"\textemdash"
            pipe_fail_str = r"\textemdash"
            pipe_total_str = r"\textemdash"

        # Color failures red
        sc_fail_display = sc_fail_str
        if sc_suite and sc_fail > 0:
            sc_fail_display = r"\textcolor{red}{" + str(sc_fail) + r"}"

        pipe_fail_display = pipe_fail_str
        if pipe_suite and (pipe_suite.failed + pipe_suite.errors) > 0:
            pipe_fail_display = r"\textcolor{red}{" + str(pipe_suite.failed + pipe_suite.errors) + r"}"

        lines.append(
            f"{escape_latex(pretty)} & "
            f"{sc_pass_str} & {sc_fail_display} & {sc_total_str} & "
            f"{pipe_pass_str} & {pipe_fail_display} & {pipe_total_str} \\\\"
        )

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def generate_latex_synthesis_table(
    all_results: Dict[str, ArchitectureResults]
) -> str:
    """Generate LaTeX table with synthesis results including replica statistics."""
    lines = []
    lines.append(r"% Automatically generated by collect_results.py")
    lines.append(r"% Date: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"\centering")
    lines.append(r"\caption{Synthesis Results Comparison}")
    lines.append(r"\label{tab:synthesis}")
    lines.append(r"\begin{tabular}{lrr}")
    lines.append(r"\toprule")
    lines.append(r"Metric & Single-Cycle & Pipeline \\")
    lines.append(r"\midrule")

    sc = all_results.get("single_cycle", ArchitectureResults(name=""))
    pipe = all_results.get("pipeline", ArchitectureResults(name=""))

    # Helper to format a cell with mean ± stddev
    def _fmt_replica(r: Optional[ReplicaStats]) -> str:
        if r is None or r.count == 0:
            return r"\textemdash"
        if r.count == 1:
            return f"{r.mean:.2f}"
        return f"{r.mean:.2f} $\\pm$ {r.stddev:.2f}"

    # Fmax rows with replica statistics
    sc_r = sc.synthesis.replicas if sc.synthesis else None
    pipe_r = pipe.synthesis.replicas if pipe.synthesis else None

    # Fmax @85°C from replicas (mean ± σ, n)
    sc_fmax = _fmt_replica(sc_r)
    pipe_fmax = _fmt_replica(pipe_r)
    sc_n = sc_r.count if sc_r else 0
    pipe_n = pipe_r.count if pipe_r else 0
    lines.append(r"\textbf{Fmax @85$^\circ$C (MHz)} \\")
    lines.append(r"\quad Mean $\pm$ SD & " + f"{sc_fmax} & {pipe_fmax} \\\\")
    lines.append(r"\quad Replicas (n) & " + f"{sc_n} & {pipe_n} \\\\")
    if sc_r and sc_r.count > 0:
        lines.append(r"\quad Min & " + f"{sc_r.minimum:.2f} & {pipe_r.minimum:.2f} \\\\" if pipe_r and pipe_r.count > 0 else
                     r"\quad Min & " + f"{sc_r.minimum:.2f} & {r'\textemdash'} \\\\")
    if sc_r and sc_r.count > 0 and pipe_r and pipe_r.count > 0:
        lines.append(r"\quad Max & " + f"{sc_r.maximum:.2f} & {pipe_r.maximum:.2f} \\\\")

    # Individual replica values (compact, as a comma-separated list)
    if sc_r and sc_r.count > 0:
        sc_vals = ", ".join(f"{v:.2f}" for v in sc_r.fmax_values)
        pipe_vals = ", ".join(f"{v:.2f}" for v in pipe_r.fmax_values) if pipe_r else ""
        lines.append(r"\quad Per replica & " + f"{sc_vals} & {pipe_vals} \\\\")

    lines.append(r"\midrule")

    # Other synthesis metrics (from the primary build, not replicas)
    metrics = [
        (r"Fmax @0$^\circ$C (MHz)", "fmax_0c", "{:.2f}"),
        ("Setup Slack (ns)", "setup_slack", "{:.3f}"),
        ("Hold Slack (ns)", "hold_slack", "{:.3f}"),
        ("ALMs", "alms", "{}"),
        ("Registers", "registers", "{}"),
        ("DSP Blocks", "dsp_blocks", "{}"),
        ("Memory Bits", "memory_bits", "{}"),
        ("Pins", "pins", "{}"),
    ]

    for label, attr, fmt in metrics:
        sc_val = fmt.format(getattr(sc.synthesis, attr, 0)) if sc.synthesis else r"\textemdash"
        pipe_val = fmt.format(getattr(pipe.synthesis, attr, 0)) if pipe.synthesis else r"\textemdash"
        lines.append(f"{label} & {sc_val} & {pipe_val} \\\\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def generate_latex_hazard_table(
    all_results: Dict[str, ArchitectureResults]
) -> str:
    """Generate LaTeX table with detailed pipeline hazard test results."""
    pipe = all_results.get("pipeline", ArchitectureResults(name=""))

    # Find hazard/forwarding test suites
    hazard_suite = pipe.suites.get("test_pipeline_hazards")
    control_suite = pipe.suites.get("test_pipeline_control")
    cpi_suite = pipe.suites.get("test_pipeline_cpi")

    lines = []
    lines.append(r"% Automatically generated by collect_results.py")
    lines.append(r"% Date: " + datetime.now().strftime("%Y-%m-%d %H:%M"))

    if hazard_suite and hazard_suite.tests:
        lines.append(r"\begin{table}[htbp]")
        lines.append(r"\centering")
        lines.append(r"\caption{Pipeline Hazard and Forwarding Test Results}")
        lines.append(r"\label{tab:hazards}")
        lines.append(r"\begin{tabular}{ll}")
        lines.append(r"\toprule")
        lines.append(r"Test & Result \\")
        lines.append(r"\midrule")

        for t in hazard_suite.tests:
            if t.status == "passed":
                result_str = r"\textcolor{green!60!black}{PASS}"
            else:
                result_str = r"\textcolor{red}{FAIL}"
            name_pretty = t.name.replace("test_", "").replace("_", r"\_")
            lines.append(f"{name_pretty} & {result_str} \\\\")

        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\end{table}")

    if control_suite and control_suite.tests:
        lines.append(r"\begin{table}[htbp]")
        lines.append(r"\centering")
        lines.append(r"\caption{Pipeline Control Hazard Test Results}")
        lines.append(r"\label{tab:control}")
        lines.append(r"\begin{tabular}{ll}")
        lines.append(r"\toprule")
        lines.append(r"Test & Result \\")
        lines.append(r"\midrule")

        for t in control_suite.tests:
            if t.status == "passed":
                result_str = r"\textcolor{green!60!black}{PASS}"
            else:
                result_str = r"\textcolor{red}{FAIL}"
            name_pretty = t.name.replace("test_", "").replace("_", r"\_")
            lines.append(f"{name_pretty} & {result_str} \\\\")

        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\end{table}")

    if cpi_suite and cpi_suite.tests:
        lines.append(r"\begin{table}[htbp]")
        lines.append(r"\centering")
        lines.append(r"\caption{Pipeline Performance Counter Test Results}")
        lines.append(r"\label{tab:cpi}")
        lines.append(r"\begin{tabular}{ll}")
        lines.append(r"\toprule")
        lines.append(r"Test & Result \\")
        lines.append(r"\midrule")

        for t in cpi_suite.tests:
            if t.status == "passed":
                result_str = r"\textcolor{green!60!black}{PASS}"
            else:
                result_str = r"\textcolor{red}{FAIL}"
            name_pretty = t.name.replace("test_", "").replace("_", r"\_")
            lines.append(f"{name_pretty} & {result_str} \\\\")

        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\end{table}")

    return "\n".join(lines)


def generate_latex_report(all_results: Dict[str, ArchitectureResults]) -> str:
    """Generate a complete LaTeX report with all tables."""
    sections = []
    sections.append(r"% ============================================================")
    sections.append(r"% RV32IM FPGA Verification and Synthesis Results")
    sections.append(r"% Automatically generated by scripts/collect_results.py")
    sections.append(r"% Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    sections.append(r"% ============================================================")
    sections.append(r"% Required LaTeX packages:")
    sections.append(r"%   \usepackage{booktabs}    % \toprule, \midrule, \bottomrule")
    sections.append(r"%   \usepackage{xcolor}      % \textcolor for PASS/FAIL coloring")
    sections.append(r"%   \usepackage[table]{xcolor} % for row/column coloring")
    sections.append(r"% ============================================================")
    sections.append("")

    sections.append(generate_latex_verification_table(all_results))
    sections.append("")
    sections.append(generate_latex_synthesis_table(all_results))
    sections.append("")
    sections.append(generate_latex_hazard_table(all_results))

    return "\n".join(sections)



def generate_markdown_report(all_results: Dict[str, ArchitectureResults]) -> str:
    """Generate a human-readable Markdown summary report."""
    lines = []
    lines.append("# RV32IM FPGA — Results Report")
    lines.append("")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Verification Summary ──
    lines.append("## Verification Results")
    lines.append("")
    lines.append("| Test Suite | Single-Cycle (P/F/T) | Pipeline (P/F/T) |")
    lines.append("|---|---|---|")

    all_suite_names = set()
    for arch_results in all_results.values():
        all_suite_names.update(arch_results.suites.keys())

    ordered = [
        "test_rv32i", "test_rv32m", "test_rv32mi",
        "test_alu_rv32i", "test_branch", "test_model_vs_dut",
        "test_cpi_one",
        "test_pipeline_smoke", "test_pipeline_debug",
        "test_pipeline_rv32i", "test_pipeline_rv32m", "test_pipeline_rv32mi",
        "test_pipeline_hazards", "test_pipeline_control", "test_pipeline_cpi",
    ]

    for suite_name in ordered:
        if suite_name not in all_suite_names:
            continue

        pretty = TEST_SUITE_NAMES.get(suite_name, suite_name)

        sc_suite = all_results["single_cycle"].suites.get(suite_name)
        pipe_suite = all_results["pipeline"].suites.get(suite_name)

        if sc_suite and sc_suite.total > 0:
            sc_str = f"{sc_suite.passed}/{sc_suite.failed+sc_suite.errors}/{sc_suite.total}"
        else:
            sc_str = "—"

        if pipe_suite and pipe_suite.total > 0:
            pipe_str = f"{pipe_suite.passed}/{pipe_suite.failed+pipe_suite.errors}/{pipe_suite.total}"
        else:
            pipe_str = "—"

        # Color indicators
        sc_indicator = "✅" if (sc_suite and sc_suite.failed == 0 and sc_suite.errors == 0 and sc_suite.total > 0) else "❌" if (sc_suite and sc_suite.total > 0) else "⬜"
        pipe_indicator = "✅" if (pipe_suite and pipe_suite.failed == 0 and pipe_suite.errors == 0 and pipe_suite.total > 0) else "❌" if (pipe_suite and pipe_suite.total > 0) else "⬜"

        lines.append(f"| {pretty} | {sc_indicator} {sc_str} | {pipe_indicator} {pipe_str} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Synthesis Summary ──
    lines.append("## Synthesis Results")
    lines.append("")
    lines.append("| Metric | Single-Cycle | Pipeline |")
    lines.append("|---|---|---|")

    sc_synth = all_results["single_cycle"].synthesis
    pipe_synth = all_results["pipeline"].synthesis

    synth_metrics = [
        ("Fmax @85°C", "fmax_85c", "{:.2f} MHz"),
        ("Fmax @0°C", "fmax_0c", "{:.2f} MHz"),
        ("ALMs", "alms", "{}"),
        ("Registers", "registers", "{}"),
        ("DSP Blocks", "dsp_blocks", "{}"),
        ("Memory Bits", "memory_bits", "{}"),
        ("Pins", "pins", "{}"),
        ("Setup Slack (85°C)", "setup_slack", "{:.3f} ns"),
        ("Hold Slack (85°C)", "hold_slack", "{:.3f} ns"),
    ]

    for label, attr, fmt in synth_metrics:
        sc_val = fmt.format(getattr(sc_synth, attr, "—")) if sc_synth else "—"
        pipe_val = fmt.format(getattr(pipe_synth, attr, "—")) if pipe_synth else "—"
        lines.append(f"| {label} | {sc_val} | {pipe_val} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Replica Fmax Statistics ──
    lines.append("## Replica Fmax Statistics")
    lines.append("")
    lines.append("| Replica | Single-Cycle (MHz) | Pipeline (MHz) |")
    lines.append("|---|---|---|")

    # Collect replica values per architecture
    sc_r = sc_synth.replicas if sc_synth else None
    pipe_r = pipe_synth.replicas if pipe_synth else None
    max_replicas = max(
        (sc_r.count if sc_r else 0),
        (pipe_r.count if pipe_r else 0),
    )

    for i in range(max_replicas):
        sc_val = f"{sc_r.fmax_values[i]:.2f}" if sc_r and i < sc_r.count else "—"
        pipe_val = f"{pipe_r.fmax_values[i]:.2f}" if pipe_r and i < pipe_r.count else "—"
        lines.append(f"| Replica {i+1} | {sc_val} | {pipe_val} |")

    # Summary row: mean ± stddev
    sc_mean = f"{sc_r.mean:.2f} ± {sc_r.stddev:.2f}" if sc_r and sc_r.count > 1 else (
        f"{sc_r.mean:.2f}" if sc_r and sc_r.count == 1 else "—"
    )
    pipe_mean = f"{pipe_r.mean:.2f} ± {pipe_r.stddev:.2f}" if pipe_r and pipe_r.count > 1 else (
        f"{pipe_r.mean:.2f}" if pipe_r and pipe_r.count == 1 else "—"
    )
    lines.append(f"| **Mean ± σ** | **{sc_mean}** | **{pipe_mean}** |")

    # Min/Max rows
    sc_min = f"{sc_r.minimum:.2f}" if sc_r and sc_r.count > 0 else "—"
    sc_max = f"{sc_r.maximum:.2f}" if sc_r and sc_r.count > 0 else "—"
    pipe_min = f"{pipe_r.minimum:.2f}" if pipe_r and pipe_r.count > 0 else "—"
    pipe_max = f"{pipe_r.maximum:.2f}" if pipe_r and pipe_r.count > 0 else "—"
    lines.append(f"| Min | {sc_min} | {pipe_min} |")
    lines.append(f"| Max | {sc_max} | {pipe_max} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Detailed Pipeline Test Results ──
    pipe = all_results["pipeline"]
    hazard_suite = pipe.suites.get("test_pipeline_hazards")
    control_suite = pipe.suites.get("test_pipeline_control")
    cpi_suite = pipe.suites.get("test_pipeline_cpi")

    if hazard_suite and hazard_suite.tests:
        lines.append("## Pipeline Hazard/Forwarding Tests")
        lines.append("")
        lines.append("| Test | Status | Time (s) |")
        lines.append("|---|---|---|")
        for t in hazard_suite.tests:
            status_str = "✅ PASS" if t.status == "passed" else f"❌ FAIL: {t.error_msg}"
            lines.append(f"| {t.name} | {status_str} | {t.time:.4f} |")
        lines.append("")

    if control_suite and control_suite.tests:
        lines.append("## Pipeline Control Hazard Tests")
        lines.append("")
        lines.append("| Test | Status | Time (s) |")
        lines.append("|---|---|---|")
        for t in control_suite.tests:
            status_str = "✅ PASS" if t.status == "passed" else f"❌ FAIL: {t.error_msg}"
            lines.append(f"| {t.name} | {status_str} | {t.time:.4f} |")
        lines.append("")

    if cpi_suite and cpi_suite.tests:
        lines.append("## Pipeline CPI/Performance Counter Tests")
        lines.append("")
        lines.append("| Test | Status | Time (s) |")
        lines.append("|---|---|---|")
        for t in cpi_suite.tests:
            status_str = "✅ PASS" if t.status == "passed" else f"❌ FAIL: {t.error_msg}"
            lines.append(f"| {t.name} | {status_str} | {t.time:.4f} |")
        lines.append("")

    # Detailed failure info
    all_failures = []
    for arch in ARCHITECTURES:
        arch_results = all_results[arch]
        for suite_name, suite in arch_results.suites.items():
            for t in suite.tests:
                if t.status in ("failed", "error"):
                    all_failures.append((arch, suite_name, t))

    if all_failures:
        lines.append("## Detailed Failure Information")
        lines.append("")
        for arch, suite_name, t in all_failures:
            lines.append(f"- **[{arch}]** {t.suite}.{t.name}")
            lines.append(f"  - Type: {t.error_type}")
            lines.append(f"  - Message: {t.error_msg}")
            lines.append("")

    return "\n".join(lines)



def generate_csv_report(all_results: Dict[str, ArchitectureResults]) -> str:
    """Generate a CSV summary of all results."""
    lines = []
    lines.append("suite,arch,passed,failed,skipped,errors,total,total_time_s")
    for arch in ARCHITECTURES:
        arch_results = all_results[arch]
        for suite_name, suite in arch_results.suites.items():
            lines.append(
                f"{suite_name},{arch},{suite.passed},{suite.failed},"
                f"{suite.skipped},{suite.errors},{suite.total},{suite.total_time:.4f}"
            )
    return "\n".join(lines)


def generate_synth_csv(all_results: Dict[str, ArchitectureResults]) -> str:
    """Generate CSV of synthesis metrics with replica statistics."""
    lines = []
    lines.append(
        "arch,fmax_85c_mhz,fmax_0c_mhz,alms,registers,dsp_blocks,memory_bits,"
        "pins,setup_slack_ns,hold_slack_ns,"
        "replica_count,fmax_mean_mhz,fmax_stddev_mhz,fmax_min_mhz,fmax_max_mhz"
    )
    for arch in ARCHITECTURES:
        s = all_results[arch].synthesis
        if s:
            r = s.replicas
            r_count = r.count if r else 0
            r_mean = f"{r.mean:.2f}" if r and r.count > 0 else ""
            r_std = f"{r.stddev:.2f}" if r and r.count > 1 else ""
            r_min = f"{r.minimum:.2f}" if r and r.count > 0 else ""
            r_max = f"{r.maximum:.2f}" if r and r.count > 0 else ""
            lines.append(
                f"{arch},{s.fmax_85c},{s.fmax_0c},{s.alms},{s.registers},"
                f"{s.dsp_blocks},{s.memory_bits},{s.pins},{s.setup_slack},{s.hold_slack},"
                f"{r_count},{r_mean},{r_std},{r_min},{r_max}"
            )
    return "\n".join(lines)



def main():
    parser = argparse.ArgumentParser(
        description="Collect RV32IM verification and synthesis results for thesis."
    )
    parser.add_argument(
        "--run-tests", action="store_true",
        help="Run all verification tests before collecting results"
    )
    parser.add_argument(
        "--latex", action="store_true",
        help="Generate LaTeX tables only"
    )
    parser.add_argument(
        "--markdown", action="store_true",
        help="Generate Markdown report only"
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Export results as CSV"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run tests and generate all output formats"
    )
    parser.add_argument(
        "--output-dir", type=str, default=str(REPO_ROOT / "results"),
        help="Output directory for generated files (default: results/)"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine what to do
    run_tests = args.run_tests or args.all
    do_latex = args.latex or args.all or not (args.markdown or args.csv)
    do_markdown = args.markdown or args.all or not (args.latex or args.csv)
    do_csv = args.csv or args.all

    # Run tests if requested
    if run_tests:
        print("=" * 60)
        print("RV32IM Verification Results Collector")
        print("=" * 60)
        ok = run_all_tests()
        if not ok:
            print("\nWARNING: Some tests failed. Continuing with partial results.\n")

    # Collect results
    print("Collecting results from existing data...")
    all_results = collect_all_results()

    # Print summary to console
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    for arch in ARCHITECTURES:
        arch_results = all_results[arch]
        print(f"\n  {arch.upper()}:")
        for suite_name, suite in arch_results.suites.items():
            pretty = TEST_SUITE_NAMES.get(suite_name, suite_name)
            indicators = []
            if suite.passed > 0:
                indicators.append(f"\033[92m{suite.passed} passed\033[0m")
            if suite.failed > 0:
                indicators.append(f"\033[91m{suite.failed} failed\033[0m")
            if suite.errors > 0:
                indicators.append(f"\033[91m{suite.errors} errors\033[0m")
            if suite.skipped > 0:
                indicators.append(f"\033[93m{suite.skipped} skipped\033[0m")
            status = ", ".join(indicators) if indicators else "\033[90mno data\033[0m"
            print(f"    {pretty}: {status}  ({suite.total} total)")

    print("\n" + "=" * 60)
    print("SYNTHESIS SUMMARY")
    print("=" * 60)
    for arch in ARCHITECTURES:
        s = all_results[arch].synthesis
        if s and s.fmax_85c > 0:
            print(f"\n  {arch.upper()}:")
            print(f"    Fmax @85°C: {s.fmax_85c:.2f} MHz")
            print(f"    Fmax @0°C:  {s.fmax_0c:.2f} MHz")
            print(f"    ALMs: {s.alms}, Registers: {s.registers}, "
                  f"DSP: {s.dsp_blocks}, Memory: {s.memory_bits} bits")
        else:
            print(f"\n  {arch.upper()}: \033[90mno synthesis data\033[0m")

    # Generate LaTeX
    if do_latex:
        latex_path = output_dir / "results_latex.tex"
        latex_content = generate_latex_report(all_results)
        latex_path.write_text(latex_content)
        print(f"\n  LaTeX tables written to: {latex_path}")

    # Generate Markdown
    if do_markdown:
        md_path = output_dir / "results_report.md"
        md_content = generate_markdown_report(all_results)
        md_path.write_text(md_content)
        print(f"  Markdown report written to: {md_path}")

    # Generate CSV
    if do_csv:
        csv_path = output_dir / "results_verification.csv"
        csv_content = generate_csv_report(all_results)
        csv_path.write_text(csv_content)
        print(f"  CSV verification data written to: {csv_path}")

        synth_csv_path = output_dir / "results_synthesis.csv"
        synth_csv_content = generate_synth_csv(all_results)
        synth_csv_path.write_text(synth_csv_content)
        print(f"  CSV synthesis data written to: {synth_csv_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
