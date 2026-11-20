# RV32IM on the DE1-SoC

Two microarchitectures of the same RISC-V RV32IM processor, written in SystemVerilog
and synthesized for the Intel Cyclone V DE1-SoC board: a **single-cycle** core and a
**five-stage pipelined** core.

El repositorio compara dos diseños completos que comparten unidades funcionales,
incluido el divisor iterativo. También difieren en la organización temporal de
las memorias y en el control. La comparación utiliza el mismo dispositivo,
herramientas y programas, sin atribuir sus diferencias únicamente a insertar
registros entre etapas.

La revisión corregida del 17 de noviembre de 2026 aprobó 268 casos de regresión,
incluidos los 60 programas de `riscv-tests` por arquitectura. Se documentan sus
límites y el tratamiento de excepciones en [ADR 061](docs/decisions/061_precise_synchronous_exceptions.md).
Los resultados físicos de la revisión anterior conservan carácter histórico y
no validan este RTL. La campaña física corregida permanece pendiente.

Para preparar las cinco ejecuciones físicas por carga y arquitectura, sin
acceder a la placa, se puede ejecutar el siguiente comando desde el entorno
configurado del proyecto.

```sh
.venv/bin/python3 scripts/measure_physical_repetitions.py
```

La opción `--capture` requiere que una persona lea la consola VGA en cada
ejecución. Las 50 observaciones previstas se registran en
`results/physical_repetitions/`. Son repeticiones de ejecución del mismo
bitstream y no las cinco semillas de ubicación y enrutamiento.

## What is in the box

- **Single-cycle core** — one instruction retired per cycle; the datapath from register
  file to write-back is entirely combinational.
- **Five-stage pipeline** — IF/ID/EX/MEM/WB with data forwarding, load-use stalls and
  branch flushing, so that a new instruction starts every cycle.
- **Shared RTL** — modules that both cores instantiate without modification.
- **Verification** — the official `riscv-tests` suites (RV32I, RV32M, RV32MI) driven by
  cocotb testbenches, plus a Python ISA reference model used as a golden reference for
  differential testing.
- **VGA console** — the board's VGA output renders live internal state (PC, register
  file, per-stage signals) as a teaching aid for computer architecture courses.

## Results

<!-- TODO: insert the synthesis and CPI comparison tables here, once the final
     measurement campaign is closed. Sources:
       results/results_replicas.csv    (Fmax and resources per replica)
       results/results_benchmarks.csv   (CPI per benchmark and architecture)
       thesis/tables/                  (the tables, ready for \input)
       docs/cpi_analysis.md            (per-hazard cost breakdown)
-->

## Repository layout

```
rtl/            SystemVerilog sources
  shared/       modules used unchanged by both cores (ALU, register file, branch unit, ...)
  single_cycle/ single-cycle top level and its exclusive modules
  pipeline/     five-stage top level, inter-stage registers, hazard and forwarding units
verification/
  riscv-tests/  git submodule with the official ISA test suite
  reference_model/  Python implementation of RV32IM used as golden reference
  cocotb/       testbenches: common/ (ISA), single_cycle/, pipeline/, vga/
synthesis/      one Quartus project per architecture, plus the .tcl flow scripts
programs/       bare-metal programs: coremark/, synthetic/ (hazard stress), validate/
scripts/        Python helpers: Fmax extraction, ELF→.mem, screen artifacts, reports
results/        raw measurement data and the generated reports
thesis/         thesis-ready artifacts: tables, figures and the results chapter
docs/           architecture reference, ADRs, analysis write-ups, setup guide
```

## Quick start

Requirements: Intel Quartus Prime 25.1, Icarus Verilog, Python 3.12 with the pinned
environment in [`requirements.txt`](requirements.txt) (cocotb 2.0.1), and a
`riscv-none-elf` toolchain.

