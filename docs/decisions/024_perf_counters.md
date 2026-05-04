# ADR 024 — Performance Counters and Measurement Infrastructure

**Status:** Accepted  
**Date:** 2026-05-04  
**Revision:** 3 — `program_done` changed from combinational to registered output

## Context

The experimental protocol requires measuring four
variables for each microarchitecture: Fmax, effective CPI, throughput, and FPGA
resource utilization. Fmax and resource utilization are extracted from Quartus Prime
synthesis reports. CPI and throughput require cycle-accurate counters embedded in
the RTL itself.

Two decisions must be taken before the first synthesis replica:

1. **Where does the counter logic live**, embedded in the datapath or in a
   dedicated module?
2. **How are counter values made observable**, and what triggers the end of
   measurement?

Both decisions affect Fmax (any logic on the critical path changes timing) and
experimental validity (the counter infrastructure must be identical for both
microarchitectures, or the comparison is invalid).

Counter value extraction from the physical FPGA is governed by ADR 026
(SignalTap II via USB-Blaster). This ADR covers only the RTL definition of the
counters and the `program_done` signal.

## Decisions

**1. All counter logic is isolated in a dedicated module `perf_counters.sv`.**  
The module is instantiated identically in both `top_single_cycle.sv` and
`top_pipeline.sv`. It receives observation signals from the datapath but has no
outputs that feed back into the datapath. It is a purely passive observer and is
excluded from the processor’s functional behavior.

**2. Counter width is 64 bits.**  
Two counters are implemented: `cycle_count` and `instr_retired`. Both are 64 bits
wide, matching the signal widths declared in the SignalTap II `.stp` file
(ADR 026). At 50 MHz, a 64-bit counter overflows after far more cycles than any
planned benchmark will execute; overflow is unreachable and no saturation logic is
implemented.

**3. `instr_retired` is defined differently per microarchitecture via a static elaboration parameter.**  
The module is parameterized with

```systemverilog
parameter bit PIPELINE_MODE = 1'b0;
```

resolved at elaboration time. This generates distinct hardware for each top-level
with no shared multiplexer:

- **Single-cycle (`PIPELINE_MODE = 1'b0`)**: `instr_retired` increments on every
  clock cycle where `div_busy == 0`. A multi-cycle divide operation holds
  `div_busy == 1`, and those cycles are not counted as retired instructions.
- **Pipeline (`PIPELINE_MODE = 1'b1`)**: `instr_retired` increments when
  `valid_wb == 1`, i.e., only when a non-bubble instruction commits at the WB
  stage. Bubbles inserted by the hazard unit propagate `valid_wb == 0` and are
  not counted.

A `parameter bit PIPELINE_MODE` is resolved by the synthesizer during elaboration,
so only the relevant increment path is synthesized for each architecture. A runtime
`input` mode flag is explicitly rejected, as it would synthesize a multiplexer on
the increment enable path and violate the homogeneity requirement.

**4. A registered `program_done` signal triggers counter freeze.**  
`program_done` is implemented as a **registered** 1-bit output of `perf_counters.sv`,
not as a combinational expression. It is asserted on the first clock cycle in which
the core performs a data memory write (`dm_wr == 1`) to the `tohost` address
(`alu_res == TOHOST_ADDR`, default `32'h8000_1000`), following the riscv-tests
convention (lowRISC, 2019). On that cycle, a 1-bit `frozen` flag latches and both
counters stop incrementing; `program_done` remains high until reset.

Formally, the behavioral contract is:

- `cycle_count` increments by 1 on every rising edge of `clk` while `reset_n == 1`
  and `frozen == 0`.  
- `instr_retired` increments according to `PIPELINE_MODE` as described above, but
  only while `frozen == 0`.  
- `program_done` and `frozen` are reset to 0 when `reset_n == 0`.  
- On any rising edge of `clk` where `reset_n == 1`, `frozen == 0`,
  `dm_wr == 1`, and `alu_res == TOHOST_ADDR`, the module sets
  `program_done <= 1` and `frozen <= 1`.  
- Once `frozen == 1`, both counters hold their value and `program_done` stays
  asserted until the next reset.

