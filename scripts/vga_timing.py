#!/usr/bin/env python3
"""Check VGA timing and sweep hypothetical external skew and far capacitance."""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from campaign_state import _source_files, source_fingerprint

ROOT = Path(__file__).resolve().parents[1]
TCL = ROOT / 'synthesis/report_vga_sensitivity.tcl'
SCENARIOS = ('project', 'c10_c10', 'c10_c20', 'c20_c10', 'c20_c20')
SKEWS = (0.0, 0.5, 1.0, 2.0, 2.5, 3.0)
CORNERS = {('slow', '85'), ('slow', '0'), ('fast', '85'), ('fast', '0')}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_path(path, executable):
    """Convert WSL paths only when invoking a Windows Quartus binary."""
    if os.name != 'nt' and executable.lower().endswith('.exe'):
        return subprocess.check_output(['wslpath', '-w', str(path.resolve())], text=True).strip()
    return str(path.resolve())


class TimingViolation(ValueError):
    """A modeled timing constraint has negative slack."""


def summarize(directory, *, write_summary=True):
    """Reject incomplete sweeps, missing endpoints and failed nominal checks."""
    with (directory / 'sensitivity.csv').open() as source:
        rows = list(csv.DictReader(source))
    expected = {(scenario, skew, model, temperature) for scenario in SCENARIOS
                for skew in SKEWS for model, temperature in CORNERS}
    observed = set()
    for row in rows:
        key = (row['scenario'], float(row['skew_ns']), row['model'], row['temperature_c'])
        if key in observed or key not in expected:
            raise ValueError(f'Duplicate or unexpected sensitivity case: {key}')
        observed.add(key)
        if int(row['setup_paths']) != 25 or int(row['hold_paths']) != 25:
            raise ValueError(f'Expected all 25 DAC endpoints: {key}')
        for analysis in ('setup', 'hold'):
            if not math.isfinite(float(row[f'{analysis}_slack_ns'])):
                raise ValueError(f'Nonfinite timing result: {key}')
    if observed != expected:
        raise ValueError('Incomplete VGA sensitivity sweep')

    ucp = (directory / 'unconstrained.rpt').read_text()
    counts = re.findall(r'; (?:Illegal Clocks|Unconstrained [^;]+?)\s*;\s*(\d+)\s*;\s*(\d+)\s*;', ucp)
    if len(counts) != 6 or any(a != '0' or b != '0' for a, b in counts):
        raise ValueError('Unconstrained or illegal timing endpoints remain')
    log = (directory / 'analysis.log').read_text(errors='replace')
    if 'No ignored assignments to report' not in log or 'VGA_SENSITIVITY_COMPLETE' not in log:
        raise ValueError('Missing completion or ignored-constraint check')
    if re.search(r'Ignored .*capacitance|assignment is obsolete', log, re.I):
        raise ValueError('The tool ignored a requested capacitance assignment')

    with (directory / 'baseline.csv').open() as source:
        baseline = list(csv.DictReader(source))
    baseline_keys = {(model, temperature, analysis) for model, temperature in CORNERS
                     for analysis in ('setup', 'hold', 'recovery', 'removal', 'pulse_width')}
    if len(baseline) != 20 or {(r['model'], r['temperature_c'], r['analysis'])
                               for r in baseline} != baseline_keys:
        raise ValueError('Incomplete baseline timing analysis')
    for row in baseline:
        if (not math.isfinite(float(row['slack_ns']))
                or int(row['paths']) < 0
                or (row['analysis'] in ('setup', 'hold', 'pulse_width')
                    and int(row['paths']) == 0)):
            raise ValueError(f'Nominal fitted timing evidence is incomplete: {row}')
    for row in baseline:
        if int(row['paths']) and float(row['slack_ns']) < 0:
            raise TimingViolation(f'Nominal fitted timing failed: {row}')

    # Differing data loads with a fixed clock load must affect timing. Identical
    # results would indicate a silently ineffective load sweep.
    for analysis in ('setup', 'hold'):
        low = {(r['model'], r['temperature_c']): float(r[f'{analysis}_slack_ns'])
               for r in rows if r['scenario'] == 'c10_c10' and float(r['skew_ns']) == 0.5}
        high = {(r['model'], r['temperature_c']): float(r[f'{analysis}_slack_ns'])
                for r in rows if r['scenario'] == 'c20_c10' and float(r['skew_ns']) == 0.5}
        if all(abs(low[corner] - high[corner]) < 0.001 for corner in low):
            raise ValueError(f'Capacitance sweep did not change {analysis} timing')

    summary = []
    for scenario in SCENARIOS:
        selected = [r for r in rows if r['scenario'] == scenario and float(r['skew_ns']) == 0.5]
        setup = min(float(r['setup_slack_ns']) for r in selected)
        hold = min(float(r['hold_slack_ns']) for r in selected)
        passing = [skew for skew in SKEWS if all(
            min(float(r['setup_slack_ns']), float(r['hold_slack_ns'])) >= 0
            for r in rows if r['scenario'] == scenario and float(r['skew_ns']) == skew)]
        summary.append({'scenario': scenario, 'setup_at_0_5_ns': setup,
                        'hold_at_0_5_ns': hold,
                        'largest_tested_passing_skew_ns': max(passing) if passing else None,
                        'linear_zero_margin_skew_ns': round(0.5 + min(setup, hold), 3)})
    if any(min(row['setup_at_0_5_ns'], row['hold_at_0_5_ns']) < 0 for row in summary[:2]):
        raise TimingViolation('Nominal +/-0.5 ns VGA budget failed (project or 10/10 pF scenario)')
    if write_summary:
        with (directory / 'summary.csv').open('w', newline='') as output:
            writer = csv.DictWriter(output, fieldnames=summary[0])
            writer.writeheader()
            writer.writerows(summary)
        (directory / 'summary.json').write_text(json.dumps({
            'nominal_pass': True, 'cases': len(rows), 'scenarios': summary,
            'interpretation': 'Model sensitivity only; capacitance and skew are hypothetical, not measured bounds.'
        }, indent=2) + '\n')
    return summary


