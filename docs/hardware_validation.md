# Hardware validation on the DE1-SoC

Scope: what is verified automatically before the FPGA is programmed, what the
board shows while a program runs, and which parts of the documented
"SignalTap cross-validation" flow are broken in Quartus Prime 25.1.

Board: Cyclone V 5CSEMA5F31C6 (DE1-SoC), programmed over the USB-Blaster
(`quartus_pgm --list` reports `DE-SoC [USB-1]`).

---

## 1. The program must reach the FPGA memory, not just the simulation

The program travels through two files:

| Artifact | Consumer | Purpose |
|---|---|---|
| `build/imem.mem`, `build/dmem.mem` | `rtl/*/instruction_memory*.sv`, `data_memory*.sv` via `$readmemh` | the program itself, loaded into the M10K blocks |
| `synthesis/<arch>/screen.mif` | `rtl/shared/video_memory.sv` (`ram_init_file`) | the console template, including a dump of the program image |

`rtl/shared/mem_config.vh` carries the `$readmemh` paths. The paths are
relative to the **Quartus project directory** (`synthesis/<arch>`), so the
header has to be regenerated for every build - the simulation and the
synthesis build use different memory images (16384/8192 words in simulation,
2048/512 words in the FPGA), and the simulation must never overwrite the
header that the Quartus build reads.

### 1.1 Automatic check of the bitstream contents

`scripts/check_mem_init.py` reads back the `.hdl.mif` files that Quartus
generates in `synthesis/<arch>/db/` and compares them word by word with the
`.mem` sources:

```console
$ python3 scripts/check_mem_init.py --project synthesis/pipeline
Project      : .../synthesis/pipeline
mem_config.vh: IMEM=../../build/imem.mem DMEM=../../build/dmem.mem
  ok    IMEM_FILE -> .../build/imem.mem
  ok    DMEM_FILE -> .../build/dmem.mem
IMEM rv32im_pipeline.ram0_instruction_memory_pipe_b61c7bc4.hdl.mif (depth 2048)
  PASS  IMEM: 2048 words identical
DMEM 4 byte lanes (depth 512)
  PASS  DMEM: 512 words identical

RESULT: PASS
```

This is the check that proves the bitstream contains the program that was
asked for, instead of a stale image left in `build/` by an earlier run.

### 1.2 The console shows the same program

`screen.mif` is regenerated from `build/imem.mem` by
`scripts/gen_screen_artifacts.sh` (invoked by `make mem`, `make flash` and
`make build`), so the "Prog. Memory" table of the console
shows the same words that the instruction memory holds.  The first words of
`rv32ui/add.elf` are visible in the console as:

```
0000: 0480006f   0004: 34202f73   0008: 00080093   000c: 03ff0863
```

---

## 2. On-board check (what to look at)

The board is programmed with

```console
$ make program ARCH=pipeline        # or: quartus_pgm -c "DE-SoC" -m JTAG -o "P;<sof>@2"
```

Note the device index: the DE1-SoC chain is USB-Blaster -> MAX10 -> Cyclone
V, so the FPGA is device **2**.  Programming device 1 configures the MAX10
and fails with a JTAG ID mismatch.

With `rv32ui/add.elf` loaded, the VGA console shows:

| Field | Expected | Meaning |
|---|---|---|
| `CyclesToPass` | `000000000000022d` | clock cycles of the program, frozen when it wrote to `tohost` |
| `InstrToPass` | `0000000000000188` | instructions retired by the program, frozen at the same instant |
| `HALTED` | `1` | the program reached its end |
| `Data Write` | `00000001` | the value written to `tohost` (1 = pass) |
| `Prog. Memory` | `0480006f 34202f73 ...` | the program image, identical to the `.mem` |

The 7-segment displays show the instruction in WB (nibble per display) and
`LEDR` shows the low 10 bits of the PC.

`CyclesToPass` and `InstrToPass` are the numbers the thesis reports: they are
frozen by the processor when the program writes to `tohost`, and the cocotb
test asserts that they are **identical** to the values the simulation
reports, so the photograph of the board and the CPI table are the same
measurement.  See ADR 042.

