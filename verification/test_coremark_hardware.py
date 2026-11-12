"""Physical completion evidence must match the program, bitstream and counters."""

import contextlib
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from elftools.elf.elffile import ELFFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import coremark_hardware as physical
import generate_reports as reports
import hardware_measure as hardware
import thesis_artifacts as artifacts
from campaign_state import file_fingerprint
from verification.reference_model import CPU


class ConsoleCaptureTests(unittest.TestCase):
    def test_crc_status_is_read_separately_from_counters(self):
        with patch("builtins.input", side_effect=["0x2fd26d00", "0x25689c43", "00000001", "16.05", "observed"]):
            with contextlib.redirect_stdout(io.StringIO()):
                values = hardware.ask_vga_values(0x6000, coremark=True)
        self.assertEqual(values["crc_status"], "0x1")
        self.assertEqual(values["cycle_count"], 802319616)
        self.assertEqual(values["instr_retired"], 627612739)
        self.assertEqual(values["seconds"], 16.05)

    def test_blank_status_does_not_manufacture_crc_success(self):
        with patch("builtins.input", side_effect=["10", "8", "", "", ""]):
            with contextlib.redirect_stdout(io.StringIO()):
                values = hardware.ask_vga_values(0x6000, coremark=True)
        self.assertEqual(values["crc_status"], "")


