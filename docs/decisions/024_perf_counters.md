# ADR 024 — Performance Counters and Measurement Infrastructure

**Status:** Accepted  
**Date:** 2026-05-04

## Context

The experimental protocol requires measuring four variables for each
microarchitecture: Fmax, effective CPI, throughput, and FPGA resource utilization. Fmax
and resource utilization are extracted from Quartus Prime synthesis reports and require no
RTL instrumentation. CPI and throughput, however, require cycle-accurate counters embedded
in the RTL itself.

Two design decisions must be taken before the first synthesis replica:

1. **Where does the counter logic live** - embedded in the datapath or in a separate module?
2. **How are counter values extracted** - and what triggers the end of measurement?

Both decisions directly affect Fmax (any logic added to the design changes the critical path)
and experimental validity (the measurement infrastructure must be identical for both
microarchitectures or the comparison is invalid).

## Decisions

**1. All performance counter logic is isolated in a dedicated module `perf_counters.sv`.**
The module is instantiated identically in both `top_single_cycle.sv` and
`top_pipeline.sv`. It receives observation signals from the datapath but has no
outputs that feed back into the datapath. It is purely a passive observer.

**2. Counter width is 32 bits.** Two counters are implemented: `cycle_count` and
`instr_retired`. Both saturate at `32'hFFFF_FFFF` rather than wrapping.

**3. `instr_retired` is defined differently per microarchitecture:**
- Single-cycle: increments when `~div_busy & ~rst_n_i` - every cycle a valid
  instruction retires (i.e., PC advanced).
- Pipeline: increments when `valid_wb` - only when a non-bubble instruction
  reaches WB.

**4. A `program_done` signal triggers counter freeze and UART transmission.**
`program_done` is asserted combinationally when `dm_wr == 1` and
`alu_res == TOHOST_ADDR` (default: `32'h8000_1000`). This is the `tohost`
convention used by riscv-tests. When `program_done` pulses, both counters
freeze and the UART TX controller serializes the results.

**5. A `uart_tx` module serializes the counter values to the host PC.**
Fixed baud rate: 115200 bps with 50 MHz clock (divisor = 434 cycles/bit).
Transmission format: `0xAA` (sync) + 4 bytes `cycle_count` + 4 bytes
`instr_retired` + `0x55` (end) = 10 bytes total.

**6. The measurement infrastructure is excluded from Fmax timing constraints.**
A Quartus SDC constraint marks `perf_counters`, `uart_tx`, and the
`program_done` combinational path as false paths relative to the processor
clock domain. This ensures the measurement logic does not inflate or deflate
the reported Fmax for either microarchitecture.

## Rationale

**Separate module for homogeneity:**
The project requires that both microarchitectures be evaluated under
"conditions as homogeneous as possible". If counter logic were embedded in the
datapath, any difference in where the counters are placed would cause different
routing pressure on the critical path, making the Fmax comparison heterogeneous.
A fully separate, passively-observed module eliminates this risk: neither architecture's
Fmax is affected by counter logic, and both use identical counter hardware.

**32-bit counters:**
At 50 MHz, a 32-bit cycle counter saturates after ~85 seconds. CoreMark requires
at least 10 seconds of execution (EEMBC, 2009); riscv-tests complete in microseconds.
32 bits is sufficient for all planned benchmarks and adds only 64 FFs (2×32) to the
design, negligible on Cyclone V.

**`instr_retired` definition:**
In the single-cycle processor, every cycle where `div_busy = 0` and the processor
is not in reset represents one retiring instruction. The definition is:
```
instr_retired_en = ~div_busy & ~reset_active
```
In the pipeline, the correct definition requires a `valid_wb` signal propagated
through the pipeline registers — a bubble inserted by the hazard unit must NOT
count as a retired instruction. This distinction is critical: if bubbles were counted,
the pipeline would appear to have CPI = 1 even under heavy hazard load, invalidating
the comparison.

**`tohost` convention:**
The riscv-tests suite signals pass/fail by writing a value to address `0x80001000`
(the `tohost` symbol in the default linker script). Detecting this write requires only
two signals already present in the datapath: `dm_wr` and `alu_res`. No modification
to any existing module is needed. This is the same convention used by lowRISC (2019)
and cocotb-based RISC-V testbenches.

**False path SDC constraint:**
Quartus Timing Analyzer reports Fmax for the worst-case combinational path between
any two registers in the clock domain. If `perf_counters` and `uart_tx` are included
in the timing analysis, a long path through the UART baud-rate divider (434-cycle
counter) could become the reported critical path — an artifact of the measurement
infrastructure, not of the processor datapath. The false path constraint removes this
artifact and ensures reported Fmax reflects only the processor itself.

