# ADR 024 - Performance counters: cycle and retirement counters for both microarchitectures

**Status:** Accepted, rewritten 2026-11-12 against the implemented module. The
first three revisions described a different contract (`perf_counters.sv`,
`TOHOST_ADDR` as a module parameter, a registered `program_done` and
`stall_count`/`flush_count`); none of that exists in the RTL today. Superseded in
part by ADR 042 (hardware readout), ADR 044 (counter freeze in step mode), ADR
051 (`TOHOST_ADDR` on the top) and ADR 053 (validity chain).
**Date:** 2026-05-04

---

## Context

The experimental protocol measures Fmax, effective CPI, throughput and resource
utilization for both microarchitectures. Fmax and area come from the Quartus
reports; CPI and throughput need cycle-accurate counters in the RTL, identical in
both designs so the comparison is fair.

Two questions have to be answered: where the counter logic lives, and how its
value is read out. The readout in hardware is ADR 042's problem (counters frozen
in the console); this ADR defines the RTL side.

## Decision

### 1. A dedicated, passive module

`rtl/shared/perf_counter.sv` (file name singular, module name
`perf_counters`) is instantiated in both tops. It observes the datapath and feeds
nothing back into it.

```systemverilog
module perf_counters #(
    parameter logic PIPELINE_MODE = 1'b0
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable,               // 0 freezes the counters
    input  logic        div_busy,             // single-cycle: divider in flight
    input  logic        valid_wb,             // pipeline: a real instruction commits
    input  logic        program_done_pulse,   // one-cycle pulse at the tohost store
    output logic [63:0] cycle_count,
    output logic [63:0] instr_retired,
    output logic        program_done_synced,
    output logic [63:0] cycles_at_done,
    output logic [63:0] instr_at_done
);
```

### 2. Sixty-four bits, no saturation

Both counters are 64 bits wide. At 40-50 MHz no planned benchmark approaches
2^64 cycles, so no overflow or saturation logic exists.

### 3. `instr_retired` is selected at elaboration, not at runtime

```systemverilog
generate
    if (PIPELINE_MODE == 1'b0)
        assign instr_retired_en = ~div_busy;   // one instruction per non-divide cycle
    else
        assign instr_retired_en = valid_wb;    // one instruction per commit
endgenerate
```

A runtime mode input was rejected: it would put a multiplexer on the enable path
and make the two treatments structurally different.

- **Single-cycle:** a cycle with `div_busy == 0` retires exactly one instruction.
  The 34 divider cycles are not instructions.
- **Pipeline:** `valid_wb` is the commit tag propagated through the pipeline
  registers (`ex_valid → mem_valid → wb_valid`), qualified with the divider busy
  flag in the top: `valid_wb = wb_valid && !ex_div_busy`. It must not depend on
  `wb_ru_wr`: branches and stores retire too, and requiring a register write
  halved the count (branch-stress was measured as 2003 instead of 4003) and
  inflated the pipeline CPI.

The increment is gated by the division stall. Without that, the instruction
sitting in MEM/WB during the 34-cycle divide would be counted on every cycle.

### 4. The freeze trigger is a pulse; the sticky flag lives in the top

The module receives `program_done_pulse`, asserted for one cycle when the store
to `tohost` retires. On that same edge it captures the final values:

```systemverilog
if (program_done_pulse) begin
    cycles_at_done <= cycle_count + 64'd1;                       // includes the store
    instr_at_done  <= instr_retired + {{63{1'b0}}, instr_retired_en};
end
```

and it stops incrementing. `cycles_at_done`/`instr_at_done` are the pair the
console shows (ADR 042) and the pair cocotb compares against its own count; both
include the instruction that completes the measurement, which is why the `+1`
appears only on the "at_done" copy and not on the live counter.

`program_done_synced` is the registered copy that SignalTap would use as a
trigger. It is left unconnected in both tops today, so the sticky `program_done`
that drives `HALTED` and the console lives in the top-level.

**`TOHOST_ADDR` is not a parameter of this module.** It is a parameter of
`top_single_cycle` and `top_pipeline` (default `32'h708`, ADR 051), and the top
compares `dm_addr` against it to generate `program_done_pulse` (ADR 053).

### 5. `enable` freezes both counters

`enable` is driven by the tops as `~step_hold_effective & ...` (ADR 044), so the
counters stop while the processor is frozen and do not count the power-on pause
or the tail-loop halt. The single-cycle additionally ANDs `fetch_valid`, so the
instruction-memory fill cycle is not counted and `cycle_count == instr_retired`
keeps its meaning.

### 6. There is no `stall_count` / `flush_count`

The first revision of this ADR specified two 32-bit counters in
`top_pipeline.sv` to decompose the CPI penalty, plus a false-path constraint for
`*perf_counters*` in the SDC. Neither exists: no such counters are implemented,
and `synthesis/*/constraints.sdc` contains no false path to the counters. The
CPI decomposition is done by the cocotb tests and by
`scripts/measure_benchmarks.py` from the simulation traces, not in hardware.

## Consequences

- The counters are identical in both designs and are read out through the
  console (ADR 042) or through cocotb (`test_cpi_one`,
  `test_pipeline_cpi`), never through a top-level port added for debug.
- `cycles_at_done` and `instr_at_done` are the numbers reported for the board
  runs; the live counters keep running until the freeze and are what the
  console shows while the program runs.
- The measurement is only comparable if both designs are built with the same
  `TOHOST_ADDR` and the same `enable` policy; both live in the tops, so a change
  there must be applied to both.
- Adding a CPI-decomposition counter would require reopening this ADR and
  re-running both campaigns, because it changes the measurement infrastructure.