@unittest.skipUnless(shutil.which("riscv-none-elf-gcc"), "RISC-V compiler required")
class PhysicalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.results = self.root / "results"
        self.results.mkdir()
        self.elf = self.build_fixture()
        self.sof = self.root / "synthesis/pipeline/output_files/rv32im_pipeline.sof"
        self.sof.parent.mkdir(parents=True)
        self.sof.write_bytes(b"physical bitstream fixture")
        memory_log = self.results / "hardware_evidence/memory.log"
        memory_log.parent.mkdir()
        memory_log.write_text("  PASS  IMEM: 4096 words identical\nRESULT: PASS\n")
        self.provenance = dict(rtl="current", elf=file_fingerprint(self.elf),
                               sof=file_fingerprint(self.sof), memory_check="hardware_evidence/memory.log",
                               memory_check_sha256=file_fingerprint(memory_log))
        for name, value in (("REPO_ROOT", self.root), ("RESULTS", self.results)):
            replacement = patch.object(hardware, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        replacement = patch.object(hardware, "source_fingerprint", return_value="current")
        replacement.start()
        self.addCleanup(replacement.stop)

    def build_fixture(self, *, crc_record=True):
        source = self.root / "fixture.S"
        text = '.section .text\n.globl _start\n_start: j _start\n.section .tohost,"aw"\n'
        text += ".globl tohost\ntohost: .word 0\n.section .data\n"
        for name, value in (("seed1_volatile", 0), ("seed2_volatile", 0),
                            ("seed3_volatile", 0x66), ("seed4_volatile", 2000)):
            text += f".globl {name}\n{name}: .word {value}\n"
        text += ".comm static_memblk,2000,4\n"
        if crc_record:
            text += ".comm coremark_validation,64,4\n"
        source.write_text(text)
        linker = self.root / "fixture.ld"
        linker.write_text("SECTIONS { . = 0; .text : { *(.text) } . = 0x6000; "
                          ".tohost : { *(.tohost) } .data : { *(.data) } .bss : { *(COMMON) } }")
        elf = self.root / "coremark.elf"
        subprocess.run(["riscv-none-elf-gcc", "-march=rv32im", "-mabi=ilp32", "-nostdlib",
                        "-T", str(linker), str(source), "-o", str(elf)],
                       capture_output=True, text=True, check=True)
        return elf

    def capture(self, status="0x1"):
        path = self.results / "hardware_pipeline_coremark_v2.csv"
        values = dict(cycle_count=100, instr_retired=80, cpi="1.25", seconds="",
                      notes="", crc_status=status)
        with contextlib.redirect_stdout(io.StringIO()):
            hardware.save_csv(path, "pipeline", "coremark", 0x6000, values,
                              self.elf, self.provenance)
        with path.open() as stream:
            return list(csv.DictReader(stream))[-1]

    def test_crc_gated_success_has_auditable_archived_evidence(self):
        row = self.capture()
        self.assertEqual(row["result"], "pass")
        self.assertEqual(physical.check_observation(row, self.results, "current")[0], True)
        self.assertTrue(all(path.is_file() for path in physical.observation_inputs(row, self.results)))
        with patch.object(hardware, "COREMARK_ELF", self.elf):
            self.assertTrue(hardware.already_measured_ok("pipeline", "coremark")[0])

    def test_failure_and_missing_observation_never_pass(self):
        for status, expected in (("0x3", "crc-fail"), ("", "terminated-unvalidated")):
            with self.subTest(status=status):
                row = self.capture(status)
                self.assertEqual(row["result"], expected)
                self.assertFalse(physical.check_observation(row, self.results, "current")[0])

    def test_changed_counter_cannot_reuse_an_observation(self):
        row = self.capture()
        row["cycle_count"] = "101"
        self.assertFalse(physical.check_observation(row, self.results, "current")[0])

    def test_changed_result_cannot_reuse_an_observation(self):
        row = self.capture()
        row["result"] = "crc-fail"
        self.assertFalse(physical.check_observation(row, self.results, "current")[0])

    def test_changed_bitstream_cannot_reuse_an_observation(self):
        row = self.capture()
        physical.observation_inputs(row, self.results)[1].write_bytes(b"different")
        self.assertFalse(physical.check_observation(row, self.results, "current")[0])

    def test_changed_memory_check_cannot_reuse_an_observation(self):
        row = self.capture()
        (self.results / row["memory_check"]).write_text("RESULT: FAIL\n")
        self.assertFalse(physical.check_observation(row, self.results, "current")[0])

    def test_empty_successful_memory_check_is_not_evidence(self):
        path = self.results / self.provenance["memory_check"]
        path.write_text("RESULT: PASS\n")
        self.provenance["memory_check_sha256"] = file_fingerprint(path)
        row = self.capture()
        self.assertFalse(physical.check_observation(row, self.results, "current")[0])

    def test_stale_rtl_and_boolean_flag_alone_are_rejected(self):
        row = self.capture()
        self.assertFalse(physical.check_observation(row, self.results, "other RTL")[0])
        row.pop("crc_evidence")
        row["coremark_functional_valid"] = "True"
        self.assertFalse(physical.check_observation(row, self.results, "current")[0])

    def test_legacy_elf_cannot_be_promoted_using_a_tohost_one(self):
        self.build_fixture(crc_record=False)
        self.provenance["elf"] = file_fingerprint(self.elf)
        with self.assertRaisesRegex(ValueError, "missing coremark_validation"):
            self.capture()

    def test_rebuilding_preserves_the_obsolete_board_program(self):
        self.build_fixture(crc_record=False)
        old_hash = file_fingerprint(self.elf)
        with patch.object(physical, "prepare_coremark_elf") as build:
            physical.prepare_hardware_coremark(self.elf)
        self.assertEqual(file_fingerprint(self.elf.parent / "previous" / f"{old_hash}.elf"), old_hash)
        build.assert_called_once_with(self.elf, 2000)

    def test_board_program_is_prepared_before_consulting_cached_readings(self):
        events = []
        with patch.object(hardware, "COREMARK_ELF", self.elf):
            with patch.object(hardware, "prepare_hardware_coremark", side_effect=lambda elf: events.append("build")):
                with patch.object(hardware, "already_measured_ok", side_effect=lambda *args: (events.append("cache") or (True, "current"))):
                    with contextlib.redirect_stdout(io.StringIO()):
                        hardware.measure_one("coremark", "pipeline", elf=self.elf)
        self.assertEqual(events, ["build", "cache"])

    def test_real_startup_preserves_the_crc_exit_code_in_x5(self):
        port = Path(__file__).resolve().parents[1] / "programs/coremark"
        for main_result, expected_status in ((0, 1), (1, 3)):
            with self.subTest(main_result=main_result):
                stub = self.root / "exit.S"
                stub.write_text(f".section .text\n.globl main\nmain: li a0,{main_result}\nret\n")
                elf_path = self.root / "exit.elf"
                subprocess.run(["riscv-none-elf-gcc", "-march=rv32im", "-mabi=ilp32", "-nostdlib",
                                "-T", str(port / "link.ld"), str(port / "start.S"), str(stub),
                                "-o", str(elf_path)], capture_output=True, text=True, check=True)
                cpu = CPU(imem_size=16384, dmem_size=4096)
                with elf_path.open("rb") as stream:
                    text = ELFFile(stream).get_section_by_name(".text").data()
                cpu.imem[:len(text)] = text
                for _ in range(100):
                    cpu.step()
                self.assertEqual(cpu.load_word(0x6000), expected_status)
                self.assertEqual(cpu.regs[5], expected_status)

    def test_program_changed_during_capture_is_rejected(self):
        self.elf.write_bytes(b"changed after programming")
        with self.assertRaisesRegex(ValueError, "changed while"):
            self.capture()

    def test_schema_extension_preserves_previous_physical_readings(self):
        path = self.results / "hardware_pipeline_coremark_v2.csv"
        original = "architecture,program,result,cycle_count,instr_retired\npipeline,coremark,terminated-unvalidated,99,79\n"
        path.write_text(original)
        self.capture()
        with path.open() as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["cycle_count"], "99")
        self.assertEqual(rows[1]["result"], "pass")

    def test_reports_use_current_physical_reading_instead_of_historical_counts(self):
        self.capture()
        historical = self.results / "results_coremark.csv"
        historical.write_text("architecture,iterations,cycles,instructions,clock_mhz\n"
                              "pipeline,2000,999,900,50\n")
        before = historical.read_bytes()
        with patch.multiple(artifacts, INPUT_RESULTS=self.results, COREMARK_INPUT_CSV=historical):
            with patch.object(artifacts, "source_fingerprint", return_value="current"):
                rows = artifacts.read_coremark_hardware()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cycles"], 100)
        self.assertEqual(rows[0]["coremark_functional_valid"], "True")
        self.assertEqual(historical.read_bytes(), before)

    def test_physical_capture_cannot_be_relabelled_as_the_other_architecture(self):
        self.capture()
        shutil.copy2(self.results / "hardware_pipeline_coremark_v2.csv",
                     self.results / "hardware_single_cycle_coremark_v2.csv")
        with patch.multiple(artifacts, INPUT_RESULTS=self.results,
                            COREMARK_INPUT_CSV=self.results / "results_coremark.csv"):
            with patch.object(artifacts, "source_fingerprint", return_value="current"):
                rows = {row["arch"]: row for row in artifacts.read_coremark_hardware()}
        self.assertEqual(rows["single_cycle"]["coremark_functional_valid"], "False")
        with patch.object(hardware, "COREMARK_ELF", self.elf):
            self.assertFalse(hardware.already_measured_ok("single_cycle", "coremark")[0])

    def test_report_manifest_tracks_the_physical_capture_and_its_artifacts(self):
        row = self.capture()
        files = reports.input_files(self.results, self.root / "verification")
        for path in physical.observation_inputs(row, self.results):
            self.assertIn(path, files)
        self.assertIn(self.results / "hardware_pipeline_coremark_v2.csv", files)

    def test_strict_gate_rejects_synthesis_from_a_different_program(self):
        row = self.capture()
        replica = self.results / "pipeline/replica_1"
        replica.mkdir(parents=True)
        manifest = replica / "manifest.json"
        hardware_row = dict(arch="pipeline", coremark_functional_valid="True", elf_sha256=row["elf_sha256"])
        measurement = dict(arch="pipeline", replica=1, fmax_mhz=50,
                           **{key: 1 for key in artifacts.RESOURCE_PATTERNS})
        with patch.object(artifacts, "INPUT_RESULTS", self.results):
            with patch.object(artifacts, "read_coremark_hardware", return_value=[hardware_row]):
                with patch.object(reports, "source_fingerprint", return_value="current"), patch.object(reports, "verified", return_value=True):
                    for program, mismatched in (("old program", True), (row["elf_sha256"], False)):
                        manifest.write_text(json.dumps({"inputs": {"build/coremark/coremark.elf": program}}))
                        issues = reports.evidence_issues([measurement], [], [], tests_ran=True)
                        self.assertEqual(any("synthesized workload differs" in issue for issue in issues), mismatched)


if __name__ == "__main__":
    unittest.main()