SignalTap II (ADR 026) uses the rising edge of this registered `program_done`
as its capture trigger; no combinational version of `program_done` is exported
or tapped.

**5. The measurement infrastructure is excluded from Fmax timing constraints.**  
A false-path SDC constraint excludes all registers in `perf_counters` from the
processor clock domain Fmax analysis. The reported Fmax thus reflects only the
processor datapath and memories. The counter infrastructure is present and
identical in both microarchitectures, but it is explicitly removed from the
critical-path computation.

## Rationale

The project requires conditions “as homogeneous as possible” between the two
microarchitectures. Embedding counter logic directly in the datapath would create
architecture-specific placement and routing interactions on the critical path,
contaminating the Fmax comparison. A separate `perf_counters.sv` module that only
observes signals and never feeds back into the core guarantees that both
implementations see the same measurement overhead and that any Fmax difference is
attributable to the processor microarchitecture itself.

At the planned operating frequency (50 MHz), even the longest benchmarks (e.g.
CoreMark running for several seconds) produce cycle counts far below $2^{64}$. A 64-bit
counter adds a negligible number of registers on Cyclone V and completely removes
the need for saturation or overflow detection logic, which would otherwise
introduce extra combinational paths. Matching the 64-bit width to the SignalTap II
configuration in ADR 026 also prevents elaboration-time mismatches between RTL and
`.stp` definitions.

Using a `parameter bit PIPELINE_MODE` resolved at elaboration time lets the
synthesizer prune away unused increment logic: the single-cycle and pipeline
top-levels instantiate structurally different, but measurement-equivalent, hardware
without any runtime multiplexers on the enable path. A runtime mode input would
synthesize a 2:1 multiplexer gating the increment condition, creating a structural
asymmetry between treatments and violating the homogeneity principle of the
experimental protocol.

The notion of “retired instruction” is inherently different in a single-cycle
design from a pipelined design. In the single-cycle core, every cycle where
`div_busy == 0` corresponds to the completion of one instruction; counting those
cycles directly yields the number of retired instructions. In the pipeline, a
hazard-stall or flush cycle must not be counted, so a `valid_wb` tag propagated
through the pipeline registers is required to distinguish real commits from
bubbles. Defining `instr_retired` as “number of cycles with `valid_wb == 1`” gives
a CPI that reflects true hazard and control penalties instead of being artificially
deflated by counting bubbles as successful retirements.

Using a combinational `program_done` derived directly from `dm_wr` and `alu_res`
would expose SignalTap to narrow pulses or glitches and to potential timing
misalignments with the sampling clock. Implementing `program_done` as a registered
output that latches on the first `tohost` write and remains high until reset
ensures a single, clean rising edge synchronized to `clk`. This matches the
assumption in ADR 026, where SignalTap II is configured to trigger on the rising
edge of `program_done` and capture a single post-trigger sample. The `frozen` flag
guarantees that both counters hold their final values after that event, so
SignalTap always sees a stable snapshot of `cycle_count` and `instr_retired`.

If the counter and `program_done` logic were left on the main clock’s timing
graph, they could become part of the reported critical path, especially in the
pipeline treatment where `valid_wb` and `dm_wr` traverse multiple stages. Marking
all paths to and from `perf_counters` as false in the SDC file ensures that the
Timing Analyzer reports Fmax only for the processor datapath and memories. The
measurement infrastructure remains present and identical across treatments, but it
is explicitly removed from the Fmax optimization and reporting loop, preserving
the validity of the comparison.

## Module Interface: `perf_counters.sv`

```systemverilog
module perf_counters #(
    parameter logic   PIPELINE_MODE = 1'b0,
    parameter [31:0]  TOHOST_ADDR   = 32'h8000_1000
) (
    input  logic        clk,
    input  logic        rst_n,

    // Single-cycle input (tie to 1'b0 when PIPELINE_MODE = 1)
    input  logic        div_busy,

    // Pipeline input (tie to 1'b0 when PIPELINE_MODE = 0)
    input  logic        valid_wb,

    // Shared inputs
    input  logic        dm_wr,
    input  logic [31:0] alu_res,

    // Outputs — observed by SignalTap II (ADR 026)
    output logic [63:0] cycle_count,
    output logic [63:0] instr_retired,
    output logic        program_done
);
```

