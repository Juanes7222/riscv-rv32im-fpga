"""Regression checks for preliminary reports and the final campaign gate."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_experiment as campaign


class CampaignReportModeTests(unittest.TestCase):
    def test_artifacts_are_strict_by_default(self):
        with patch.object(sys, "argv", ["run_experiment.py", "--stages", "artifacts"]):
            with patch.object(campaign, "run", return_value=0) as run:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(campaign.main(), 0)
        self.assertIn("--strict", run.call_args.args[0])

    def test_diagnostic_mode_is_explicit(self):
        with patch.object(campaign, "run", return_value=0) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                campaign.stage_artifacts(SimpleNamespace(report_mode="diagnostic"))
        self.assertNotIn("--strict", run.call_args.args[0])
        self.assertIn("--render", run.call_args.args[0])

    def test_smoke_test_cannot_overwrite_isa_results(self):
        result = subprocess.run(
            ["make", "--just-print", "--no-print-directory", "verify-coremark", "MAKE=echo"],
            cwd=campaign.REPO_ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        for arch in campaign.ARCHES:
            self.assertIn(f"COCOTB_RESULTS_FILE={campaign.REPO_ROOT}/results/coremark_smoke_{arch}.xml",
                          result.stdout)


class FullCampaignOrderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / "commands.jsonl"
        self.stub = self.directory / "command.py"
        self.stub.write_text(
            "import json, os, sys\n"
            "with open(os.environ['CAMPAIGN_TEST_LOG'], 'a') as log:\n"
            "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "if 'scripts/hardware_measure.py' in sys.argv:\n"
            "    sys.exit(int(os.environ.get('CAMPAIGN_TEST_HARDWARE_EXIT', '0')))\n"
            "if '--strict' in sys.argv:\n"
            "    sys.exit(int(os.environ.get('CAMPAIGN_TEST_STRICT_EXIT', '0')))\n")
        self.makefile = campaign.REPO_ROOT / "Makefile"
        self.override = self.directory / "override.mk"
        self.override.write_text(
            "verify-coremark:\n\t@$(VENV_PY) smoke\n")

    def run_campaign(self, **overrides):
        env = {**os.environ, "CAMPAIGN_TEST_LOG": str(self.log), **overrides}
        command = ["make", "--no-print-directory", "-f", str(self.makefile),
                   "-f", str(self.override), "full-campaign",
                   f"VENV_PY={sys.executable} {self.stub}",
                   f"MAKE=make --no-print-directory -f {self.makefile} -f {self.override}"]
        result = subprocess.run(command, cwd=self.directory, env=env,
                                capture_output=True, text=True, timeout=30)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, calls

    def test_physical_measurements_precede_strict_report(self):
        result, calls = self.run_campaign()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([call[0] for call in calls], [
            "scripts/run_experiment.py", "scripts/generate_reports.py", "smoke",
            "scripts/hardware_measure.py", "scripts/generate_reports.py",
            "scripts/generate_reports.py"])
        self.assertIn("diagnostic", calls[0])
        self.assertIn("--check", calls[1])
        self.assertIn("--strict", calls[4])
        self.assertIn("--check", calls[5])

    def test_missing_physical_evidence_still_fails_final_gate(self):
        result, calls = self.run_campaign(CAMPAIGN_TEST_STRICT_EXIT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls[3][0], "scripts/hardware_measure.py")
        self.assertIn("--strict", calls[-1])
        self.assertNotIn("passed the final checks", result.stdout)

    def test_hardware_failure_stops_before_final_publication(self):
        result, calls = self.run_campaign(CAMPAIGN_TEST_HARDWARE_EXIT="2")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls[-1][0], "scripts/hardware_measure.py")
        self.assertFalse(any("--strict" in call for call in calls))


if __name__ == "__main__":
    unittest.main()
