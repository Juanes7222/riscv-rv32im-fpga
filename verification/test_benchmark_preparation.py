"""Regression tests for obsolete CoreMark ELFs and simulation boot images."""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fpga_validate
import measure_benchmarks as benchmarks
from verification.cocotb.common import tohost


class BenchmarkPreparationTests(unittest.TestCase):
    def test_selected_coremark_variants_are_built_with_explicit_parameters(self):
        with patch.object(benchmarks.subprocess, "run") as run:
            with patch.object(benchmarks, "validate_coremark_elf") as validate:
                with contextlib.redirect_stdout(io.StringIO()):
                    benchmarks.prepare_coremark_benchmarks(benchmarks.BENCHMARKS)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(validate.call_count, 2)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn("ITERATIONS=10", commands[0])
        self.assertIn("ITERATIONS=1", commands[1])
        for command in commands:
            self.assertIn("RUN_MODE=PERFORMANCE_RUN", command)
            self.assertIn("TOTAL_DATA_SIZE=2000", command)

    def test_preparation_failure_prevents_all_simulations(self):
        with patch.object(sys, "argv", ["measure_benchmarks.py", "--only", "coremark_iter10"]):
            with patch.object(benchmarks, "prepare_coremark_benchmarks", side_effect=ValueError("obsolete ELF")):
                with patch.object(benchmarks, "run_cocotb_validation") as simulate:
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(benchmarks.main(), 1)
                simulate.assert_not_called()

    def test_reading_historical_csvs_does_not_rebuild_programs(self):
        with tempfile.TemporaryDirectory() as temporary:
            arguments = ["measure_benchmarks.py", "--from-csv", "--output", str(Path(temporary) / "summary.csv")]
            with patch.object(sys, "argv", arguments), patch.object(benchmarks, "BENCHMARKS", []):
                with patch.object(benchmarks, "read_fmax", return_value={}):
                    with patch.object(benchmarks, "prepare_coremark_benchmarks") as prepare:
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertEqual(benchmarks.main(), 0)
                        prepare.assert_not_called()

    def test_validation_boots_the_generated_images_at_the_selected_depths(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            output = directory / "result.csv"
            imem, dmem = directory / "imem.mem", directory / "dmem.mem"

            def simulated_make(command, **kwargs):
                output.write_text("result,cycle_count,instr_retired\npass,1,1\n")
                return subprocess.CompletedProcess(command, 0, stdout="simulation log", stderr="")

            with patch("verification.cocotb.common.tohost.generate_mem_for_elf", return_value=(imem, dmem)):
                with patch.object(fpga_validate, "_get_tohost_addr", return_value=0x6000):
                    with patch.dict(os.environ, {"IMEM_DEPTH": "4096", "DMEM_DEPTH": "1024"}):
                        with patch.object(fpga_validate.subprocess, "run", side_effect=simulated_make) as run:
                            result = fpga_validate.run_cocotb_validation(directory / "coremark.elf", "pipeline", output)
            command = run.call_args.args[0]
            self.assertEqual(result["result"], "pass")
            self.assertIn(f"SIM_IMEM={imem}", command)
            self.assertIn(f"SIM_DMEM={dmem}", command)
            self.assertIn("IMEM_DEPTH=4096", command)
            self.assertIn("DMEM_DEPTH=1024", command)
            self.assertEqual(output.with_suffix(".log").read_text(), "simulation log")

    def test_memory_conversion_uses_the_active_python_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            elf = directory / "program.elf"
            elf.write_bytes(b"ELF fixture")
            with patch.object(tohost, "BUILD_DIR", directory):
                with patch.object(tohost.subprocess, "run") as run:
                    tohost.generate_mem_for_elf(elf)
            self.assertEqual(run.call_args.args[0][0], sys.executable)

    def test_current_replica_frequencies_take_priority_over_legacy_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "results_fmax.csv").write_text(
                "arch,fmax_mean_mhz\nsingle_cycle,48.244\npipeline,63.886\n")
            (directory / "results_synthesis.csv").write_text(
                "arch,fmax_mean_mhz\nsingle_cycle,49.1\npipeline,62.15\n")
            with patch.object(benchmarks, "RESULTS_DIR", directory):
                self.assertEqual(benchmarks.read_fmax(),
                                 {"single_cycle": 48.244, "pipeline": 63.886})


@unittest.skipUnless(shutil.which("riscv-none-elf-gcc"), "RISC-V compiler required")
class CoreMarkElfContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def build_fixture(self, *, iterations=1, tohost=0x6000, crc_record=True):
        source = self.directory / "fixture.S"
        text = ".section .text\n.globl _start\n_start: j _start\n"
        text += '.section .tohost,"aw"\n.globl tohost\ntohost: .word 0\n.section .data\n'
        for name, value in (("seed1_volatile", 0), ("seed2_volatile", 0),
                            ("seed3_volatile", 0x66), ("seed4_volatile", iterations)):
            text += f".globl {name}\n{name}: .word {value}\n"
        text += ".comm static_memblk,2000,4\n"
        if crc_record:
            text += ".comm coremark_validation,64,4\n"
        source.write_text(text)
        linker = self.directory / "fixture.ld"
        linker.write_text(f"SECTIONS {{ . = 0; .text : {{ *(.text) }} . = {tohost}; "
                          ".tohost : { *(.tohost) } .data : { *(.data) } .bss : { *(COMMON) } }")
        elf = self.directory / "fixture.elf"
        subprocess.run(["riscv-none-elf-gcc", "-march=rv32im", "-mabi=ilp32", "-nostdlib",
                        "-T", str(linker), str(source), "-o", str(elf)],
                       capture_output=True, text=True, check=True)
        return elf

    def test_current_port_contract_is_accepted(self):
        benchmarks.validate_coremark_elf(self.build_fixture(iterations=10), 10)

    def test_missing_crc_record_is_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError, "missing coremark_validation"):
            benchmarks.validate_coremark_elf(self.build_fixture(crc_record=False), 1)

    def test_old_memory_map_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "obsolete CoreMark memory map"):
            benchmarks.validate_coremark_elf(self.build_fixture(tohost=0x5000), 1)

    def test_wrong_iteration_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "seed4_volatile"):
            benchmarks.validate_coremark_elf(self.build_fixture(iterations=1), 10)


if __name__ == "__main__":
    unittest.main()