Reference values from the simulation for the same program:

| Architecture | cycle_count | instr_retired | CPI | On board |
|---|---|---|---|---|
| pipeline | 557 | 392 | 1.4209 | `CyclesToPass: 000000000000022d`, `InstrToPass: 0000000000000188` |
| single_cycle | 503 | 503 | 1.0000 | `CyclesToPass: 00000000000001f7`, `InstrToPass: 00000000000001f7` |

### 2.1 Checklist for the photographs

1. `make mem ELF=build/riscv-tests/rv32ui/add.elf ARCH=<arch>`
2. `make build ARCH=<arch>` (regenerates `mem_config.vh` and `screen.mif`)
3. `make program ARCH=<arch>`
4. Photograph the monitor.  The picture must show, in one frame:
   `CyclesToPass` and `InstrToPass` with the values of the table above, the
   `Prog. Memory` table with `0480006f 34202f73 00080093 03ff0863` as the
   first four words, and `Data Write: 00000001`.
5. Repeat with `build/synthetic/raw_stress.elf` for the pipeline, which
   exercises the forwarding path.

The cycle-by-cycle trace that accompanies the photographs is generated with

```console
$ make -C verification/cocotb/pipeline TEST=test_pipeline_trace \
       COCOTB_TEST_MODULES=test_pipeline_trace
```

which writes `results/trace_pipeline.csv` and `results/trace_pipeline.tex`
(the state of the five stages on every cycle, including the load-use stall
and the branch flush).

---

## 3. The SignalTap cross-validation flow does not work in Quartus Prime 25.1

`scripts/run_capture.tcl`, `scripts/create_stp.tcl` and the `.stp` files in
`stp/` were written against the Quartus II SignalTap Tcl API.  In Quartus
Prime 25.1:

* the `stp_open` / `stp_run` / `stp_export` commands no longer exist - the
  `::quartus::stp` package loads but registers no command;
* `quartus_sh -t scripts/create_stp.tcl` fails with
  `ERROR: Quartus Prime Tcl package "::quartus::stp" is only available for use
  in the following executables: quartus_stp, quartus_stp_tcl`;
* the hand-written XML in `stp/perf_capture_*.stp` is rejected:
  `Error (262006): File "..." is not a valid Signal Tap File -- ignoring`, so
  a "SignalTap build" silently produces a design **without** any tap logic;
* `run_capture.tcl` had a Tcl error in `lindex $argv 1 [default]` and
  programmed device 1 instead of the FPGA.

What is in place now:

* `scripts/create_stp.tcl` writes the `.stp` file directly as XML, without the
  removed API.  The file it produces still has to be accepted by the
  SignalTap II GUI, because only the GUI writes a file that Quartus 25.1
  accepts.
* `scripts/run_capture.tcl` programs device 2 and stops with an explicit
  message when the SignalTap Tcl API is missing, instead of failing with
  `invalid command name "stp_open"`.

To capture the counters from the board:

1. `make build-fpga ARCH=<arch>` (compiles with `ENABLE_SIGNALTAP`).
2. Open the SignalTap II GUI with that project, load
   `stp/perf_capture_<arch>.stp`, run the acquisition and export the waveform
   as CSV to `results/capture_<arch>.csv`.
3. `make cross-validate ARCH=<arch>` compares it with the cocotb reference.

The alternative that needs no GUI is to add an ISSP/UART channel to the
design and read the counters over the DE1-SoC RS-232 port; that is RTL work
and was not done here.

---

## 4. Defects found while validating (all fixed)