def check_evidence(directory, fingerprint, sof):
    """Validate archived evidence before adopting a previously fitted replica."""
    manifest = json.loads((directory / 'manifest.json').read_text())
    if (manifest['source_fingerprint'] != fingerprint or manifest['sof_sha256'] != sha256(sof)
            or manifest['nominal_pass'] is not True):
        raise ValueError('VGA evidence does not match the replica')
    required = {'sensitivity.csv', 'baseline.csv', 'summary.csv', 'summary.json',
                'analysis.log', 'clocks.rpt', 'ignored.rpt', 'unconstrained.rpt', 'board_model.txt'}
    if (not required.issubset(manifest['artifacts']) or set(manifest['analysis_sources']) !=
            {'synthesis/report_vga_sensitivity.tcl', 'scripts/vga_timing.py'}):
        raise ValueError('Incomplete VGA evidence manifest')
    for name, expected in manifest['analysis_sources'].items():
        if sha256(ROOT / name) != expected:
            raise ValueError(f'VGA analysis changed: {name}')
    for name, expected in manifest['artifacts'].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or sha256(path) != expected:
            raise ValueError(f'Altered VGA evidence: {name}')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quartus-sta', default='quartus_sta.exe')
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('Output directory must be empty; preserve previous evidence')
    projects = list(project.glob('*.qpf'))
    if len(projects) != 1:
        parser.error('Expected one fitted Quartus project')
    sof = project / 'output_files' / (projects[0].stem + '.sof')
    settings = projects + list(project.glob('*.qsf')) + [sof]
    if not all(path.is_file() for path in settings):
        parser.error('Missing fitted bitstream; compile the project first')
    inputs = _source_files() + settings[:-1] + [ROOT / 'build/imem.mem', ROOT / 'build/dmem.mem']
    if any(path.stat().st_mtime > sof.stat().st_mtime for path in inputs):
        parser.error('Fitted bitstream predates its inputs; compile the project again')
    sources = source_fingerprint()
    before = {path: sha256(path) for path in settings}
    output.mkdir(parents=True, exist_ok=True)
    command = [args.quartus_sta, '-t', tool_path(TCL, args.quartus_sta),
               tool_path(project, args.quartus_sta), tool_path(output, args.quartus_sta)]
    with (output / 'analysis.log').open('w') as log:
        subprocess.run(command, cwd=project, stdout=log, stderr=subprocess.STDOUT, check=True)
    if sources != source_fingerprint() or any(sha256(path) != value for path, value in before.items()):
        raise ValueError('Analysis changed project settings, bitstream or sources')
    summary = summarize(output)
    source_archive = output / 'sources'
    source_archive.mkdir()
    for path in (TCL, Path(__file__).resolve(), project / 'constraints.sdc'):
        shutil.copy2(path, source_archive / path.name)
    manifest = {
        'schema': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
        'source_fingerprint': sources, 'sof_sha256': before[sof], 'nominal_pass': True,
        'analysis_sources': {p.relative_to(ROOT).as_posix(): sha256(p) for p in (TCL, Path(__file__).resolve())},
        'artifacts': {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob('*'))
                      if p.is_file()},
        'scope': 'Fixed-placement what-if analysis; no PCB measurement or physical electrical sign-off',
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
