# Getting started

This guide covers what has to be installed, how to run each stage of the flow, and
which parameters have to stay consistent across the RTL, the linker scripts and the
Quartus project. The [`README.md`](../README.md) is the entry point; this document is
the reference for working on the project.

---

## 1. Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Intel Quartus Prime | 25.1 (Lite Edition) | Targets Cyclone V `5CSEMA5F31C6` |
| Icarus Verilog | 12.0 | Simulation backend for cocotb |
| Python | 3.12 | Repository-local virtualenv in `.venv/` |
| cocotb | 2.0.1 | Pinned in `requirements.txt` |
| `riscv-none-elf-gcc` | 14.2.0 (xPack) | Builds the ISA test suite and the benchmarks |
| GNU Make | any recent | The root `Makefile` is the entry point for every flow |

The Quartus command-line tools must be reachable as `quartus_sh`, `quartus_pgm` and
`quartus_stp`. On a Windows Quartus installation under WSL they are named
`quartus_sh.exe` and friends; the root `Makefile` already uses the `.exe` names for
that reason. Adjust the `QUARTUS_*` variables at the top of the `Makefile` if your
installation exposes them without the suffix.

`requirements.txt` also pins a large set of unrelated packages from the development
machine. Installing it wholesale is harmless but unnecessary; the simulation only needs
`cocotb`, `pytest` and `pyelftools`, and the screen-artifact generation needs
`openpyxl`.

## 2. Getting the sources

```bash
git clone --recurse-submodules https://github.com/Juanes7222/riscv-rv32im-fpga.git
cd riscv-rv32im-fpga
```

Two submodules are used:

- `verification/riscv-tests` — the official RISC-V ISA test suite, pinned to a fixed
  commit so that the verification results are reproducible.
- `programs/coremark/src` — the EEMBC CoreMark source, ported to bare metal in
  `programs/coremark/`.

## 3. Python environment

The cocotb Makefiles call `cocotb-config`, so the virtualenv has to be on `PATH`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The root `Makefile` invokes `.venv/bin/python3` directly for the report and
cross-validation scripts, so the virtualenv must live at `.venv/` in the repository
root.

## 4. Building the ISA test programs

The `riscv-tests` binaries are consumed by the cocotb suites, so they have to exist
before any simulation runs:

```bash
make -C verification/riscv-tests all
```

This compiles the RV32I, RV32M and RV32MI suites into `build/riscv-tests/`. The
linker script used for the build places the reset vector at `0x00000000` and exports a
`tohost` symbol, which is what the testbench monitors to decide pass or fail. See
[ADR 027](../docs/decisions/027_riscv-tests_compilation.md) for the rationale.

> **Known gap.** The project-local build harness for the submodule — the custom
> `link.ld` and the `Makefile` that drives the compilation — is not currently tracked
> in the parent repository, because the submodule's own `.gitignore` excludes
> `/Makefile` and the parent cannot commit files inside a submodule path. A fresh
> clone therefore cannot rebuild the suite from scratch until those two files are
> moved outside the submodule (for example to `verification/riscv-tests-build/`) and
> tracked there.

## 5. Running the verification suites

```bash
make verify-full          # both architectures, all suites
make verify-all-sc        # single-cycle only
make verify-all-pipe      # pipeline only
```

`make verify-all-sc` runs the shared ISA suites against the single-cycle top level
plus the single-cycle-specific suite; `make verify-all-pipe` runs the pipeline
suites. The breakdown by suite, and the pass/fail convention used for the
machine-mode tests, are described in
[`docs/verification/plan.md`](verification/plan.md).

To regenerate the report and the LaTeX tables from the existing results without
re-running the simulations:

```bash
make report-quick
```

This writes `results/results_report.md`, `results/results_latex.tex` and the CSV files
under `results/`.

## 6. Synthesis

Each architecture has its own Quartus project, so that no configuration can leak from
one design into the other.

```bash
make setup ARCH=pipeline          # create the project (once per architecture)
make build ARCH=pipeline          # compile
make replicas ARCH=pipeline       # N_REPLICAS independent runs, Fmax extracted
make program ARCH=pipeline        # program the board with the last bitstream
```

`make replicas` re-runs the full Quartus flow with a different fitter seed each time
and extracts the Fmax from every timing report, which is what makes the comparison
statistically meaningful rather than a single lucky run. The number of replicas is
set with `N_REPLICAS` (default 5).

`make help` lists the remaining targets: `sync` and `sync-all` to re-register RTL
files after adding a new module, `clean` and `clean-all` to remove synthesis
artifacts, `results` and `status` to inspect what has been built.

The bitstream is programmed over JTAG with `quartus_pgm`. `program.tcl` scans the
JTAG chain before programming so that a board or cable problem is not mistaken for a
bitstream problem.

## 7. Programming a program and running on hardware

The FPGA build does not use the ELF directly. It is converted to a flat binary, then
to a `$readmemh` image, and the path to that image is injected into the RTL through
`rtl/shared/mem_config.vh`:

