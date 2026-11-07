# ADR 052 - Single-cycle fetch waits for the power-on pause to lift

**Status:** Accepted
**Date:** 2026-11-07
**Related:** ADR 044 (step mode), ADR 024 (performance counters),
ADR 042 (hardware measurement without SignalTap)

## Context

The single-cycle top holds the processor for four CPU clocks after reset
(`power_on_pause`) so the VGA console can render before the first instruction
runs.  The hold reaches the PC, the register write gate, the divisor and the
counter enable, but the `fetch_valid` register was set to 1 unconditionally
one clock after reset:

```systemverilog
always_ff @(posedge clk_cpu) begin
    if (!rst_n_cpu) fetch_valid <= 1'b0;
    else            fetch_valid <= 1'b1;
end
```

Consequence on the board (the pause exists only outside `SIMULATION`):

```
c0  pc=0  fetch_valid=0  pause=1  imem captures address 0
c1  pc=0  fetch_valid=1  pause=1  imem now captures next_pc = 4
c4  pc=0  fetch_valid=1  pause=0  first executed word is the one at 4
```

The word at the reset vector is never fetched, so the first instruction of
every program is skipped.  Synthetic programs whose loop counter is set by the
second instruction were unaffected; `branch_stress.S` sets its loop counter
with the first instruction (`li x1, 1000`), so `x1` stayed 0, `addi x1, x1, -1`
underflowed and the loop ran 2^32 times:

```
4 x 2^32 + 4 = 17 179 869 188 = 0x4_0000_0004
```

which at 40 MHz is 429 s.  That is the value the single-cycle console
reported for `branch_stress` (`results/hardware_single_cycle_branch_stress.csv`)
instead of the cocotb 4004.

The pipeline is not affected: its `fetch_valid` is already conditioned on
`!pipe_stall`.

## Decision

`fetch_valid` is also gated by the freeze, so the instruction memory captures
the reset vector during the whole pause and the processor starts with
instruction 0:

```systemverilog
always_ff @(posedge clk_cpu) begin
    if (!rst_n_cpu)                fetch_valid <= 1'b0;
    else if (!step_hold_effective) fetch_valid <= 1'b1;
end
```

`pc.sv` already holds while `!fetch_valid` or `step_hold`, so no other module
changes.

## Consequences

* The board and the simulation now agree for every program: `branch_stress`
  reports 4004 cycles and 4004 instructions on the single-cycle console
  (`0xFA4`), matching the simulator.
* Measurements taken on single-cycle bitstreams built before this ADR are off
  by one skipped instruction per run: every program that depended on its
  first instruction produced a wrong result, and `branch_stress` produced a
  value dominated by the 2^32-iteration loop.  Those runs must be repeated.
* Step mode is unchanged in practice: a processor frozen before its first
  fetch now waits for the first release cycle to fill the instruction memory,
  which is the same one-fill behaviour the pipeline has.
* Verified by the single-cycle cocotb suite (51 architecture tests, 111
  shared instruction tests, step-mode tests included) and by simulating the
  hardware branch (`power_on_pause` enabled) with the real
  `branch_stress.elf` image.
