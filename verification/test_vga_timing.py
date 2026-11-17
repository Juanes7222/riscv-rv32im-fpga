"""Exercise rejection of incomplete, stale and silently ineffective VGA evidence."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import vga_timing as vga


class VgaEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        rows = []
        for scenario in vga.SCENARIOS:
            data_load = 20 if scenario.startswith('c20') else 10
            for skew in vga.SKEWS:
                for model, temperature in sorted(vga.CORNERS):
                    rows.append(dict(scenario=scenario, data_load_pf=data_load, clock_load_pf=10,
                                     skew_ns=skew, model=model, temperature_c=temperature,
                                     setup_paths=25, setup_slack_ns=2.5-skew-data_load*0.02,
                                     hold_paths=25, hold_slack_ns=5-skew+data_load*0.02))
        self.write_rows('sensitivity.csv', rows)
        baseline = [dict(model=model, temperature_c=temperature, analysis=analysis,
                         paths=0 if analysis in ('recovery', 'removal') else 10, slack_ns=0.2)
                    for model, temperature in vga.CORNERS
                    for analysis in ('setup', 'hold', 'recovery', 'removal', 'pulse_width')]
        self.write_rows('baseline.csv', baseline)
        properties = ('Illegal Clocks', 'Unconstrained Clocks', 'Unconstrained Input Ports',
                      'Unconstrained Input Port Paths', 'Unconstrained Output Ports',
                      'Unconstrained Output Port Paths')
        (self.output / 'unconstrained.rpt').write_text(''.join(f'; {p} ; 0 ; 0 ;\n' for p in properties))
        (self.output / 'analysis.log').write_text('No ignored assignments to report\nVGA_SENSITIVITY_COMPLETE\n')
        for name in ('clocks.rpt', 'ignored.rpt', 'board_model.txt'):
            (self.output / name).write_text('test evidence\n')

    def write_rows(self, name, rows):
        with (self.output / name).open('w', newline='') as output:
            writer = csv.DictWriter(output, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)

    def mutate(self, name, function):
        with (self.output / name).open() as source:
            rows = list(csv.DictReader(source))
        function(rows)
        self.write_rows(name, rows)

    def test_stress_failure_does_not_replace_nominal_acceptance(self):
        summary = vga.summarize(self.output)
        self.assertEqual(len(summary), 5)
        self.assertEqual(summary[0]['largest_tested_passing_skew_ns'], 2.0)

    def test_missing_corner_is_rejected(self):
        self.mutate('sensitivity.csv', lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            vga.summarize(self.output)

    def test_missing_endpoint_is_rejected(self):
        self.mutate('sensitivity.csv', lambda rows: rows[0].update(setup_paths=24))
        with self.assertRaisesRegex(ValueError, '25 DAC'):
            vga.summarize(self.output)

    def test_nominal_failure_is_rejected(self):
        self.mutate('sensitivity.csv', lambda rows: next(r for r in rows
                    if r['scenario'] == 'c10_c10' and r['skew_ns'] == '0.5').update(setup_slack_ns=-0.1))
        with self.assertRaisesRegex(ValueError, 'Nominal'):
            vga.summarize(self.output)

    def test_ineffective_capacitance_model_is_rejected(self):
        def equalize(rows):
            for row in rows:
                row['setup_slack_ns'] = 2.5 - float(row['skew_ns'])
        self.mutate('sensitivity.csv', equalize)
        with self.assertRaisesRegex(ValueError, 'did not change'):
            vga.summarize(self.output)

    def test_unconstrained_endpoint_is_rejected(self):
        (self.output / 'unconstrained.rpt').write_text('; Unconstrained Output Ports ; 1 ; 1 ;\n')
        with self.assertRaisesRegex(ValueError, 'Unconstrained'):
            vga.summarize(self.output)

    def test_nonfinite_baseline_is_rejected(self):
        self.mutate('baseline.csv', lambda rows: rows[0].update(slack_ns='nan'))
        with self.assertRaisesRegex(ValueError, 'Nominal fitted'):
            vga.summarize(self.output)

    def test_archived_report_and_analysis_hashes_are_checked(self):
        vga.summarize(self.output)
        sof = self.output / 'candidate.sof'
        sof.write_bytes(b'candidate')
        manifest = dict(source_fingerprint='test', sof_sha256=vga.sha256(sof), nominal_pass=True,
                        analysis_sources={p.relative_to(vga.ROOT).as_posix(): vga.sha256(p)
                                          for p in (vga.TCL, Path(vga.__file__))},
                        artifacts={p.name: vga.sha256(p) for p in self.output.iterdir() if p.is_file()})
        path = self.output / 'manifest.json'
        path.write_text(json.dumps(manifest))
        vga.check_evidence(self.output, 'test', sof)
        with self.assertRaisesRegex(ValueError, 'does not match'):
            vga.check_evidence(self.output, 'different-source', sof)
        (self.output / 'summary.csv').write_text('altered')
        with self.assertRaisesRegex(ValueError, 'Altered VGA evidence'):
            vga.check_evidence(self.output, 'test', sof)


if __name__ == '__main__':
    unittest.main()
