"""Exercise frequency selection, fitted clocks and fail-closed evidence."""
import csv
import shutil
import threading
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import frequency_build as build
from frequency_campaign import candidates, pending, preferred, search
from frequency_observation import (adopt_boots, boot_records, capture_boot, load_sof, observe,
                                   observe_all, paired_results, physical_state)
from coremark_hardware import check_observation, observation_inputs, save_observation
from frequency_timing import ANALYSES, CORNERS, clock_request, fitted_clock, physical_timing

ROOT = Path(__file__).resolve().parents[1]


class FrequencyCampaignTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)

    def test_grid_ratio_stays_in_bin(self):
        for mhz in range(40, 64):
            config = clock_request(mhz)
            self.assertTrue(config["realizable"])
            self.assertGreater(config["expected_mhz"], mhz - 1)
            self.assertLessEqual(config["expected_mhz"], mhz)
        with self.assertRaises(ValueError):
            clock_request(64)
        with self.assertRaises(ValueError):
            clock_request(45.5)

    def test_fitted_waveform_and_clock_binding(self):
        original = (ROOT / "results/physical_replicas/coremark/single_cycle/replica_1"
                    / "vga_timing/clocks.rpt")
        record = fitted_clock(original, clock_request(40))
        self.assertEqual(record["effective_mhz"], 40)
        self.assertEqual(record["fall_ns"], 12.5)
        with self.assertRaises(ValueError):
            fitted_clock(original, clock_request(41))

    def test_indeterminate_higher_candidate_blocks_maximum(self):
        entries = [(clock_request(mhz), self.root / str(mhz), None, {"status": status})
                   for mhz, status in [(49, "build_error"), (48, "timing_violation"),
                                       (47, "timing_pass"), (46, "pending")]]
        self.assertEqual(preferred(entries), (entries[2], False))
        self.assertEqual(list(pending(entries, set(), set())), [entries[0]])
        entries[0][3]["status"] = "timing_violation"
        self.assertEqual(preferred(entries), (entries[2], True))

    def test_resumption_refuses_tampered_timing_rejection(self):
        request = clock_request(49)
        combo = {"id": "coremark/single_cycle/s1", "requests": [request], "build_inputs": {"seed": 1}}
        target = self.root / "c" / combo["id"] / "49" / "a1"
        target.mkdir(parents=True)
        evidence = target / "summary.tsv"
        evidence.write_text("complete")
        build.save_json(target / "manifest.json", dict(status="timing_violation", request=request,
                         inputs=combo["build_inputs"], quartus_version="Q", threads=4,
                         artifacts={evidence.name: build.file_fingerprint(evidence)}))
        state = {"quartus_version": "Q", "threads": 4}
        self.assertEqual(candidates(combo, self.root, state, verify=True)[0][3]["status"], "timing_violation")
        evidence.write_text("changed")
        self.assertEqual(candidates(combo, self.root, state, verify=True)[0][3]["status"], "integrity_error")

    def test_missing_corner_is_error_and_negative_slack_is_violation(self):
        (self.root / "timequest.log").write_text(
            "No ignored assignments to report\nPHYSICAL_TIMING_REPORT_COMPLETE\n")
        (self.root / "unconstrained.rpt").write_text(
            "; Illegal Clocks ; 0 ; 0 ;\n" + "; Unconstrained paths ; 0 ; 0 ;\n" * 5)
        rows = [(f"{model}_{temp}C", name,
                 f"{25 if name.startswith('dac_') else 2 if name.startswith('sync_') else 1} "
                 f"{-.025 if (model, temp, name) == ('fast', '0', 'hold') else .5}")
                for model, temp in CORNERS for name in ANALYSES]
        for solution in (rows[:-1], rows):
            with (self.root / "summary.tsv").open("w", newline="") as stream:
                writer = csv.writer(stream, delimiter="\t")
                writer.writerow(["corner", "analysis", "result"])
                writer.writerows(solution)
            if len(solution) < len(rows):
                with self.assertRaisesRegex(ValueError, "Incomplete timing"):
                    physical_timing(self.root)
            else:
                self.assertEqual(physical_timing(self.root)[1], ["fast_0C/hold: -0.025 ns"])

    def test_physical_arrivals_are_controls_and_pilot_has_no_hypothesis_result(self):
        row = dict(result="functional_pass", exit_status=1, crc_status="0x1",
                   cycle_count=10, instr_retired=10, clock_mhz=45, elf_sha256="same")
        self.assertEqual(physical_state([row]), "one_boot")
        self.assertEqual(physical_state([row, {**row, "cycle_count": 11}]), "inconsistent_boots")
        self.assertEqual(physical_state([row, dict(row)]), "functional_pass")
        pairs, summary, support = paired_results({
            ("coremark", "single_cycle", 1): row,
            ("coremark", "pipeline", 1): dict(row, clock_mhz=60, cycle_count=12),
        }, 1e-9)
        self.assertAlmostEqual(pairs[0]["speedup"], 60 / 45 / 1.2)
        self.assertIsNone(summary["coremark"]["sample_sd"])
        self.assertIsNone(support)

    def test_parallel_scheduler_starts_both_architectures_before_lower_points(self):
        combos = []
        mhz = {"single_cycle": 49, "pipeline": 63}
        for arch, high in mhz.items():
            combo_id = f"coremark/{arch}/s1"
            snapshot = self.root / "c" / combo_id / "inputs"
            snapshot.mkdir(parents=True)
            source = snapshot / "input.txt"
            source.write_text("frozen")
            combos.append({
                "id": combo_id, "requests": [clock_request(f) for f in (high, high - 1)],
                "build_inputs": {"inputs": {source.name: build.file_fingerprint(source)}},
            })
        both_started = threading.Barrier(2)
        seen = []

        def compile_candidate(directory, combination, inputs, request, *args):
            seen.append((combination.parent.name, request["requested_mhz"]))
            if request["requested_mhz"] == mhz[combination.parent.name]:
                both_started.wait(timeout=5)
            return {"status": "timing_pass", "reason": "test timing complete"}

        args = SimpleNamespace(quartus_sh="sh", quartus_sta="sta", jobs=2, reuse_from=None)
        config = {"id": "test", "threads": 4, "combinations": combos}
        with patch("frequency_campaign.subprocess.check_output", return_value="Version test Build 1"), \
                patch.object(build, "build", side_effect=compile_candidate), \
                patch("frequency_observation.rejected_artifacts", return_value=set()):
            search(self.root, config, {}, args)
        self.assertCountEqual(seen, mhz.items())

    def test_variable_coremark_clock_requires_manifest_frequency(self):
        historic, _, original = build.reference("single_cycle", "coremark", 1)
        row = {**historic, "clock_mhz": 46}
        for path in observation_inputs(historic, build.RESULTS):
            target = self.root / path.relative_to(build.RESULTS)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        elf = observation_inputs(row, self.root)[0]
        row["crc_evidence"] = save_observation(row, elf, self.root)
        self.assertFalse(check_observation(row, self.root, original["fingerprint"])[0])
        self.assertTrue(check_observation(
            row, self.root, original["fingerprint"], expected_clock_mhz=46)[0])
        self.assertFalse(check_observation(
            row, self.root, original["fingerprint"], expected_clock_mhz=47)[0])

    def test_programmer_accepts_only_confirmed_device_configuration(self):
        args = SimpleNamespace(quartus_pgm="quartus_pgm.exe", cable="DE-SoC", device_position=2)
        attempt = self.root / "candidates" / "46"
        attempt.mkdir(parents=True)
        sof = attempt / "test.sof"
        sof.write_bytes(b"test bitstream")
        manifest = {"sof": sof.name, "artifacts": {sof.name: build.file_fingerprint(sof)}}
        output = "Info (209007): Configuration succeeded -- 1 device(s) configured\n"
        process = MagicMock()
        process.wait.return_value = 0
        process.stdout = iter(output.splitlines(keepends=True))
        with patch.object(build, "ROOT", self.root), \
                patch("frequency_observation.subprocess.Popen") as launch:
            launch.return_value.__enter__.return_value = process
            self.assertEqual(load_sof(attempt, manifest, args, attempt), sof)
            self.assertEqual(launch.call_args.args[0],
                             ["quartus_pgm.exe", "-c", "DE-SoC", "-m", "JTAG",
                              "-o", "P;candidates/46/test.sof@2"])
            self.assertEqual(launch.call_args.kwargs["cwd"], self.root)
            self.assertEqual((attempt / "program.log").read_text(), output)

            process.stdout = iter(["Info: Quartus Prime Programmer was successful.\n"])
            with self.assertRaisesRegex(ValueError, "did not confirm FPGA configuration"):
                load_sof(attempt, manifest, args, attempt)

    def test_observe_programs_before_prompting_for_readings(self):
        def decline_reset(_):
            load.assert_called_once()
            return "n"

        with patch("frequency_observation.sys.stdin", SimpleNamespace(isatty=lambda: True)), \
                patch("frequency_observation.boot_records", return_value=[]), \
                patch("frequency_observation.load_sof") as load, \
                patch("builtins.input", side_effect=decline_reset):
            with self.assertRaisesRegex(ValueError, "fresh boot"):
                observe((self.root, {}), SimpleNamespace())
        self.assertFalse(list(self.root.glob("boots/*/observation.json")))

    def test_observe_shows_halted_instruction_and_leaves_deferred_boot_unverified(self):
        attempt = self.root / "candidate"
        with patch("frequency_observation.load_sof", return_value=attempt / "test.sof"), \
                patch("builtins.input", side_effect=["y", "0"]) as readings, \
                patch("builtins.print") as output:
            with self.assertRaisesRegex(ValueError, "capture unresolved"):
                capture_boot(attempt, {}, SimpleNamespace())
        readings.assert_called_with("HALTED [1/0]: ")
        self.assertTrue(any("Enter 1 once it shows HALTED=1" in call.args[0]
                            for call in output.call_args_list))
        self.assertFalse((attempt / "boots/1/observation.json").exists())

    def test_observe_programs_all_remaining_boots_in_the_same_invocation(self):
        row = dict(result="functional_pass", exit_status=1, crc_status="0x1",
                   cycle_count=10, instr_retired=10)
        for existing_count in range(3):
            with self.subTest(existing=existing_count):
                records = [dict(row, boot=boot) for boot in range(1, 3)]
                states = [records[:count] for count in range(existing_count + 1, 3)]
                with patch("frequency_observation.sys.stdin", SimpleNamespace(isatty=lambda: True)), \
                        patch("frequency_observation.boot_records", return_value=records[:existing_count]), \
                        patch("frequency_observation.capture_boot", side_effect=states) as capture, \
                        patch("builtins.input", return_value="") as wait_for_reset:
                    observe((self.root, {}), SimpleNamespace())
                self.assertEqual(capture.call_count, 2 - existing_count)
                self.assertEqual(wait_for_reset.call_count, int(existing_count == 0))

    def test_batch_capture_skips_pending_or_already_validated_candidates(self):
        boot = dict(result="functional_pass", exit_status=1, crc_status="0x1",
                    cycle_count=10, instr_retired=10)
        already = self.root / "already"
        ready = self.root / "ready"
        manifest = {"status": "timing_pass", "clock": {"effective_mhz": 60},
                    "sof": "candidate.sof", "artifacts": {"candidate.sof": "digest"}}
        entries = [
            [(None, None, already, manifest)],
            [(None, None, None, {"status": "pending"})],
            [(None, None, ready, manifest)],
        ]
        args = SimpleNamespace()
        with patch("frequency_observation.sys.stdin", SimpleNamespace(isatty=lambda: True)), \
                patch("frequency_observation.candidates", side_effect=entries), \
                patch("frequency_observation.boot_records", side_effect=[[boot, boot], []]), \
                patch("frequency_observation.observe") as capture:
            observe_all(self.root, [{"id": name} for name in ("done", "pending", "ready")], {}, args)
        capture.assert_called_once_with((ready, manifest), args, prompt_first=True, records=[])

    def test_reused_boot_carries_original_manifest_and_unmodified_readings(self):
        source, target = self.root / "source", self.root / "target"
        directory = source / "boots" / "1"
        directory.mkdir(parents=True)
        target.mkdir()
        log = directory / "program.log"
        log.write_text("Info (209007): Configuration succeeded\n")
        baseline = dict(elf_sha256="elf", cycle_count=5, instr_retired=4)
        original = dict(campaign_id="pilot", sof="candidate.sof", artifacts={"candidate.sof": "sof"},
                        clock={"effective_mhz": 46}, inputs={
                            "architecture": "single_cycle", "program": "raw_stress",
                            "historical_reference": baseline,
                        })
        build.save_json(source / "manifest.json", original)
        origin_digest = build.file_fingerprint(source / "manifest.json")
        row = dict(baseline, architecture="single_cycle", program="raw_stress", sof_sha256="sof",
                   boot=1, candidate_sha256=origin_digest, clock_mhz=46, halted=True,
                   exit_status=1, crc_status="", result="functional_pass",
                   evidence={"program.log": build.file_fingerprint(log)})
        build.save_json(directory / "observation.json", row)
        destination = dict(original, campaign_id="seed1",
                           origin={"campaign": "pilot", "manifest_sha256": origin_digest})
        build.save_json(target / "manifest.json", destination)
        self.assertEqual(adopt_boots(source, original, target, destination), 1)
        copied = target / "boots/1/provenance/pilot/observation.json"
        self.assertEqual(copied.read_bytes(), (directory / "observation.json").read_bytes())
        self.assertEqual(boot_records(target, destination)[0]["cycle_count"], 5)
        copied.write_text("{}")
        self.assertEqual(boot_records(target, destination), [])