```bash
git clone --recurse-submodules https://github.com/Juanes7222/riscv-rv32im-fpga.git
cd riscv-rv32im-fpga

python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

make riscv-tests                             # build the ISA test programs
make verify-full                             # run every cocotb suite

make setup ARCH=pipeline                      # create the Quartus project
make flash ARCH=pipeline ELF=build/riscv-tests/rv32ui/add.elf   # synthesize and program
```

`make help` lists every target. The full workflow, and each configuration knob that has
to agree between the RTL, the linker scripts and the Quartus project, are documented in
[`docs/getting_started.md`](docs/getting_started.md).

## Thesis campaign

One command runs the whole experimental campaign and leaves every artifact of the
thesis ready for review:

```bash
make thesis
```

It checks the toolchain, synthesizes the five replicas of each architecture (Fmax and
resource usage per replica), runs the cocotb suites, measures the effective CPI of
every benchmark, and writes the statistics, the LaTeX tables, the pgfplots figures, the
protocol documents and the results chapter. A synthesis replica whose fingerprint does
not match the current RTL is regenerated, so the campaign is safe to re-run.

| Target | What it does |
|---|---|
| `make thesis` | Full campaign: synthesis replicas, verification, benchmarks, artifacts |
| `make thesis-quick` | Same, reusing the replicas already in `results/` |
| `make thesis-hardware` | Programs the DE1-SoC with each benchmark and prints the values the console must show, for the hardware evidence |

The artifacts land in:

| Path | Contents |
|---|---|
| `results/results_replicas.csv` | Fmax and resource usage of every replica |
| `results/results_statistics.csv` | Mean, standard deviation, CV, minimum and maximum |
| `results/results_benchmarks_summary.csv` | CPI, IPC, throughput and speedup per program |
| `thesis/tables/*.tex` | `booktabs` tables, ready for `\input` |
| `thesis/figures/diagrams/*.tex` | `pgfplots` figures |
| `docs/reproduction/*.md` | Measurement, synthesis and environment protocols |

The generator writes tables, figures and protocol documents only: the chapter
prose is written by hand around them.

## Documentation

| Document | Contents |
|---|---|
| [`docs/getting_started.md`](docs/getting_started.md) | Environment setup, full workflow, parameters to keep in sync |
| [`docs/architecture/single_cycle.md`](docs/architecture/single_cycle.md) | Single-cycle datapath, signal inventory, critical path |
| [`docs/architecture/pipeline.md`](docs/architecture/pipeline.md) | Stage-by-stage pipeline description and hazard resolution |
| [`docs/architecture/shared_modules.md`](docs/architecture/shared_modules.md) | Port-level contract of every shared module |
| [`docs/architecture/control_signals.md`](docs/architecture/control_signals.md) | Per-instruction control signal truth table |
| [`docs/decisions/`](docs/decisions/README.md) | 42 architecture decision records: why the design looks the way it does |
| [`docs/verification/`](docs/verification/plan.md) | Verification plan and reference model description |
| [`docs/cpi_analysis.md`](docs/cpi_analysis.md) | Per-hazard CPI cost and throughput comparison |
| [`docs/coremark_integration.md`](docs/coremark_integration.md) | CoreMark port, linker layout, build options |
| [`docs/vga_console_review.md`](docs/vga_console_review.md) | VGA console design, defects found and fixed |
| [`docs/vga_fmax_isolation.md`](docs/vga_fmax_isolation.md) | Keeping the VGA clock domain out of the Fmax path |

## Board

Intel DE1-SoC, Cyclone V `5CSEMA5F31C6`. The processor takes its 50 MHz clock from
`PIN_AF14`; `KEY[0]` is the active-low reset. The VGA output runs 720p60 text mode and
is driven from a 74.25 MHz PLL, declared as a false path against the processor clock.

## Attribution

Undergraduate thesis, Ingeniería de Sistemas y Computación, Universidad Tecnológica
de Pereira, Colombia, 2026. Released under the MIT license (see [`LICENSE`](LICENSE)).