```bash
make flash ARCH=pipeline ELF=build/coremark/coremark.elf
```

`make flash` performs the whole chain: `objcopy` to binary, conversion to `.mem`,
regeneration of `mem_config.vh`, synthesis, and programming. To rebuild a program
image without synthesizing, use `make mem ELF=...`.

For CoreMark, build it first:

```bash
make -C programs/coremark                 # performance run, 2000 iterations
make -C programs/coremark ITERATIONS=3 TOTAL_DATA_SIZE=120   # simulation-sized run
```

The CoreMark memory map and the reason its `.tohost` symbol has to sit at `0x5000`
are documented in
[`docs/coremark_integration.md`](coremark_integration.md).

### Cross-validating the hardware against the simulation

The processor carries performance counters (`cycle_count`, `instr_retired`) that can be
read out of the FPGA with SignalTap II and compared against the same numbers obtained
in simulation:

```bash
python scripts/fpga_validate.py --elf build/riscv-tests/rv32ui/add.elf --fpga-only
make build-fpga ARCH=pipeline     # build with the SignalTap II .stp file
make capture ARCH=pipeline        # capture from the programmed board
make cross-validate ARCH=pipeline COCOTB_CSV=results/validation_pipeline.csv
```

## 8. Configuration that has to stay consistent

These are the places where the same value appears more than once. Changing one
without the others produces a design that simulates correctly and misbehaves on
hardware, or the reverse.

| Value | Where it is set | Notes |
|---|---|---|
| Reset vector `0x00000000` | `rtl/*/pc_unit.sv`, every linker script | The instruction memory is mapped at address 0 |
| `IMEM_DEPTH` / `DMEM_DEPTH` | `synthesis/*/*.qsf` (`set_parameter`), the root `Makefile`, `verification/cocotb/common.mk` | Synthesis uses small depths for fast compiles (2048/512); the simulation uses 16384/8192 |
| `tohost` address | linker script, `TOHOST_ADDR` parameter in both top levels | The testbench monitors writes to this address to decide pass or fail |
| `TOHOST_ADDR` default | `0x708` in `top_single_cycle.sv` and `top_pipeline.sv` | Matches the `riscv-tests` layout |
| CPU clock | `synthesis/*/constraints.sdc` | 10 ns target, so the analyzer reports the achievable Fmax rather than stopping at an artificial target |
| VGA clock | `rtl/shared/vga_pll.sv`, `constraints.sdc` | 74.25 MHz PLL, declared as a false path against the processor clock |
| Pin assignments | `synthesis/*/*.qsf` | `CLK_50` on `PIN_AF14`, `KEY[0]` on `PIN_AA14`, LEDs, six 7-segment displays and the VGA connector |
| `SEED` | `synthesis/*/*.qsf`, or the argument to `build.tcl` | The fitter seed; each synthesis replica uses a different one |

The `IMEM_DEPTH` / `DMEM_DEPTH` pair deserves particular attention: the synthesis
build uses deliberately small memories so that Quartus compiles quickly, while the
simulation uses the large defaults. Both the `.qsf` parameters and the `.mem` image
depth have to match, or the image and the memory it is loaded into disagree.

## 9. Regenerating the VGA console

The console layout lives in a spreadsheet, `scripts/RiscVScreenV3.xlsx`. Everything
derived from it is checked in and regenerated by:

```bash
bash scripts/gen_screen_artifacts.sh
```

That produces the video-memory images (`synthesis/*/screen.mif`), the field maps
(`synthesis/*/fields.json`) and the two screen writers
(`rtl/*/screen_writer_*.sv`). The memory images depend on the program that is loaded,
so the artifacts are regenerated whenever the program image changes — which is why
`make build` depends on them.

## 10. Where things are

| Path | Contents |
|---|---|
| `rtl/shared/` | ALU, register file, branch unit, immediate generator, CSR file, performance counters, VGA modules |
| `rtl/single_cycle/` | Single-cycle top level, control unit, program counter, combinational memories |
| `rtl/pipeline/` | Pipeline top level, control unit, inter-stage registers, hazard detection, forwarding |
| `verification/cocotb/common/` | ISA suites and instruction-level tests, shared by both architectures |
| `verification/cocotb/pipeline/` | Pipeline-specific tests: hazards, control hazards, CPI counters |
| `verification/reference_model/` | Python implementation of RV32IM, used as the golden reference |
| `synthesis/` | Quartus projects, `.tcl` flow scripts, timing constraints |
| `programs/` | CoreMark, synthetic hazard-stress programs, validation program |
| `scripts/` | ELF→`.mem` conversion, Fmax extraction, screen artifacts, report generation |
| `docs/architecture/` | Design reference for each microarchitecture and the shared modules |
| `docs/decisions/` | Architecture decision records |
| `results/` | Raw measurements and the generated reports |
