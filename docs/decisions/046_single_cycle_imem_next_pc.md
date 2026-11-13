# ADR 046 - Single-cycle instruction memory: registered read addressed with next_pc

**Status:** Accepted (updated 2026-11-12: test count, the loader write port and
the data-memory paragraph)
**Date:** 2026-10-28

## Context

ADR 011 gave the single-cycle processor an asynchronous (combinational)
instruction memory because the instruction has to be available in the same
cycle in which the PC presents its address. Quartus cannot place a
combinational read in an M10K block, so the array is built from logic cells
and its cost grows with the program size.

That cost is the reason the single-cycle cannot run CoreMark. The binary's
`.text` + `.rodata` ends at ~0x28F5 (10.5 KB, 2 622 words), while the synthesis
flow instantiates `IMEM_DEPTH = 2048` (8 KB) in `synthesis/single_cycle/setup.tcl`
and in the `Makefile`. Raising the depth in logic cells is not viable: at the
cost measured for the asynchronous data memory (8 969 ALMs for 512 words) a
4 096-word array would exceed the 32 070 ALMs of the 5CSEMA5F31C6.

ADR 011 §4 states that converting the single-cycle to a synchronous read "is
not feasible" because it would add a cycle to every fetch. That reasoning
assumes the address presented to the memory must be the *current* PC. It does
not have to be.

The single-cycle campaign of October 2026 was also measured with a
twelve-instruction image (`build/program.bin`, 48 bytes): Quartus folded the
2 048-word array down to 35 ALUTs, so the reported Fmax (52.92 MHz, n = 5) and
the ALM total (11 438) do not contain a realistic instruction memory.

## Decision

`rtl/single_cycle/instruction_memory.sv` performs a **registered read** and is
addressed with the **next PC**:

```systemverilog
always_ff @(posedge clk)
    if (fetch_en) mem_q <= mem[word_index];   // word_index from next_pc
```

- The array's own address register becomes the IF/ID boundary: the word read
  with `next_pc` at the end of cycle N is the instruction of cycle N+1, already
  available when it is executed.
- `pc.sv` exports `next_pc` (it already computed it) and keeps its own PC
  register: AUIPC, the JAL/JALR link value, the branch base, `mepc` and the
  console all need the PC of the *executing* instruction.
- `fetch_en = ~div_busy & ~step_hold` holds the output register during the
  34-cycle divider and during step mode, so the instruction stays aligned with
  the frozen PC.
- One fill cycle follows reset (`fetch_valid`). While it lasts the processor
  executes a NOP and the PC stays at the reset vector; the cycle is excluded
  from `perf_counters.enable` so the `cycle_count == instr_retired` invariant
  keeps its meaning.
- The out-of-range NOP mux sits after the output register, otherwise Quartus
  does not infer the block (same reason documented in `vga_rom_shadow.sv`).
- The array gained the program loader's write port (`wr_en`, `wr_addr`,
  `wr_data`) after this decision; it has priority over the `$readmemh` load and
  is only enabled while the CPU is frozen (ADR 054).
- `IMEM_DEPTH` is raised to 4096 (16 KB) in `Makefile` and in both
  `synthesis/*/setup.tcl`. The pipeline needs the same depth to run the same
  binary, and its instruction memory is already an M10K block RAM, so the two
  architectures stay homogeneous in memory configuration.

## Rationale

**No bubble, no CPI cost.** The branch/jump target is resolved combinationally
in the same cycle (the ALU already produces it for `pc.sv`), so the address
captured at the edge is correct even for a taken branch or a JALR. The
instruction fetch of N+1 overlaps the execution of N without adding a stage
that anyone has to wait for: CPI stays 1.

**The array moves to M10K.** 4 096 words x 32 bits = 131 072 bits = 13 M10K
blocks of the 397 available (the device has 4 065 280 bits, and the design
already uses 229 888 bits for the VGA console).

**Timing becomes content-independent.** An M10K read costs the same whatever
the program contains, so the Fmax no longer depends on how many distinct
instructions the image has. This is what makes the homogeneous measurement
protocol defensible for the single-cycle.

## Consequences

- `instruction_memory` has `clk` and `fetch_en` ports; the async-ROM
  configuration note in `docs/reproduction/synthesis_protocol.md` no longer
  applies to it.
- ADR 011 §3 and §4 are superseded by this record: the single-cycle memory is
  no longer a logic-cell async ROM of 2048 words, it is a registered M10K read
  of 4096 words. ADR 011 §1-2 stay valid as the statement of the
  asynchronous-read problem, and the pipeline memory keeps the synchronous read
  ADR 011 described.
- The instruction-level cocotb tests assume the instruction is available in the
  cycle the PC presents its address. They now call `prime_fetch()` after
  depositing the program, before the instruction step (ADR 034 pattern).
- The single-cycle Fmax and ALM figures of the October 2026 campaign must be
  regenerated: the IMEM leaves the logic cells and enters the M10K blocks, and
  the critical path changes (the PC clock-to-out plus LUT-ROM read leaves it,
  the next-PC mux and the M10K address setup enter it). The direction of the
  change is not assumed here; it is measured with the standard five replicas.
- **The data memory is no longer the binding constraint.** ADR 048 replaced the
  asynchronous word array with four byte-lane M10K arrays read on the falling
  half-cycle and raised the window to `DMEM_DEPTH = 1024` words (ADR 047). The
  paragraph that closed this ADR originally (async array of 512 words, 8 969
  ALMs, CoreMark's `.tohost` at 0x5000 outside the array) described the state
  before ADR 048 and is kept here only as the reason that decision was made.

## Verification

`verification/cocotb/single_cycle` (Icarus, 51 tests: 37 RV32I + 8 RV32M CPI
tests, 3 step-mode tests, 3 loader tests) and `verification/cocotb/common`
(111 tests: RV32I, RV32M, RV32MI, ALU, branch unit, model-vs-DUT) pass with the
registered read. The counts are the ones in the current `results.xml`; they are
snapshot values, not a contract.
The DIV tests exercise the `fetch_en` hold; the JALR and branch tests exercise
the next-PC address path.
