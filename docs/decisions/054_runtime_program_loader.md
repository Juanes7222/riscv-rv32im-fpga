# ADR 054 - Runtime program loader: program selection with SW[3:0] and KEY[2]

**Status:** Accepted (records a feature that already exists in the RTL)
**Date:** 2026-11-12
**Depends on:** ADR 004 (shared module boundary), ADR 025 (`mem_config.vh`),
ADR 044 (step mode), ADR 046 (registered single-cycle IMEM), ADR 047 (data window)
**Related:** ADR 055 (VGA console), which displays the loaded program

---

## Context

Until the loader existed, the program executed by the FPGA was fixed at
synthesis time by `rtl/shared/mem_config.vh`: changing the benchmark meant
regenerating the `.mem` images and recompiling the bitstream (ADR 025). Showing
several programs on the board (fibonacci, ALU test, MUL/DIV test, factorial,
accumulator) required a new Quartus run each time.

The branch `feature/program-loader` adds a runtime loader so one bitstream can
run six small programs, selected from the board switches and written into both
memories while the processor is frozen. The change touches the memories and both
tops, which is exactly the kind of interface change ADR 004 says requires a new
ADR. This is that ADR.

## Decision

A shared module `rtl/shared/program_loader.sv` writes a program image into the
instruction memory and the data memory at runtime.

### Interface

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | processor clock |
| `rst_n` | in | 1 | active-low reset |
| `step_hold` | in | 1 | `1` while the processor is frozen (ADR 044) |
| `prog_sel` | in | 4 | `SW[3:0]`, the selected program |
| `key_load` | in | 1 | `KEY[2]`, raw active-low pin |
| `load_done` | out | 1 | one-cycle pulse when the copy finishes |
| `imem_wr_addr/data/en` | out | 32/32/1 | write port to the instruction memory |
| `dmem_wr_addr/data/en` | out | 32/32/1 | write port to the data memory |

Parameters `IMEM_DEPTH`, `DMEM_DEPTH` and `N_PROGS` (6) match the depth of the
memories they write.

### Behaviour

- The loader is a three-state FSM: `S_IDLE → S_COPY → S_DONE → S_IDLE`.
- A **falling edge** of the synchronised `key_load` starts the copy, and only
  when `step_hold == 1`. The user sets `SW[9]` (step mode, ADR 044), picks the
  program with `SW[3:0]` and presses `KEY[2]`. Loading while the processor runs
  is impossible by construction: the write ports share the memory with the
  fetch and the store path.
- `S_COPY` writes one word per clock to both memories, from word 0 up to the
  length of the selected image. Images shorter than the memory are not padded:
  the remainder keeps whatever the previous load left, and every stored program
  ends in a self-loop (`j .`) or an `ecall`, so execution never reaches it.
- The program contents are **constants inside the module** (`prog_imem_word` /
  `prog_dmem_word`, case on `prog_sel_q`), not `$readmemh` images. Selector 0
  is `NOP + ECALL` (halt); 1 fibonacci; 2 ALU test (RV32I); 3 MUL/DIV test
  (RV32M); 4 factorial (RV32M); 5 accumulator (RV32I). Keeping the images in
  the case avoids a second initialization format and keeps the loader
  independent of `mem_config.vh`.
- `prog_sel_q` is captured when the copy starts, so moving the switches during
  the copy does not corrupt the image.

### Changes to the memories (the interface change ADR 004 forbids without an ADR)

Both instruction memories gain a write port:

```systemverilog
input  logic        wr_en,
input  logic [31:0] wr_addr,
input  logic [31:0] wr_data
```

The write has priority over the `$readmemh` initialization load and uses the
same word index as the read.

The data memories are wired differently in the two tops:

- `rtl/single_cycle/data_memory.sv` gets a **second, dedicated write port**
  (`wr_en_loader`, `wr_addr_loader`, `wr_data_loader`) with priority over the
  CPU store. It writes all four byte lanes, so a loaded word is visible lane by
  lane like any store.
- `rtl/pipeline/data_memory_pipe.sv` keeps its single write port and the
  pipeline top muxes the loader in front of it
  (`dmem_wr_eff = mem_dm_wr | loader_dmem_wr_en`, address/data selected by
  `loader_dmem_wr_en`, `dm_ctrl_eff = 3'b100`). The memory itself does not know
  the loader exists.

### Interaction with reset, counters and the console

- The loader runs on the processor clock and on the processor reset, so a board
  reset returns it to `S_IDLE` with no pending copy.
- Because loading requires `step_hold`, the performance counters do not advance
  during the copy (their enable is qualified with `~step_hold_effective`).
- The instruction-memory shadow read by the VGA console (ADR 055) is written
  by the loader (`vga_rom_shadow.wr_en = loader_imem_wr_en`), so the console
  shows the newly loaded program. The **data**-memory shadow follows the loader
  in the pipeline (its write port is muxed with `loader_dmem_wr_en`) but only
  `dm_wr` in the single-cycle, so there a loaded data word is not mirrored
  until the program itself stores to it.

## Consequences

- One bitstream runs six programs. Changing the program no longer requires
  synthesis, only `SW[9]=1`, `SW[3:0]=program`, `KEY[2]`.
- The memory modules are no longer "frozen shared modules" in the sense of ADR
  004; ADR 004 is updated accordingly.
- `N_PROGS = 6` and the image lengths live in the RTL. Adding a program is a
  code change with a new case branch, not a data-file change.
- The loader is covered by `verification/cocotb/common/test_program_loader.py`
  and, for the pipeline, `verification/cocotb/pipeline/test_loader_executes.py`.
- The instruction-memory shadow follows the load in both designs; the
  single-cycle data shadow does not (the pipeline one does). Mirroring loaded
  data in the single-cycle would need the loader wired into `u_dmem_shadow`,
  which is not done today.
