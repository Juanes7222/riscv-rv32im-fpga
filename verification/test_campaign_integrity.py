"""Regression checks for provenance and time-based comparisons."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from replica_manifest import sha256, verified
from thesis_artifacts import benchmark_metrics, describe


class CampaignIntegrityTests(unittest.TestCase):
    def test_legacy_metadata_is_not_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "meta.json").write_text(json.dumps({"fingerprint": "current"}))
            self.assertFalse(verified(directory, "current"))

    def test_changed_artifact_is_not_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            artifact = directory / "timing.rpt"
            artifact.write_text("original")
            artifacts = {}
            for name in ("timing.rpt", "fit.summary", "compile.log", "fmax.txt",
                         "inputs.tar.gz", "rv32im_pipeline.sof"):
                path = directory / name
                path.write_text("original")
                artifacts[name] = sha256(path)
            manifest = {"status": "complete", "fingerprint": "current",
                        "architecture": "pipeline", "artifacts": artifacts}
            (directory / "manifest.json").write_text(json.dumps(manifest))
            self.assertTrue(verified(directory, "current"))
            artifact.write_text("different run")
            self.assertFalse(verified(directory, "current"))

    def test_speedup_uses_duration_and_unrounded_counts(self):
        stats = {arch: {"fmax": describe(values)} for arch, values in
                 (("single_cycle", [40.0, 45.0]), ("pipeline", [50.0, 55.0]))}
        rows = [dict(program="same_work", architecture=arch, result="pass",
                     cycle_count=cycles, instr_retired=instructions, cpi="99")
                for arch, cycles, instructions in
                (("single_cycle", 100, 100), ("pipeline", 125, 80))]
        metric = benchmark_metrics(rows, stats)[0]
        expected = ((100 / 40) / (125 / 50) + (100 / 45) / (125 / 55)) / 2
        self.assertAlmostEqual(metric["speedup"]["mean"], expected)
        self.assertEqual(metric["arch"]["single_cycle"]["cpi"], 1)


if __name__ == "__main__":
    unittest.main()
