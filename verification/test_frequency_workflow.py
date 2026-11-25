"""Exercise campaign coordination and academic output without Quartus or JTAG."""
import csv
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import frequency_artifacts as artifacts
import frequency_build as build
import frequency_campaign as campaign
import frequency_workflow as workflow
from frequency_observation import boot_records, metrics, paired_results
from frequency_timing import clock_request


class FrequencyWorkflowTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)
        self.args = SimpleNamespace(id="full", arch=None, program=None, seed=None, grid=None, jobs=2,
                                    threads=4, reuse_from=None, quartus_sh="mock-sh", quartus_sta="mock-sta")

    def combo(self, name):
        frozen = self.directory / "c" / name / "inputs"
        frozen.mkdir(parents=True)
        source = frozen / "source.txt"
        source.write_text("sealed")
        return dict(id=name, requests=[clock_request(49), clock_request(48)],
                    build_inputs={"inputs": {source.name: build.file_fingerprint(source)}})

    def test_full_scope_is_fixed_and_process_count_configurable(self):
        config = campaign.configuration(workflow.full_args(self.args))
        self.assertEqual(len(config["combinations"]), 50)
        self.assertEqual(sum(len(combo["requests"]) for combo in config["combinations"]), 600)
        self.assertEqual(workflow.job_count(self.args), 2)
        self.args.jobs = 0
        with patch.object(workflow, "available_cpus", return_value=12), \
                patch.object(workflow, "available_memory", return_value=7 * 1024**3):
            self.assertEqual(workflow.job_count(self.args), 1)
        self.args.seed = [2]
        with self.assertRaisesRegex(ValueError, "all five programs"):
            workflow.full_args(self.args)

    def test_read_only_plan_recognizes_ten_existing_configurations(self):
        self.args.id = "fc-reproduction-test"
        if not (build.RESULTS / "frequency_campaign/fc-seed1/campaign_manifest.json").is_file():
            self.skipTest("fc-seed1 evidence is not available in this checkout")
        with patch.object(workflow, "BASE", build.RESULTS / "frequency_campaign"), \
                patch("frequency_workflow.subprocess.run") as invoke, redirect_stdout(StringIO()) as output:
            workflow.plan(self.directory / self.args.id, self.args)
        invoke.assert_not_called()
        self.assertFalse((self.directory / self.args.id).exists())
        self.assertIn("10 reusable from fc-seed1, 40 remaining", output.getvalue())
        self.assertIn("Remaining successful boots after reuse: 80", output.getvalue())

    def test_reuse_reparses_real_timing_and_preserves_both_original_boots(self):
        source = build.RESULTS / "frequency_campaign" / "fc-seed1"
        if not (source / "campaign_manifest.json").is_file():
            self.skipTest("fc-seed1 evidence is not available in this checkout")
        original, state = workflow.read_campaign(source)
        combo = next(item for item in original["combinations"] if item["id"] == "coremark/single_cycle/s1")
        config = {"id": "mock-import", "combinations": [combo]}
        known = {combo["id"]: campaign.candidates(combo, self.directory, state, verify=True)}
        campaign.reuse_candidates(self.directory, config, state, known, source.name, emit=lambda _: None)
        entries = campaign.candidates(combo, self.directory, state, verify=True)
        entry, confirmed = campaign.preferred(entries)
        self.assertTrue(confirmed)
        self.assertEqual(entry[3]["clock"]["effective_mhz"], 46)
        observed = boot_records(entry[2], entry[3])
        self.assertEqual(len(observed), 2)
        self.assertTrue(all(row["adopted_boot_from"]["campaign"] == source.name for row in observed))
        campaign.reuse_candidates(self.directory, config, state, known, source.name, emit=lambda _: None)
        self.assertEqual(entries, campaign.candidates(combo, self.directory, state, verify=True))

    def test_interrupted_preparation_reuses_atomic_inputs(self):
        self.args.program, self.args.arch, self.args.seed = ["coremark"], ["single_cycle"], [1, 2]
        stop = threading.Event()

        def freeze(staged, arch, program, seed):
            source = staged / "inputs" / "source.txt"
            source.parent.mkdir(parents=True)
            source.write_text(f"{arch} {program} {seed}")
            stop.set()
            return dict(git_commit="revision", rtl_fingerprint="rtl",
                        inputs={source.name: build.file_fingerprint(source)})

        with patch.object(campaign.subprocess, "check_output", return_value="revision"), \
                patch.object(build, "freeze_inputs", side_effect=freeze) as prepare:
            campaign.initialize(self.directory, self.args, stopped=stop.is_set)
            self.assertFalse((self.directory / "campaign_manifest.json").exists())
            campaign.initialize(self.directory, self.args)
        self.assertEqual(prepare.call_count, 2)
        self.assertTrue((self.directory / "campaign_manifest.json").exists())

    def test_pause_checkpoints_running_fit_before_releasing_search(self):
        combo = self.combo("coremark/single_cycle/s1")
        stop = workflow.Stop(self.directory / workflow.PAUSE)
        dispatched = []

        def fit(attempt, combination, frozen, request, *args):
            dispatched.append(request["requested_mhz"])
            with redirect_stdout(StringIO()):
                workflow.request_pause(self.directory)
            return {"status": "timing_violation", "reason": "negative slack"}

        with campaign.exclusive(self.directory), \
                patch.object(campaign.subprocess, "check_output", return_value="Version test Build 1"), \
                patch.object(build, "build", side_effect=fit):
            campaign.search(self.directory, {"id": "mock", "threads": 4, "combinations": [combo]},
                            {}, self.args, stopped=stop.is_set, emit=lambda _: None)
        self.assertEqual(dispatched, [49])
        state = build.load_json(self.directory / "campaign_state.json")
        self.assertIn("last_search_started", state)
        self.assertIn("last_search_finished", state)

    def test_unresponsive_tool_releases_worker_and_preserves_partial_log(self):
        command = [sys.executable, "-u", "-c", "import time; print('tool started'); time.sleep(30)"]
        log = self.directory / "compile.log"
        with self.assertRaises(build.ToolStopped) as failure:
            build.invoke(command, self.directory, log, build.ToolLimits(idle_seconds=0.1))
        self.assertEqual(failure.exception.status, "tool_timeout")
        self.assertIn("compile.log", str(failure.exception))
        self.assertEqual(log.read_text().strip(), "tool started")

    def test_pause_cancels_even_a_tool_that_is_still_writing(self):
        command = [sys.executable, "-u", "-c",
                   "import time;\nwhile True: print('working'); time.sleep(0.1)"]
        log = self.directory / "timequest.log"
        with self.assertRaises(build.ToolStopped) as failure:
            build.invoke(command, self.directory, log, build.ToolLimits(cancel=lambda: True))
        self.assertEqual(failure.exception.status, "interrupted")
        self.assertIn("Pause grace period expired", str(failure.exception))
        self.assertIn("working", log.read_text())

    def test_interrupted_analysis_keeps_fitted_checkpoint_for_resume(self):
        checkpoint = self.directory / "fitter.db"
        checkpoint.write_text("existing fitted database")
        request = clock_request(49)
        inputs = {"architecture": "single_cycle"}
        record = dict(inputs=inputs, request=request, compilation="complete", quartus_version="test",
                      threads=4, sof="existing.sof",
                      compile_checkpoint={checkpoint.name: build.file_fingerprint(checkpoint)})
        with patch.object(build, "invoke", side_effect=build.ToolStopped("interrupted", "paused")):
            result = build.analyze(self.directory, self.directory / "inputs", record, "test-sta")
        self.assertEqual(result["status"], "interrupted")
        self.assertTrue(build.resumable(self.directory, result, inputs, request, "test", 4))
        self.assertNotIn(result["status"], build.TERMINAL)

    def test_infrastructure_failure_does_not_compile_unneeded_lower_point(self):
        combos = [self.combo(name) for name in ("coremark/single_cycle/s1", "raw_stress/single_cycle/s1")]
        dispatched = []

        def fit(attempt, combination, frozen, request, *args):
            dispatched.append((combination.parents[1].name, request["requested_mhz"]))
            return dict(status="build_error" if combination.parents[1].name == "coremark" else "timing_pass",
                        reason="fixture")

        with patch.object(campaign.subprocess, "check_output", return_value="Version test Build 1"), \
                patch.object(build, "build", side_effect=fit), \
                patch("frequency_observation.rejected_artifacts", return_value=set()):
            campaign.search(self.directory, {"id": "mock", "threads": 4, "combinations": combos},
                            {}, self.args, emit=lambda _: None)
        self.assertCountEqual(dispatched, [("coremark", 49), ("raw_stress", 49)])

    def test_search_reports_active_tool_stage_while_waiting_for_fit(self):
        combo = self.combo("coremark/single_cycle/s1")
        displayed = threading.Event()
        output = []

        def fit(attempt, combination, frozen, request, *args):
            attempt.mkdir(parents=True)
            (attempt / "compile.log").write_text("Info: Running Quartus Prime Fitter\n")
            if not displayed.wait(5):
                raise AssertionError("The running Fitter was never reported")
            return dict(status="timing_pass", reason="sealed")

        def emit(message):
            output.append(message)
            if message.startswith("Active:") and "Quartus Prime Fitter" in message:
                displayed.set()

        with patch.object(campaign.subprocess, "check_output", return_value="Version test Build 1"), \
                patch.object(campaign, "PROGRESS_INTERVAL", 0), \
                patch.object(build, "build", side_effect=fit):
            campaign.search(self.directory, {"id": "mock", "threads": 4, "combinations": [combo]},
                            {}, self.args, emit=emit)
        self.assertTrue(any("49 MHz: starting Quartus" in line for line in output))
        self.assertTrue(any("49 MHz: timing_pass" in line for line in output))

    def test_validation_overlaps_search_and_owns_board_lock(self):
        combo = {"id": "coremark/single_cycle/s1"}
        next_fit = threading.Event()
        captured = threading.Event()
        entry = (clock_request(49), self.directory, self.directory / "a1", {"status": "timing_pass"})

        def search_fixture(directory, config, state, args, *, publish, **_):
            next_fit.set()
            publish(combo, [entry])
            if not captured.wait(5):
                raise AssertionError("Physical validation waited until search completed")

        def observe_fixture(*args, **kwargs):
            self.assertTrue(next_fit.is_set())
            with self.assertRaises(OSError):
                with campaign.exclusive(self.directory / ".board"):
                    self.fail("Board lock was shared")
            captured.set()
            return "functional_pass"

        with patch.object(workflow, "BASE", self.directory), \
                patch.object(workflow, "search", side_effect=search_fixture), \
                patch.object(workflow, "rejected_artifacts", return_value=set()), \
                patch.object(workflow, "candidates", return_value=[entry]), \
                patch.object(workflow, "boot_records", return_value=[]), \
                patch.object(workflow, "select", return_value=(entry[2], entry[3])), \
                patch.object(workflow, "observe", side_effect=observe_fixture) as capture:
            workflow.coordinate(self.directory, {"combinations": [combo]}, {}, self.args, lambda _: None,
                                workflow.Stop(self.directory / workflow.PAUSE), True)
        capture.assert_called_once()

    def test_without_board_search_completes_without_capture(self):
        with patch.object(workflow, "observe") as observe, patch.object(workflow, "search") as search:
            workflow.coordinate(self.directory, {"combinations": []}, {}, self.args, lambda _: None,
                                workflow.Stop(self.directory / workflow.PAUSE), False)
        search.assert_called_once()
        observe.assert_not_called()

    def test_late_verified_board_failure_reopens_only_its_combination(self):
        combo = {"id": "coremark/single_cycle/s1"}
        high = (clock_request(49), self.directory / "49", self.directory / "a1", {"status": "timing_pass"})
        low = (clock_request(48), self.directory / "48", self.directory / "a2", {"status": "timing_pass"})
        remaining = (low[0], low[1], None, {"status": "pending"})
        entries = [high, remaining]
        rejected = set()
        dispatched = []

        def search_fixture(directory, config, state, args, *, publish, **_):
            dispatched.append([item["id"] for item in config["combinations"]])
            if len(dispatched) == 2:
                self.assertEqual(rejected, {high[2]})
                entries[1] = low
            publish(combo, entries)

        def observe_fixture(selected, *args, **kwargs):
            if selected[0] == high[2]:
                rejected.add(high[2])
                return "functional_fail"
            self.assertEqual(selected[0], low[2])
            return "functional_pass"

        with patch.object(workflow, "BASE", self.directory), \
                patch.object(workflow, "search", side_effect=search_fixture), \
                patch.object(workflow, "rejected_artifacts", side_effect=lambda _: rejected), \
                patch.object(workflow, "candidates", side_effect=lambda *a, **k: list(entries)), \
                patch.object(workflow, "boot_records", return_value=[]), \
                patch.object(workflow, "select", side_effect=lambda entries: campaign.preferred(entries, rejected)[0][2:]), \
                patch.object(workflow, "observe", side_effect=observe_fixture) as capture:
            workflow.coordinate(self.directory, {"combinations": [combo]}, {}, self.args, lambda _: None,
                                workflow.Stop(self.directory / workflow.PAUSE), True)
        self.assertEqual(dispatched, [[combo["id"]], [combo["id"]]])
        self.assertEqual(capture.call_count, 2)

    def test_completed_campaign_never_starts_quartus_or_programmer(self):
        self.args.id = "full"
        config = campaign.configuration(workflow.full_args(self.args))
        build.save_json(self.directory / "campaign_manifest.json", config)
        checked = {c["id"]: ("functional_pass", 2) for c in config["combinations"]}
        self.args.output = self.args.latex = None
        with patch.object(workflow, "completion", return_value=checked), \
                patch.object(workflow, "require_tools") as tools, \
                patch.object(workflow, "coordinate") as execute, \
                patch.object(artifacts, "export") as export:
            workflow.run(self.directory, self.args)
        tools.assert_not_called()
        execute.assert_not_called()
        export.assert_called_once()

    def test_session_logs_background_progress_without_interrupting_board_prompt(self):
        config = campaign.configuration(workflow.full_args(self.args))
        build.save_json(self.directory / "campaign_manifest.json", config)
        self.args.output = self.args.latex = None
        self.args.quartus_pgm = "mock-pgm"

        def simulate(*args, operator_capture):
            emit = args[4]
            emit("before board prompt")
            with operator_capture():
                emit("background fit completed")
            emit("after board prompt")
            return {}

        with patch.object(workflow, "completion", return_value={}), \
                patch.object(workflow, "require_tools"), \
                patch.object(workflow, "board_available", return_value=False), \
                patch.object(workflow, "read_campaign", side_effect=[
                    (config, {}), (config, {"threads": 4})]), \
                patch.object(workflow, "coordinate", side_effect=simulate), \
                patch.object(artifacts, "export"), redirect_stdout(StringIO()) as output:
            workflow.run(self.directory, self.args)
        self.assertIn("before board prompt", output.getvalue())
        self.assertIn("after board prompt", output.getvalue())
        self.assertNotIn("background fit completed", output.getvalue())
        log = next((self.directory / "sessions").glob("*.log"))
        self.assertIn("background fit completed", log.read_text())

    def test_export_consistency_detects_modified_table_even_if_rehashed(self):
        root = self.directory
        build.save_json(root / "campaign_manifest.json", {"id": "mock", "tie_absolute_speedup": 1e-9})
        data = dict(campaign_id="mock", observations=[], paired=[], candidates=[], by_program={},
                    selections=[], descriptive_support=None)
        with patch.object(artifacts, "report", return_value=data):
            artifacts.export(root, {"id": "mock", "tie_absolute_speedup": 1e-9}, {})
        artifacts.verify(root, portable=True)
        target = root / "academic"
        table = target / "tables" / "frecuencias.tex"
        table.write_text("tampered LaTeX")
        with self.assertRaisesRegex(ValueError, "integrity check failed"):
            artifacts.verify(root, portable=True)
        manifest = build.load_json(target / "manifest.json")
        manifest["files"]["tables/frecuencias.tex"] = build.file_fingerprint(table)
        build.save_json(target / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "do not agree"):
            artifacts.verify(root, portable=True)

    def test_scientific_statistics_use_pairs_and_keep_absence(self):
        row = dict(elf_sha256="sealed", cycle_count=100, instr_retired=80, clock_mhz=40.0)
        accepted = {(program, arch, seed): row | {"clock_mhz": frequency}
                    for program in campaign.PROGRAMS for seed in workflow.SEEDS
                    for arch, frequency in (("single_cycle", 40.0), ("pipeline", 50.0))}
        pairs, summary, support = paired_results(accepted, 1e-9)
        self.assertEqual(len(pairs), 25)
        self.assertTrue(support)
        self.assertEqual(summary["coremark"]["sample_sd"], 0)
        self.assertAlmostEqual(pairs[0]["time_reduction_pct"], 20.0)
        self.assertAlmostEqual(pairs[0]["achieved_frequency_increase_pct"], 25.0)
        self.assertEqual(metrics(row)["cpi"], 1.25)
        del accepted[("coremark", "pipeline", 5)]
        pairs, summary, support = paired_results(accepted, 1e-9)
        self.assertEqual(len(pairs), 24)
        self.assertIsNone(summary["coremark"]["meets_descriptive_rule"])
        self.assertIsNone(support)
