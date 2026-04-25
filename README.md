# rv32im-pipeline-de1soc

Experimental comparison of single-cycle and five-stage pipelined RV32IM
microarchitectures implemented in SystemVerilog on the Intel Cyclone V DE1-SoC
FPGA. Includes functional verification via riscv-tests and cocotb testbenches,
a homogeneous measurement protocol for Fmax, effective CPI, throughput and
resource utilization, and a pipeline state visualization module designed as a
teaching aid for computer architecture courses.

> Undergraduate thesis — Ingeniería de Sistemas y Computación  
> Universidad Tecnológica de Pereira, Colombia, 2026

---

## Repository structure

```
rv32im-pipeline-de1soc/
│
├── rtl/
│   ├── single_cycle/
│   ├── pipeline/
│   └── shared/
│
├── verification/
│   ├── cocotb/
│   │   ├── single_cycle/
│   │   ├── pipeline/
│   │   └── common/
│   ├── riscv-tests/          # git submodule
│   └── reference_model/
│
├── synthesis/
│   ├── single_cycle/
│   └── pipeline/
│
├── benchmarks/
│
├── results/
│   ├── single_cycle/
│   └── pipeline/
│
├── scripts/
│
└── docs/
```

### `rtl/`

Register-transfer level source files in SystemVerilog. Organized into three
subdirectories so that modules shared between both microarchitectures are never
duplicated.

`rtl/single_cycle/` contains the top-level module and all components exclusive
to the single-cycle datapath: the combined combinational control unit and the
full-width critical-path datapath.

`rtl/pipeline/` contains the top-level module and all components exclusive to
the pipelined implementation: inter-stage registers (IF/ID, ID/EX, EX/MEM,
MEM/WB), the hazard detection unit, the forwarding unit, and branch flush
logic.

`rtl/shared/` contains modules instantiated without modification by both
microarchitectures: the ALU, the register file, instruction memory, and data
memory. Keeping shared modules here is a prerequisite of the experimental
protocol — any measured performance difference must be attributable to
microarchitecture, not to variation in secondary components.

### `verification/`

All verification artifacts. The separation between `common/` and
microarchitecture-specific subdirectories reflects the structure of the
instruction set: tests for individual RV32IM instructions apply equally to
both implementations, while hazard-specific and inter-stage signal tests are
meaningful only for the pipeline.

`verification/cocotb/common/` holds testbenches that drive the same stimulus
against both designs, including the integration with riscv-tests and comparison
against the Python reference model.

`verification/cocotb/pipeline/` holds testbenches that exercise hazard
scenarios (RAW dependencies, load-use stalls, branch flushes) and inspect
inter-stage register values — signals that do not exist in the single-cycle
design.

`verification/riscv-tests/` is a Git submodule pointing to the official
`riscv/riscv-tests` repository. Using a submodule preserves the exact commit
used during verification and allows anyone cloning the repository to reproduce
results without hunting for the correct version of the test suite.

`verification/reference_model/` contains the Python ISA model against which
both implementations are compared. It is independent of any RTL and can be
executed standalone.

### `synthesis/`

One Quartus Prime project per microarchitecture. Both projects target the same
device (`5CSEMA5F31C6`), use identical timing constraints, and are synthesized
with the same tool version. Keeping them separate prevents any configuration
from one design leaking into the other, which would invalidate the homogeneous
measurement protocol.

Generated synthesis artifacts (`.sof`, `.pof`, `db/`, `incremental_db/`,
simulation output) are excluded via `.gitignore`. Only source project files and
constraint files are versioned.

### `benchmarks/`

<!-- TODO: add CoreMark source and compilation instructions -->

Assembly and C programs used as workloads during performance evaluation.
Includes CoreMark and any representative test programs selected for the
measurement protocol. Compilation flags and linker scripts are documented here
so that all measurements are reproducible.

### `results/`

Raw data from each synthesis and execution replica — one file per
treatment/benchmark/replica combination. Processed tables and statistical
summaries are generated from these files by scripts in `scripts/` and are not
stored here. The separation ensures that analysis can be rerun without
modifying the original measurements.

### `scripts/`

Automation for the experimental protocol: launching synthesis replicas,
extracting Fmax from Quartus Timing Analyzer reports, computing CPI and
throughput from hardware counters, and producing the comparison tables used in
the thesis document. All scripts are written in Python.

### `docs/`

Technical documentation for the repository itself: block diagrams for both
microarchitectures, design decisions, signal naming conventions, and
reproduction instructions. This is not the thesis document; it is the
reference material needed to understand, extend, or reuse the implementation.

---

## Prerequisites

<!-- TODO: fill in tested versions -->

- Intel Quartus Prime (version X.X)
- ModelSim or Icarus Verilog (version X.X)
- Python 3.x with cocotb (version X.X)
- RISC-V GNU toolchain (version X.X)
- DE1-SoC board with Cyclone V 5CSEMA5F31C6

## Cloning

```bash
git clone --recurse-submodules https://github.com/Juanes7222/riscv-rv32im-fpga.git
```

The `--recurse-submodules` flag is required to initialize `riscv-tests`.

## Running verification

<!-- TODO: add commands once cocotb environment is configured -->

## Running synthesis

<!-- TODO: add Quartus batch mode commands -->

## Reproducing results

<!-- TODO: add scripts/ usage instructions -->

---

## License

<!-- TODO: choose a license -->

## Author

Juan Esteban Cardona Blandón  
Universidad Tecnológica de Pereira