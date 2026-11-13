# ADR 049 - Single-cycle processor clock: 40 MHz from a dedicated PLL

**Status:** Accepted (updated 2026-11-12: the Fmax figures below are marked as
the measurement of this decision's campaign)
**Date:** 2026-11-03
**Related:** ADR 048 (half-cycle data memory), ADR 050 (dedicated adder)

> **About the numbers in this ADR.** 48.37 MHz (single-cycle) and 58.74 MHz
> (pipeline) are the five-replica means of the campaign that produced this
> decision. `results/results_report.md` reports 48.48 MHz / 60.60 MHz at 85 °C
> with replica means of 49.10 / 62.15 MHz, and the comment in `cpu_pll.sv`
> quotes 46.17 MHz from an earlier run. The four numbers are not comparable:
> they come from different checkouts and, in the 46.17 case, from a partial
> recompile. Cite them by campaign and take the current figure from the
> results report. The decision itself (40 MHz, which all the figures clear with
> margin) does not depend on which number is used.

## Context

The single-cycle processor keeps CPI = 1 with a 4 KB M10K data memory whose
read address is captured on the falling edge of the processor clock (ADR
048).  Its critical path after place-and-route is the **multiply writeback**:

```
IMEM output register (M10K, registered read, ADR 046)
  --> control_unit (combinational decode)
  --> register_file (combinational read on rs1_addr)
  --> alu_rv32im (DSP multiply + result adder)
  --> writeback mux
  --> register file write data
```

That path measures 17.4 ns of data delay, which gives an **Fmax of
48.37 MHz** (slow 1100 mV 85 C, mean of five replicas:
47.58-48.79 MHz).  The 50 MHz oscillator of the board is
therefore out of reach for this microarchitecture: the multiply writeback
would need 17.4 ns inside a 20 ns period, with no margin for the clock
network, and the pipeline's own Fmax is 58.74 MHz, so the difference is the
processor, not the board.

The alternatives were: run at 50 MHz out of spec (a marginal design that
fails on the board), break CPI = 1 with a 2-cycle load (CPI 1.173, rejected
because the anteproyecto defines the single-cycle as one instruction per
cycle), or run the processor at a clock the design actually meets.

The first version of this decision was 25 MHz, on the basis of a measured
Fmax of 29.02 MHz.  That number was an artifact of the shared ALU output mux
(ADR 050): the multiplier was timed into the data memory address register
even though a load always uses the adder.  With the dedicated adder the
design reaches 48.37 MHz, so the clock was raised to 40 MHz.

## Decision

`rtl/shared/cpu_pll.sv` generates **40 MHz** from the 50 MHz oscillator
(ALTPLL, effective ratio 24/30, VCO 1200 MHz) and `top_single_cycle` uses it
as the processor clock.  Everything in the CPU domain (PC, fetch-valid
register, instruction and data memories, register file, ALU, CSR file,
performance counters, step-mode controller and the write port of the VGA
shadow) runs on that clock.  The VGA pixel PLL still takes the 50 MHz pin and
produces 74.25 MHz; the console read side is unchanged and the clock-domain
crossing stays asynchronous and declared as a false path.

The CPU also waits for the PLL to lock: `rst_n_cpu = rst_n & cpu_pll_locked`
keeps the processor in reset until the clock is stable, so a power-up that
does not press KEY[0] cannot run the program on an unlocked clock.

The pipeline is untouched: it keeps `CLOCK_50` because it meets timing there
(58.74 MHz).

At 40 MHz (25 ns period) the multiply writeback has 25 ns against 17.4 ns
of delay, an 18 % margin on the measured Fmax.

## Consequences

- The single-cycle runs CoreMark on the board at 40 MHz.  The cycle counts
  and the CPI do not change (both are clock-independent), but the wall-clock
  time is 60 % longer than at the 50 MHz the pipeline uses: CoreMark at
  `ITERATIONS = 2000` (630.7 M cycles) takes about 15.8 s instead of 12.6 s,
  still above the 10 s minimum EEMBC requires.
- Any wall-clock or CoreMark-per-second figure for the single-cycle must use
  40 MHz.  Frequency-normalised comparisons with the pipeline use CPI, which
  is unaffected.
- The SDC keeps the homogeneous 2x aggressive target: the pin is declared at
  10 ns and the derived 40 MHz clock is analysed at 12.5 ns, both half the
  real board periods (20 ns and 25 ns).  The reported Fmax therefore stays
  directly comparable with the pipeline's.
- `set proc_clocks` in both SDC files groups the pin clock with the CPU PLL
  output, so the clock uncertainty and the VGA false paths cover the new
  domain.  The pattern matches nothing in the pipeline, so both files stay
  identical.
- Simulation bypasses the PLL (`cpu_pll` output = input in the simulation
  branch): the tests verify behaviour and read CPU cycles from the performance
  counters, which do not depend on the clock period, and every testbench keeps
  driving a single clock.

## Verification

- Single-cycle cocotb suites at `IMEM_DEPTH = 4096`, `DMEM_DEPTH = 1024`:
  111 common tests plus 51 single-cycle tests, all pass. The counts are the
  `results.xml` snapshot of the moment this ADR was written.
- Synthesis: the PLL must appear at 40 MHz, the Fmax at the derived clock
  must stay around 48 MHz, and the documented margin must hold.
- CoreMark `ITERATIONS = 10` on the single-cycle: 3 153 561 cycles /
  3 153 527 instructions / CPI = 1.0000, identical to the simulation baseline,
  with the wall-clock time measured from the 40 MHz clock.
