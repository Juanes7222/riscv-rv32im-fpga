# ADR 050 - Dedicated adder for the load/store address and the branch target

**Status:** Accepted
**Date:** 2026-11-03
**Related:** ADR 048 (half-cycle data memory), ADR 049 (single-cycle CPU clock)

## Context

Both microarchitectures take two values from the ALU's **shared output mux**
(`alu_res`):

* the single-cycle uses it as the data memory address (loads and stores) and
  as the comparison against `tohost`;
* the pipeline uses it as the redirect target (branch and jump targets).

The mux selects between the adder, the shifter, the comparator and the four
multipliers, so its **worst timing arc is the DSP multiplier**: 7.1 ns of
multiply plus 2.9 ns of output mux, measured after place-and-route.

That arc is functionally a *don't-care* for both uses:

* a load or a store always has `alu_op = ALU_ADD`, and its address is
  `rs1 + imm`;
* a branch or a jump target is always an addition too (`pc + imm` for
  branches and `JAL`, `rs1 + imm` for `JALR`).

The Timing Analyzer cannot know that: it times every input arc of the mux into
the register that captures it, so the multiplier ended up inside the timing
path of the data memory address register and of the redirect target.

The effect was measured, with the same seeds, on the same project:

| Design | Critical path before | Fmax before | Fmax after |
|---|---|---|---|
| Single-cycle | IMEM -> decode -> register file -> **MUL** -> ALU mux -> data memory address register | 28.15-29.61 MHz (n = 5) | **47.58-48.79 MHz** (n = 5, mean 48.37) |
| Pipeline | data memory -> forwarding -> **MUL** -> ALU mux -> redirect -> IMEM -> IF/ID | 46.93-48.65 MHz (n = 5) | **57.13-60.28 MHz** (n = 5, mean 58.74) |

The pipeline lost 4 MHz against its 54.45 MHz campaign of the previous
configuration because CoreMark needs a 4096-word instruction memory and a
1024-word data memory (ADR 047), and the bigger memories added the multiplier
to its fetch path. The single-cycle lost even more: it was measured at
28-29 MHz instead of the 51.75-53.75 MHz of the previous configuration, and
the whole "the single-cycle cannot reach 50 MHz" conclusion of ADR 048 and
ADR 049 was an artifact of this don't-care arc.

## Decision

`rtl/shared/alu_rv32im.sv` exposes the adder result separately from the
output mux:

```systemverilog
output logic [31:0] alu_sum;   // always a + b
assign alu_sum = a + b;
```

* The single-cycle drives the data memory address, the `tohost` comparison,
  the console field and the VGA shadow write address with `alu_sum`.
* The pipeline drives the redirect target with `ex_alu_sum`.

The muxed `alu_res` is still what reaches the register file (the writeback
needs the multiplier result) and everything else.

## Consequences

- Functionally identical. For every instruction that can use these two
  values, `alu_op` is `ALU_ADD`, so `alu_sum == alu_res`. The divider
  override (`alu_res = div_result` while `div_busy`, `div_done_r` or
  `div_processed` is active) cannot be active at the same time: the
  single-cycle holds the fetch while `div_busy`, and the pipeline holds the
  ID/EX and EX/MEM registers, so no load, store, branch or jump is in flight
  while the divider owns the ALU output.
- The multiplier leaves the load-address and redirect paths, so the paths that
  remain are the ones that really matter: the multiply writeback in the
  single-cycle (a full cycle) and the redirect in the pipeline.
- The single-cycle now measures 48.37 MHz (mean of five replicas), which is
  still below the 50 MHz of the board oscillator, so it keeps its own 40 MHz
  clock (ADR 049). The pipeline measures 58.74 MHz and runs from `CLOCK_50`
  like before.
- The adder may be duplicated: the ALU keeps its own for the mux and the
  design adds one for `alu_sum`. The cost is at most one 32-bit adder
  (about 150 ALMs) and it disappears if Quartus shares the two.
- The verification suites (159 tests for the single-cycle, 194 for the
  pipeline) and the CoreMark runs are the regression proof: the cycle counts
  and the CPI do not change.

## Verification

- `make verify-all-sc IMEM_DEPTH=4096 DMEM_DEPTH=1024`: 111 + 48 tests pass.
- `make verify-all-pipe IMEM_DEPTH=4096 DMEM_DEPTH=1024`: 83 + 111 tests pass.
- CoreMark at `ITERATIONS = 10`: single-cycle 3 153 561 cycles /
  3 153 527 instructions / CPI = 1.0000; pipeline 4 419 771 cycles /
  3 153 032 instructions / CPI = 1.4018. Both are the same numbers as
  before the change.
- Synthesis: the single-cycle reports 48.37 MHz and the pipeline 58.74 MHz
  after place-and-route, against 28-29 MHz and 47-49 MHz before.
