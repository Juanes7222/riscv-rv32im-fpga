# ADR 048 - Single-cycle data memory: half-cycle M10K read

**Status:** Accepted
**Date:** 2026-11-03

## Context

ADR 047 kept the single-cycle data memory as an asynchronous array in logic
cells so that a load completes in its own cycle (CPI = 1). At
`DMEM_DEPTH = 1024` (4 KB, the window CoreMark needs) Analysis & Synthesis
reported:

```
|top_single_cycle      Combinational ALUTs 24 360   Registers 36 537
|data_memory:u_dmem    Combinational ALUTs 19 236   Registers 32 768
```

The `(* ramstyle = "M10K" *)` attribute could not be honoured: M10K has no
asynchronous read, so Quartus built the array out of 32 768 registers and
19 236 ALUTs of read multiplexers, 79 % of the design's combinational logic.
The fitter placed it, but routing did not converge: after one hour it had
routed 28 302 of 50 224 signals with 28 700 interconnect resources used by
more than one signal, reported 79 % peak interconnect usage and predicted
long run time and significant setup/hold failures. The asynchronous 4 KB
array is not implementable on the 5CSEMA5F31C6.

The alternative that keeps CPI = 1 is to give the memory the second half of
the cycle instead of the whole cycle.

## Decision

`rtl/single_cycle/data_memory.sv` is four byte-lane `M10K` arrays (one per
byte, for native byte enables and guaranteed inference) with:

- **write** on the rising edge, as before;
- **read address captured on the falling edge** (`always_ff @(negedge clk)`);
- **combinational output** of the lanes, with the half/byte selection and
  sign extension after the block, as in the pipelined memory.

The load issued in a cycle therefore has its address registered mid-cycle and
its data available before the rising edge that writes the register file, so
the instruction still completes in one clock cycle and CPI stays 1. The
pipeline is unchanged: it already reads its M10K data memory on the rising
edge and pays the load-use stall that its CPI reflects.

`synthesis/*/constraints.sdc` now also sets clock uncertainty for the
rise-to-fall and fall-to-rise transfers, so TimeQuest analyses the half-cycle
path with the same margin as the rising-edge one. The constraint is inert in
the pipeline but both files stay identical.

## Rationale

**CPI keeps its meaning.** The treatment under study is "one instruction per
cycle"; the memory implementation is free to use both edges of that cycle.
The rejected alternative (ADR 047, option A) added a load-use stall and moved
the single-cycle CPI to 1.173, which would have falsified the definition the
anteproyecto states.

**The cost moves to the clock.** The critical path now starts at the rising
edge (register file + ALU + address mux) and must end at the falling edge, a
half period, and the read path gets the other half. The design either meets
50 MHz with that split or it does not; the measured Fmax in the synthesis
campaign decides, and no claim is made here before it is measured.

**Measured result.** The half-cycle path is 5.8 ns of data delay, which is
not the limit: the critical path is the multiply writeback, a full cycle, and
the design measures 48.37 MHz (ADR 050). The processor therefore runs from
its own 40 MHz clock (ADR 049) and CPI stays 1.

**Behaviour is unchanged.** Same ports, same byte enables, same address
window, same `rd_data` encoding, same exported `dbg_wr_*` signals for the VGA
shadow. A store followed by a load to the same address still sees the stored
word, because the read address is captured after the write edge.

## Consequences

- The single-cycle data memory uses 4 M10K blocks instead of 32 768 registers;
  the logic-cell pressure that broke routing disappears.
- ADR 047's data window (0x6000-0x7000), the split image flow and the 4 KB
  depth remain valid; only the storage implementation changes.
- Every single-cycle test and the CoreMark cycle counts must be re-run: the
  first version of this memory is new logic on the load path.
- The VGA shadow is untouched; it already mirrors writes through `dbg_wr_be`
  and `dbg_wr_data`.

## Verification

- `verification/cocotb/single_cycle` and `verification/cocotb/common` at
  `IMEM_DEPTH = 4096`, `DMEM_DEPTH = 1024`.
- CoreMark (ITERATIONS = 10) on the single-cycle: expected to reproduce
  3 153 561 cycles / 3 153 527 instructions / CPI = 1.0000, since the memory
  is transparent to the instruction stream.
- Synthesis: M10K count, ALMs, Fmax and the five replicas of the campaign.
