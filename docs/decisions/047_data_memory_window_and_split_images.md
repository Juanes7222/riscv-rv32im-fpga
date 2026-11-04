# ADR 047 - Data memory: a 4 KB window and separate code/data images

**Status:** Accepted; the data-memory array was superseded by
[ADR 048](048_single_cycle_half_cycle_data_memory.md) (the 4 KB window and the
split images stand; the logic-cell array does not route at 1024 words)
**Date:** 2026-10-29

## Context

ADR 046 moved the single-cycle instruction memory into M10K blocks and left the
data memory as the binding constraint for CoreMark: an asynchronous array in
logic cells, instantiated with `DMEM_DEPTH = 512` (2 KB), whose read address
was hardcoded to `addr[14:2]` (13 bits) while `DMEM_DEPTH` was a parameter.

The other half of the problem was the image flow. The Makefile produced **one**
flat binary with `objcopy -O binary` and fed the same file to both memories, so
the data sections had to sit above `.text`. CoreMark's map put `.tohost` at
0x5000, `.data` at 0x6000 and the stack at 0x7000: 32 KB of address space for
2 KB of data, which no realistic logic-cell array can cover.

Two ways out were considered:

- **A - data memory in M10K with a load-use stall.** 1-cycle load latency,
  CPI = 1 + 0.1731 = 1.173 (loads are 17.31 % of CoreMark's instructions).
  Rejected: it falsifies the definition of the treatment under study
  ("ejecuta cada instrucción en un único ciclo de reloj", anteproyecto §4) and
  it changes both treatments' CPI comparison.
- **B - shrink the data image and keep the asynchronous array.** CoreMark's
  whole writable footprint is small; only the address map was wasteful.

## Decision

1. **`DMEM_DEPTH = 1024` words (4 KB) for both architectures**, in the
   `Makefile` and in `synthesis/de1soc_pins.tcl`, which is the last file both
   `setup.tcl` source: a copy in `setup.tcl` was being silently overwritten by
   the pinout file. It is the smallest depth that holds CoreMark's data image,
   and both treatments keep a homogeneous memory configuration.
2. **The word index follows the parameter.** `data_memory.sv`,
   `data_memory_pipe.sv` and `vga_mem_shadow.sv` index with
   `addr[$clog2(DEPTH)+1:2]` instead of the fixed `addr[14:2]`. The shadow must
   truncate exactly like the memory it shadows, otherwise the console and the
   CPU disagree once the depth changes.
3. **Separate images.** `scripts/elf_to_mem_split.py` replaces the flat
   `objcopy` + `elf_to_mem.py` path: the executable sections (`.text*`) build
   the instruction image at their own addresses, and **every other allocated
   section** (`.rodata*`, `.data*`, `.bss*`, `.tohost`) builds the data image
   relative to the base of the data window. `.rodata` belongs to the data
   image even though it is read-only: the program reads it with loads
   (CoreMark's `list_known_crc` / `matrix_known_crc` / `state_known_crc`
   tables live there), and the instruction memory cannot be addressed by a
   load. The splitter rejects a section that falls outside the window or
   overlaps another one. The data base is the 4 KB boundary at or below the
   lowest data section, so a program with `.tohost` at 0x708 keeps base 0 and
   needs no change. The instruction image is padded with NOPs and the data
   image with zeros.
4. **CoreMark's data window is 0x6000-0x7000** (`programs/coremark/link.ld`),
   packed with no gaps: `.tohost` at 0x6000, `.rodata` at 0x6008, `.data` at
   0x6558, `.bss` at 0x6564-0x6D48, and the stack takes the rest of the window
   (0x2B0 = 688 bytes; the call frames measure ~400 bytes). The script fails
   the link if less than 512 bytes of stack are left, and if `.bss` grows past
   the top of the window the section size becomes negative and the link fails
   as well.
5. **`MEM_METHOD = MEM_STATIC`** (`programs/coremark/core_portme.h`). The
   2 000-byte working block lives in `.bss` instead of on the stack, which
   leaves the stack with the call frames only (~400 bytes measured). The
   benchmark's behaviour and instruction mix do not change.
6. **`TOHOST_ADDR` is a build knob.** The RTL default stays `32'h708` for the
   riscv-tests and the synthetic programs; the `Makefile` exports
   `TOHOST_ADDR` (default `0x00000708`) and both `setup.tcl` and `build.tcl`
   read it. CoreMark's bitstream must be built with `TOHOST_ADDR=0x6000`,
   otherwise the console counters do not freeze at the end of the run and the
   measurement cannot be read off the board. When Quartus runs as a Windows
   binary from WSL, the variable only crosses the boundary if it is listed in
   `WSLENV`, which the `Makefile` exports for this reason.

## Rationale

**CPI stays 1.** The data memory keeps its combinational read, so the
single-cycle treatment still executes one instruction per cycle and the
comparison with the pipeline keeps its meaning.

**The 4 KB window is enough.** CoreMark's data image: `.tohost` 8 B,
`.rodata` 1 357 B, `.data` 12 B, `.bss` 20 B + 2 000 B working block = 3 400 B
with alignment, which leaves 688 B of stack (0x2B0) out of the 4 096. The call
frames measure ~400 B, so the margin is 70 %, and the linker refuses to build
if it drops below 512 B. Every one of the 60 riscv-test ELFs also fits: the
highest writable address is 0x7C8 (498 words).

**The cost was measured, not assumed.** The asynchronous array was not
implementable at 4 KB: synthesis reported 32 768 registers and 19 236 ALUTs for
the data memory alone, 79 % of the design's combinational logic, and the fitter
could not route it. [ADR 048](048_single_cycle_half_cycle_data_memory.md)
replaces the array with a half-cycle M10K read, which keeps CPI = 1 and frees
the logic cells.

## Consequences

- The single-cycle ALM total and Fmax of the October 2026 campaign are void for
  a second reason (the first was ADR 046): the data memory doubles in size. The
  five-replica protocol must be re-run.
- A depth of 8 192 words in an asynchronous array was never viable (~262 000
  flip-flops against 128 000 on the device); at 1 024 words it was not routable
  either, which is why ADR 048 moves the array into M10K.
- `scripts/elf_to_mem.py` is no longer used by the flow (it remains as a
  standalone flat-binary converter). `gen_mem_config.py`, `fpga_validate.py`,
  the `Makefile` and `verification/cocotb/common.mk` all use the splitter.
- `build/imem.mem` and `build/dmem.mem` are now different files with different
  contents. Any flow that assumed they were identical must be revisited; the
  cocotb makefile now also passes `-P<top>.IMEM_DEPTH` / `DMEM_DEPTH` so the
  simulated arrays have the depth of the images.
- The pipeline keeps its M10K data memory; only its depth and its index width
  change, and it runs the same 4 KB data window.

## Verification

- CoreMark (ITERATIONS=10) on the single-cycle at `IMEM_DEPTH = 4096`,
  `DMEM_DEPTH = 1024`: `pass`, 3 153 561 cycles, 3 153 527 instructions,
  CPI = 1.0000 (`results/benchmark_coremark_iter10_single_cycle.csv`). The
  previous flat-image build took 3 152 076 cycles; the difference (1 485) is
  the 2 KB `.bss` clear at start-up, not a change in the benchmark.
- CoreMark on the pipeline at the same depths: `pass`, 4 419 771 cycles,
  3 153 032 instructions, CPI = 1.4018
  (`results/benchmark_coremark_iter10_pipeline.csv`; the flat-image build
  measured CPI = 1.4016). The two treatments now run the same benchmark from
  the same ELF.
- The first version of the splitter sent `.rodata` to the instruction image
  only and CoreMark timed out after 4 M instructions with CPI = 1.0000: it was
  running, but its CRC verification read zeros. That is why the classification
  is "executable" versus "everything else" and not "writable" versus
  "read-only".
- `verification/cocotb/single_cycle` (48/48) and `verification/cocotb/common`
  (111/111) pass with `IMEM_DEPTH=4096`, `DMEM_DEPTH=1024`, i.e. at the
  hardware depths and with the split images.
- `scripts/elf_to_mem_split.py` reproduces the expected images for CoreMark
  (base 0x6000) and for a riscv-test (base 0x0).