## Module Interface: `perf_counters.sv`

```systemverilog
module perf_counters #(
    parameter [31:0] TOHOST_ADDR = 32'h8000_1000
) (
    input  logic        clk,
    input  logic        rst_n,

    // Single-cycle inputs
    input  logic        div_busy,       // from alu_rv32im

    // Pipeline inputs (tie to 0 in single-cycle)
    input  logic        valid_wb,       // 1 when non-bubble instruction at WB

    // Shared inputs (both microarchitectures)
    input  logic        dm_wr,          // data memory write enable
    input  logic [31:0] alu_res,        // ALU result / memory address

    // Mode selector: 0 = single-cycle, 1 = pipeline
    input  logic        pipeline_mode,

    // Outputs
    output logic [31:0] cycle_count,
    output logic [31:0] instr_retired,
    output logic        program_done    // pulses 1 cycle on tohost write
);
```

## Behavioral Contract

```
program_done = dm_wr & (alu_res == TOHOST_ADDR)   // combinational

instr_retired_en = pipeline_mode ? valid_wb
                                 : (~div_busy)     // single-cycle

On posedge clk:
  if (!rst_n):
    cycle_count   <= 0
    instr_retired <= 0
    frozen        <= 0
  else if (program_done && !frozen):
    frozen <= 1                  // latch: freeze counters
  else if (!frozen):
    cycle_count   <= cycle_count   + 1          // saturating
    instr_retired <= instr_retired + instr_retired_en  // saturating
```

## Pipeline Stall and Flush Counters (pipeline only)

For the pipeline microarchitecture, two additional counters decompose the CPI:

```systemverilog
output logic [31:0] stall_count,   // cycles where PC is stalled (data hazard)
output logic [31:0] flush_count,   // instructions flushed (control hazard)
```

These are connected to the hazard unit signals `pc_write_n` (stall) and
`if_id_flush` (flush) respectively. The decomposition enables:

$$
\text{CPI}_{\text{efectivo}} = 1 + \frac{\text{stall\_count} + \text{flush\_count}}{\text{instr\_retired}}
$$

This formula provides the qualitative analysis required by the project.
These counters are absent in `top_single_cycle` (tied to zero) and present in
`top_pipeline`.

## UART Transmission Format

| Byte | Value | Description |
|------|-------|-------------|
| 0 | `0xAA` | Sync header |
| 1–4 | `cycle_count[31:0]` | Big-endian |
| 5–8 | `instr_retired[31:0]` | Big-endian |
| 9 | `0x55` | End marker |

For the pipeline, bytes 10–13 carry `stall_count` and bytes 14–17 carry
`flush_count`, followed by `0x55`.

The host Python script (`scripts/read_results.py`) reads this frame via
`pyserial` at 115200 bps and computes CPI, IPC, and throughput.

## SDC Constraint (to be placed in `constraints/timing.sdc`)

```tcl
# Exclude measurement infrastructure from Fmax critical path
set_false_path -from [get_registers {perf_counters*}] -to [all_registers]
set_false_path -from [all_registers] -to [get_registers {perf_counters*}]
set_false_path -from [get_registers {uart_tx*}]      -to [all_registers]
set_false_path -from [all_registers] -to [get_registers {uart_tx*}]
```

## Consequences

- `perf_counters.sv` and `uart_tx.sv` must be committed before the first
  synthesis replica. Adding them after would require re-running all five
  replicas for both microarchitectures.
- The `valid_wb` signal must be designed into the pipeline register chain from
  the beginning. It is a 1-bit tag propagated alongside the instruction from
  IF to WB; bubbles carry `valid_wb = 0`.
- `program_done` is visible to cocotb testbenches. The testbench monitors
  this signal to know when to read the counter values from the DUT, replacing
  any ad-hoc end-of-simulation detection.
- The saturating behavior of counters prevents incorrect CPI values for very
  long benchmarks, at the cost of losing absolute cycle counts above ~85 s at
  50 MHz. For CoreMark (minimum 10 s), a 32-bit counter is sufficient if the
  processor runs CoreMark in under 85 s — which is expected given Fmax ~50 MHz
  and CoreMark's modest instruction count.
- The `pipeline_mode` input allows a single `perf_counters.sv` file to serve
  both microarchitectures, eliminating divergence between two separate counter
  implementations.
