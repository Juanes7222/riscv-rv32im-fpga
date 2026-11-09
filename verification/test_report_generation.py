"""Report regressions: stale evidence, failed runs and publication integrity."""

import contextlib
import csv
import io
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import collect_results as collector
import generate_reports as reports
import thesis_artifacts as artifacts


class ReportGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.raw, self.verification, self.output = root / "measurements", root / "verification", root / "report"
        self.raw.mkdir()
        for module, names in ((artifacts, ("RESULTS", "INPUT_RESULTS", "TABLES", "FIGURES", "REPRO",
                                           "COREMARK_CSV", "COREMARK_INPUT_CSV", "TIMING_PATHS_TXT")),
                              (collector, ("RESULTS_DIR", "VERIF_DIR"))):
            replacement = patch.multiple(module, **{name: getattr(module, name) for name in names})
            replacement.start()
            self.addCleanup(replacement.stop)
        for name in ("common", "single_cycle", "pipeline"):
            path = self.verification / name / "results.xml"
            path.parent.mkdir(parents=True)
            path.write_text(f'<testsuites><testsuite><testcase classname="{name}_suite" name="case"/></testsuite></testsuites>')
        for arch, frequencies in (("single_cycle", (40, 42)), ("pipeline", (50, 52))):
            for index, frequency in enumerate(frequencies, 1):
                replica = self.raw / arch / f"replica_{index}"
                replica.mkdir(parents=True)
                (replica / "fmax.txt").write_text(str(frequency))
                (replica / "meta.json").write_text(json.dumps({"seed": index}))
                (replica / "fit.summary").write_text(
                    "Logic utilization (in ALMs) : 100\nTotal registers : 150\n"
                    "Total RAM Blocks : 2\nTotal DSP Blocks : 0\n"
                    "Total block memory bits : 1000\nTotal pins : 90\n")
        self.benchmarks = [dict(architecture=arch, program="tiny_work", result="pass",
                               cycle_count=cycles, instr_retired=100, cpi="99")
                           for arch, cycles in (("single_cycle", 100), ("pipeline", 125))]
        self.write_benchmarks()

    def write_benchmarks(self):
        with (self.raw / "results_benchmarks.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self.benchmarks[0]))
            writer.writeheader()
            writer.writerows(self.benchmarks)

    def generate(self, *flags):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return reports.main(["--results-dir", str(self.raw), "--verification-dir",
                                 str(self.verification), "--output-dir", str(self.output), *flags])

    def test_complete_bundle_checks_and_leaves_measurements_unchanged(self):
        before = {str(p): p.read_bytes() for p in self.raw.rglob("*") if p.is_file()}
        self.assertEqual(self.generate(), 0)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.raw.rglob("*") if p.is_file()})
        self.assertTrue((self.output / "results/results_verification.csv").is_file())
        self.assertEqual(self.generate("--check"), 0)
        self.assertIn("diagnostic", (self.output / "manifest.json").read_text())

    def test_fresh_failure_overrides_archived_success(self):
        (self.raw / "verification_pipeline.xml").write_text(
            '<testsuite><testcase classname="old_success"/></testsuite>')
        (self.verification / "pipeline/results.xml").write_text(
            '<testsuite><testcase classname="new_failure"><failure/></testcase></testsuite>')
        self.assertEqual(self.generate(), 1)
        summary = (self.output / "results/results_verification.csv").read_text()
        self.assertIn("new_failure", summary)
        self.assertNotIn("old_success", summary)

    def test_test_runner_overrides_inherited_architecture(self):
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with patch.object(collector.subprocess, "run", return_value=completed) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(collector.run_make_target("verify", "pipeline"))
        self.assertEqual(run.call_args.args[0], ["make", "verify", "ARCH=pipeline"])

    def test_zero_instruction_failure_is_reported_with_eight_columns(self):
        self.benchmarks[1].update(result="timeout", instr_retired=0)
        self.write_benchmarks()
        self.assertEqual(self.generate(), 0)
        rows = artifacts.parse_tex_rows(self.output / "thesis/tables/benchmarks.tex")
        self.assertTrue(all(len(row) == 8 for row in rows))
        self.assertEqual(self.generate("--check"), 0)

    def test_missing_resources_are_missing_bars_and_zero_dsp_is_valid(self):
        (self.raw / "pipeline/replica_1/fit.summary").unlink()
        (self.raw / "pipeline/replica_2/fit.summary").unlink()
        self.assertEqual(self.generate(), 0)
        figure = (self.output / "thesis/figures/diagrams/resources_comparison.tex").read_text()
        self.assertIn("nan", figure)
        statistics = (self.output / "results/results_statistics.csv").read_text()
        self.assertIn("dsp_blocks,2,0.000", statistics)
        self.assertEqual(self.generate("--check"), 0)

    def test_strict_rejection_preserves_previous_report(self):
        self.assertEqual(self.generate(), 0)
        before = (self.output / "report.md").read_bytes()
        self.assertEqual(self.generate("--strict"), 1)
        self.assertEqual((self.output / "report.md").read_bytes(), before)

    def test_render_failure_does_not_publish_partial_outputs(self):
        self.assertEqual(self.generate(), 0)
        before = (self.output / "manifest.json").read_bytes()
        with patch.object(reports, "standalone_figures", side_effect=RuntimeError("compiler failed")):
            self.assertEqual(self.generate(), 1)
        self.assertEqual((self.output / "manifest.json").read_bytes(), before)

    def test_changed_input_invalidates_report(self):
        self.assertEqual(self.generate(), 0)
        self.benchmarks[0]["cycle_count"] = 101
        self.write_benchmarks()
        self.assertEqual(self.generate("--check"), 1)

    def test_metrics_check_rejects_wrong_summary_even_without_plot_changes(self):
        self.assertEqual(self.generate(), 0)
        path = self.output / "results/results_benchmarks_summary.csv"
        content = path.read_text().replace("1.0000", "9.0000")
        path.write_text(content)
        self.assertTrue(artifacts.derived_metric_problems())

    def test_duplicate_benchmark_rows_are_rejected(self):
        self.benchmarks.append(dict(self.benchmarks[0]))
        self.write_benchmarks()
        self.assertEqual(self.generate(), 1)
        self.assertFalse(self.output.exists())

    def test_missing_frequency_does_not_become_zero_performance(self):
        for path in (self.raw / "pipeline").glob("replica_*/fmax.txt"):
            path.unlink()
        self.assertEqual(self.generate(), 0)
        self.assertEqual(self.generate("--check"), 0)

    def test_replica_gaps_preserve_identity(self):
        replica = self.raw / "pipeline/replica_2"
        replica.rename(replica.with_name("replica_3"))
        (replica.with_name("replica_3") / "meta.json").write_text('{"seed": 3}')
        self.assertEqual(self.generate(), 0)
        rows = artifacts.parse_tex_rows(self.output / "thesis/tables/fmax_replicas.tex")
        self.assertEqual(rows[1], ["2", "42.00", r"\textemdash"])
        self.assertEqual(rows[2], ["3", r"\textemdash", "52.00"])

    def test_optional_coremark_table_is_removed_when_its_input_is_removed(self):
        source = self.raw / "results_coremark.csv"
        source.write_text("architecture,cycles,instructions,iterations,clock_mhz\n"
                          "single_cycle,1000000,1000000,10,40\n"
                          "pipeline,1250000,1000000,10,50\n")
        self.assertEqual(self.generate(), 0)
        table = self.output / "thesis/tables/coremark.tex"
        self.assertTrue(table.exists())
        source.unlink()
        self.assertEqual(self.generate(), 0)
        self.assertFalse(table.exists())


if __name__ == "__main__":
    unittest.main()