## Behavioral Contract

```
// Combinational
program_done = dm_wr & (alu_res == TOHOST_ADDR);

// Increment enable — resolved statically at elaboration
generate
  if (PIPELINE_MODE == 1'b0)
    assign instr_retired_en = ~div_busy;
  else
    assign instr_retired_en = valid_wb;
endgenerate

// Sequential
always_ff @(posedge clk or negedge rst_n) begin
  if (!rst_n) begin
    cycle_count   <= 64'h0;
    instr_retired <= 64'h0;
    frozen        <= 1'b0;
  end else if (program_done && !frozen) begin
    frozen <= 1'b1;
  end else if (!frozen) begin
    cycle_count   <= cycle_count + 64'h1;
    instr_retired <= instr_retired + {{63{1'b0}}, instr_retired_en};
  end
end
```

## Instantiation in Top-Levels

```systemverilog
// top_single_cycle.sv
perf_counters #(
    .PIPELINE_MODE (1'b0),
    .TOHOST_ADDR   (32'h8000_1000)
) u_perf (
    .clk           (clk),
    .rst_n         (rst_n),
    .div_busy      (div_busy),
    .valid_wb      (1'b0),
    .dm_wr         (dm_wr),
    .alu_res       (alu_res),
    .cycle_count   (cycle_count),
    .instr_retired (instr_retired),
    .program_done  (program_done)
);

// top_pipeline.sv
perf_counters #(
    .PIPELINE_MODE (1'b1),
    .TOHOST_ADDR   (32'h8000_1000)
) u_perf (
    .clk           (clk),
    .rst_n         (rst_n),
    .div_busy      (1'b0),
    .valid_wb      (valid_wb),
    .dm_wr         (dm_wr),
    .alu_res       (alu_res),
    .cycle_count   (cycle_count),
    .instr_retired (instr_retired),
    .program_done  (program_done)
);
```

## Pipeline Stall and Flush Counters (pipeline top-level only)

For the pipeline microarchitecture, two additional 32-bit counters are instantiated
directly in `top_pipeline.sv`, not in `perf_counters.sv`, to decompose the
CPI penalty:

```systemverilog
output logic [31:0] stall_count,   // cycles where PC is held (load-use stall)
output logic [31:0] flush_count,   // instructions flushed (branch taken)
```

Connected to hazard unit signals `pc_stall` and `if_id_flush` respectively.
These counters saturate at `32'hFFFF_FFFF`; their sum is always bounded by
`instr_retired` and will not approach $2^{32}$ in any planned benchmark.

The CPI decomposition formula is:

$$
\text{CPI}_{\text{efectivo}} = 1 + 
\frac{\text{stall\_count} + \text{flush\_count}}{\text{instr\_retired}}
$$

`stall_count` and `flush_count` are also captured by SignalTap II in the pipeline
treatment. The `.stp` file (ADR 026) includes them as additional tapped signals
for `top_pipeline` only.

## SDC Constraint (`constraints/timing.sdc`)

```tcl
# Exclude performance counter infrastructure from Fmax critical path
set_false_path -from [get_registers {*perf_counters*}] -to [all_registers]
set_false_path -from [all_registers] -to [get_registers {*perf_counters*}]
```

## Consequences

- `perf_counters.sv` must be committed before the first synthesis replica.
  Adding it afterward requires re-running all five replicas for both
  microarchitectures.
- The `valid_wb` signal must be designed into the pipeline register chain from
  the start — a 1-bit tag propagated from IF to WB; bubbles carry `valid_wb = 0`.
- `program_done` is observable by cocotb testbenches. The testbench monitors this
  signal to detect benchmark completion, replacing any ad-hoc end-of-simulation
  detection.
- The 64-bit output ports of `perf_counters` must match the signal widths declared
  in `stp/perf_capture.stp` (ADR 026). A width mismatch causes a SignalTap II
  elaboration error and serves as a consistency check during integration.