| # | Defect | Effect |
|---|---|---|
| 1 | the cocotb flow regenerated `rtl/shared/mem_config.vh` with a path relative to the simulation directory | the Quartus build pointed at a non-existent file: the FPGA booted with an **empty** instruction memory |
| 2 | the simulation and the synthesis shared `build/imem.mem` (16384 vs 2048 words) | the FPGA could be loaded with a 16384-word image for a 2048-word memory |
| 3 | `make build ELF=...` reused `build/program.bin` when the ELF was older than the binary | the bitstream contained the **previous** program, silently |
| 4 | `fpga_validate.py` passed a relative ELF path to the cocotb test | the reference run failed and a **stale CSV** was used as the reference |
| 5 | `run_capture.tcl` used `lindex $argv 1 [default]` | `make capture` always failed with a Tcl error |
| 6 | `run_capture.tcl` programmed device 1 (MAX10) | the FPGA was never configured |
| 7 | `create_stp.tcl` ran under `quartus_sh` | the SignalTap file was never created |
| 8 | the font ROM path was relative to the Quartus project directory | the font ROM was empty in every simulation |
| 9 | the common cocotb suite is single-cycle specific (its Makefile lists the single-cycle sources) | running it with `TOPLEVEL=top_pipeline` fails at elaboration; the pipeline has its own RV32I/M/MI suites in `verification/cocotb/pipeline/` |
| 10 | `RTL_ROOT` was undefined in the Makefile | the screen-writer dependency rule pointed at `/pipeline/...` |
| 11 | the pipeline executed a branch twice when a load-use hazard put a branch behind a load | the pipeline could not run CoreMark; see ADR 043 |
| 12 | the RTL dumped the whole waveform on every simulation | a CoreMark run wrote 10 GB of VCD and became I/O bound; the dump is now off unless `-DDUMP_VCD` is given |
| 13 | the synthetic benchmarks put `tohost` at 0x100, the riscv-tests at 0x708 | one bitstream could not detect the end of every benchmark; the synthetic programs now use 0x708 |
| 14 | the pipeline counter only counted the instructions that write a register | the CPI of the pipeline excluded the branches and the stores and was up to twice the correct value (ADR 024) |
| 15 | the MEM-RAW hazard let the ID/EX register capture the consumer that was still in the IF/ID | the consumer was executed twice; with a branch the PC was redirected twice, with a load the program diverged from the single-cycle and CoreMark never finished (ADR 043) |

---

## 5. The counters must mean the same thing in both designs (ADR 024)

The CPI of the two microarchitectures is only comparable if both count the
same thing.  The single-cycle counts every cycle in which an instruction
retires; the pipeline counted only the instructions that write a register,
because `valid_wb` required `wb_ru_wr`.  The branches and the stores were
therefore missing from the denominator, and the CPI of the pipeline was
inflated (the branch-stress benchmark: 4003 executed instructions counted as
2003, a CPI of 4.0 instead of 2.0).

`valid_wb` now depends on the bubble only, and
`scripts/measure_benchmarks.py` compares the instruction counts of the two
designs and marks a benchmark as `divergent` when they differ.  That check is
what found the defect of the next section.

## 6. The pipeline bug that the benchmark found (ADR 043)

The pipeline never reached the `tohost` write of CoreMark, while the
single-cycle completed it.  Comparing the stream of retired program
counters of both designs located the first divergence:

```
1cc8:  lh    a4, 2032(a5)
1ccc:  beqz  a4, 2028          <- retired twice by the pipeline
1cd0:  addi  t1, sp, 80
```

The minimal reproduction is a load followed by a branch:

```systemverilog
lh   a4, 0(a5)      // the load
beqz a4, +8        // the branch that consumes the load
```

During the second cycle of the load-use stall the IF/ID register was held
(so the consumer stayed in ID) while the ID/EX register kept advancing (its
hold input was wired to the division stall only).  The consumer was copied
into EX while it stayed in ID, and it was executed twice.

The fix holds the ID/EX register whenever the pipeline stalls for a reason
other than the load-use bubble, and the regression test
`test_load_use_on_branch_executes_branch_once` counts the retirements of
the branch.

This defect was invisible to the riscv-tests because none of them places a
branch directly behind a load, and to the ALU consumers of a load-use
hazard, because a duplicated ALU instruction writes the same value twice.

