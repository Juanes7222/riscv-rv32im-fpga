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
outputs that feed back into the datapath. It is a purely passive observer.

**2. Counter width is 64 bits.**  
Two counters are implemented: `cycle_count` and `instr_retired`. Both are 64 bits
wide, matching the signal widths declared in the SignalTap II `.stp` file (ADR 026).
At 50 MHz, a 64-bit counter overflows after approximately 584 years — overflow is
unreachable for any planned benchmark. No saturation logic is implemented.

**3. `instr_retired` is defined differently per microarchitecture via a
static elaboration parameter.**  
The module is parameterized with `parameter logic PIPELINE_MODE = 1'b0`, resolved
at elaboration time. This generates distinct hardware for each top-level with no
shared multiplexer:

- Single-cycle (`PIPELINE_MODE = 0`): increments when `~div_busy`, every cycle
  in which the processor is not executing a multi-cycle divide operation.
- Pipeline (`PIPELINE_MODE = 1`): increments when `valid_wb == 1`, only when a
  non-bubble instruction commits at the WB stage. Bubbles carry `valid_wb = 0`.

**4. A `program_done` signal triggers counter freeze.**  
`program_done` is asserted combinationally when `dm_wr == 1` and
`alu_res == TOHOST_ADDR` (default: `32'h8000_1000`). This is the `tohost`
convention used by riscv-tests (lowRISC, 2019). On the first assertion of
`program_done`, a `frozen` flag latches and both counters stop incrementing.
SignalTap II (ADR 026) uses `program_done` as its capture trigger.

**5. The measurement infrastructure is excluded from Fmax timing constraints.**  
A false path SDC constraint excludes all registers in `perf_counters` from the
processor clock domain Fmax analysis, ensuring the reported Fmax reflects only
the processor datapath.

## Rationale

**Separate passive module:**  
The anteproyecto requires conditions "as homogeneous as possible". If
counter logic were embedded in the datapath, differences in placement between the
two microarchitectures would create heterogeneous routing pressure on the critical
path, invalidating the Fmax comparison. A passive observer module eliminates this
risk: neither architecture's Fmax is affected by the counter logic, and both use
identical counter hardware.

**64-bit counters without saturation:**  
At 50 MHz, CoreMark requires at least 10 seconds of execution (EEMBC, 2009).
A 64-bit counter adds only 64 additional flip-flops (negligible on Cyclone V)
and removes any need for saturation logic, which would itself introduce unnecessary
combinational paths. The 64-bit width matches the `.stp` signal configuration in
ADR 026 exactly, preventing elaboration errors at SignalTap II integration.

**Static `PIPELINE_MODE` parameter:**  
A `parameter logic PIPELINE_MODE` is resolved by the synthesizer during
elaboration, generating hardware that contains only the increment logic relevant
to each microarchitecture. A runtime `input logic pipeline_mode` signal would
instead synthesize a 2:1 multiplexer on the increment enable path, creating a
structural asymmetry between the two implementations, a violation of the
homogeneity principle.

**`instr_retired` definition per microarchitecture:**  
In the single-cycle processor, every cycle where `div_busy = 0` represents one
retiring instruction. In the pipeline, the correct definition requires a `valid_wb`
signal propagated through the pipeline registers — a bubble inserted by the hazard
unit must NOT count as a retired instruction. If bubbles were counted, the pipeline
would appear to have CPI = 1 even under heavy hazard load, invalidating the
comparison.

**`tohost` convention and registered `program_done`:**  
The riscv-tests suite signals completion by writing to address `0x80001000`
(the `tohost` symbol in the default linker script). Detecting this write requires
only two signals already present in the datapath: `dm_wr` and `alu_res`.
No modification to any existing module is needed (lowRISC, 2019).

`program_done` is implemented as a registered output rather than a combinational
signal. A registered signal guarantees that SignalTap II (ADR 026) captures a stable
value aligned to the clock edge, eliminating any risk of glitch capture on the JTAG
trigger. Because `program_done` asserts one cycle after the `tohost` write,
`cycle_count` already reflects the complete execution cycle count at capture time.
This +1 cycle offset is identical for both microarchitectures and does not affect
the comparison.

**False path SDC:**  
If `perf_counters` registers were included in timing analysis, the 64-bit counter
chains could become the reported critical path, an artifact of instrumentation,
not of the processor datapath. The false path constraint removes this artifact.

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
`instr_retired` and will not approach 2^32 in any planned benchmark.

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
