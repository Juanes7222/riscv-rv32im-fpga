# VGA console review — findings, fixes and verification

Scope: `rtl/shared/vga_*.sv`, `rtl/shared/video_memory.sv`, the generated
`rtl/*/screen_writer_*.sv`, the VGA wiring in both top levels, and the generator
scripts `scripts/gen_screen_mif.py` / `scripts/gen_screen_writer.py` plus their
committed artifacts (`synthesis/*/screen.mif`, `synthesis/*/fields.json`,
`rtl/pipeline/screen.mif`).

The three reported symptoms were:

1. Values that are "constantly changing / look strange".
2. Fields showing a literal `XX` instead of a real value.
3. Wrong screen size / content running off the screen.

Five independent defects were found. All five are fixed; the verification
results are at the end.

---

## Findings

### F1 — field values are assembled from 8 different instants (torn digits)

The screen writer is a round-robin character writer: one character per pixel
clock, each formatted **combinationally from the live signal**. An 8-character
hex field therefore takes 8 cycles and each digit is captured at a different
time. The displayed number is a chimera that never existed on the bus.

*Evidence*: a standalone testbench drove the writer with a `pc` that increments
every cycle. The field rendered as `00000992`, assembled from `pc` values
`0x98b … 0x992`.

The same applies between fields: character index 0 and index 110 are 110 pixel
clocks (1.5 µs) apart, i.e. ~74 executed instructions. Two fields reading the
same wire (`Address` and `ALURes`, both driven from `alu_res`) could show
different values.

### F2 — four fields show a literal `X` forever

`gen_screen_mif.py` detects dynamic placeholders by matching a label from
`LABEL_ALIASES` followed by a run of `X`. The Single-cycle sheet spells its
labels differently:

| Sheet label | In `LABEL_ALIASES`? | Result |
|---|---|---|
| `Data Write` | no — table has `DataWrite` | literal `XXXX` |
| `Data Read ` | no — table has `DataRead` | literal `XXXX` |
| `Clock cycles` | no — table has `Clockcycles` | literal `XXXX` |
| `HALTED` | no — only a *block header* name | literal `X` |

The placeholders were never recognised as slots, so they were baked into
`screen.mif` as the literal glyph `'X'` and the writer never overwrote them.
These four fields were exactly the four `X` fields visible on the monitor.

A fifth one was hidden in prose: `Executed instruction XXXXXXXX register and…`
at row 5 — the author's placeholder for the executed instruction value.

The Pipeline sheet uses `DataWrite:` / `DataRead:` (no space) and was not
affected.

### F3 — the pixel timing was not 720p60

`rtl/shared/vga_controller.sv` used a back porch of 20:

```
H_TOTAL  = 1280 + 110 + 40 + 20  = 1450
refresh = 74.25e6 / (1450 * 750) = 68.276 Hz     (want 60.000 Hz)
hsync   = 74.25e6 / 1450        = 51.206 kHz    (want 45.000 kHz)
```

With the back porch corrected to 220:

```
H_TOTAL  = 1280 + 110 + 40 + 220 = 1650
refresh = 74.25e6 / (1650 * 750) = 60.0000 Hz
hsync   = 74.25e6 / 1650        = 45.0000 kHz
```

74.25 MHz is *the* canonical 720p60 pixel clock and it only yields 60.000 Hz
with a 1650-pixel line; the front porch (110) and sync width (40) already
matched the standard `1280+110+40+220` decomposition. The back porch was a
dropped digit.

A monitor that receives 68.28 Hz / 51.2 kHz hsync does not recognise a
standard mode (there is none with 51.2 kHz hsync and 750 lines), so it
free-runs its auto-sync and scales or crops the 1280-pixel active area. That
is the reported "content cut off on both sides" picture.

### F4 — the templates did not fit the 160×45 viewport

`read_grid()` copied the worksheet into a 160×45 grid and **silently
discarded** the overflow:

| Sheet | Rows used | Cols used | Lost |
|---|---|---|---|
| Single-cycle | 50 | 161 | table bottom border, bottom ruler, column 161 |
| Pipeline | 51 | 161 | `ALUASrc`/`ALUBSrc`, the whole `Counters` box with `InstrRetired`, bottom ruler |

The Pipeline console was missing its counters panel entirely.

### F5 — asynchronous reset in the VGA controller

`vga_controller` used `always_ff @(posedge clk or posedge reset)`, which the
project rules forbid, and both top levels tied `.reset(1'b0)`. The counters
were never reset: on FPGA they power up at 0 by accident, in simulation they
start at `X` and the whole pixel path (`vmem_rd_addr → char_data → font_addr
→ font_byte → pixel_bit`) becomes `X`, making the VGA path untestable.

### F6 (latent) — out-of-range video-memory read

```systemverilog
assign vmem_rd_addr = (vga_vcount[9:4] * 11'd160) + vga_hcount[10:3];
```

The multiply was truncated to 11 bits: row 44, column 159 produced **339**
instead of 7199. Blanking also addressed rows 45/46 and columns 160…181,
outside the 7200-cell array.

---

## F7 — the register table and the memory tables were never displayed

`gen_screen_writer.py` filtered out three groups of fields:

```python
if not f['name'].startswith('x') and
   not f['name'].startswith('data_memory_') and
   not f['name'].startswith('prog._memory_')
```

So the writer never wrote the 32 register values nor the two memory tables.
Their cells were initialised by `build_mif()` with the dynamic attribute and
the character `'0'`, and nothing ever overwrote them: the console showed
`00000000` for every register and for every memory entry, forever.

### Implementation of F7

**Register table — live.** `register_file` gained a debug port with the whole
file packed (`x0` in `[31:0]` … `x31` in `[1023:992]`); the writer takes it as
one bus and formats the 256 characters of the table from it. The bus crosses
into the VGA domain through the existing false path and is snapshotted like
any other sampled signal, so a row shows one coherent value.

**Memory tables — static dump.** Neither the instruction memory nor the data
memory is inferred as a RAM (only the font ROM and the video memory are), so
they are logic-cell arrays with a big read multiplexer and there is no spare
port the console could read them through. The tables therefore show the
memory image that is loaded in the bitstream: `gen_screen_mif.py` takes the
`--imem`/`--dmem` images and writes the real word and its byte address into
the framebuffer, so `Prog. Memory` shows the program and `Data Memory` the
data memory image.

Consequence: the `.mif` now depends on the program that is loaded, so
`make build` regenerates the screen artifacts whenever the memory image
changes.

**Limitation.** The data memory table shows the image as loaded, not the
writes the program performs at run time. In this project the build loads the
whole `program.bin` into the data memory, so that table starts at the
program's text rather than at its data section (the link script places
`.data` right after `.text`, so its address depends on the program size and
cannot be a constant).

A live data memory view is not free in this architecture: neither memory is
inferred as a RAM (only the font ROM and the video memory are), so both are
logic-cell arrays with a large read multiplexer and no spare port. The
options, with their measured cost on the single-cycle design:

| Option | Cost | Shows |
|---|---|---|
| Static dump (implemented) | 0 | the image as loaded |
| Write log (32 entries of address + data) | ~4 100 registers, 384 more characters in the VGA domain | the writes, not the content |
| Second read port on the data memory | ~4 000 ALM in the single-cycle (the read multiplexer) | a live window, at a settable address |

The static dump was chosen because it is the only option that costs nothing
and because the data memory starts as a copy of the program image.

Both tables are live in the console as it is now: the program table follows
the PC of the instruction that executes and the data table the last
data-memory access, and both read shadow copies of the two memories. The
static dump above was the intermediate solution — see **Results**.

---

## Implementation

### `rtl/shared/vga_controller.sv`

- `HORIZONTAL_BACK_PORCH` 20 → 220 (1650 total, exactly 60.0000 Hz).
- Asynchronous reset → synchronous reset.

### `rtl/shared/` + both top levels — reset and address

Both tops now derive a pixel-domain reset from the system reset through a
two-flop synchroniser, and drive it to the controller and the writer:

```systemverilog
always_ff @(posedge vga_pixel_clk) begin
    vga_rst_sync <= {vga_rst_sync[0], ~rst_n};
end
assign vga_rst = vga_rst_sync[1];
```

The read address is computed in 14 bits and folded back into the array when
blanking leaves it:

```systemverilog
assign vmem_char_addr = ({8'd0, vga_vcount[9:4]} * 14'd160) + {6'd0, vga_hcount[10:3]};
assign vmem_rd_addr = (vmem_char_addr >= 14'd7200) ? 13'd0 : vmem_char_addr[12:0];
```

### `scripts/gen_screen_writer.py` — snapshot bank (fixes F1)

The generated writer now samples every displayed signal into a register bank
that is loaded **once per sweep**, and formats every character from that bank:

```systemverilog
always_ff @(posedge clk) begin
    if (!rst_n) begin
        char_ctr <= '0;
        snap_pc  <= '0;
        ...
    end else begin
        char_ctr <= (char_ctr == N_CHARS - 1) ? '0 : char_ctr + 1'b1;
        // Load the bank at the end of a sweep, so the next sweep renders
        // every character from the same captured instant.
        if (char_ctr == N_CHARS - 1) begin
            snap_pc <= pc;
            ...
        end
    end
end
```

Loading at the *end* of the previous sweep keeps every character of a sweep on
one snapshot, so the whole screen describes a single machine state.

The generator also gives each slot its own address constant when a signal
feeds more than one slot (`ADDR_INSTRUCTION` and `ADDR_INSTRUCTION_663`), and
`hex_digit()`/`bin_digit()` now take a 64-bit value so 64-bit counters are no
longer truncated to 32 bits.

### `scripts/gen_screen_mif.py` — alias table and viewport guard (fixes F2, F4)

New aliases: `Data Write`, `Data Read`, `Clock cycles`, `HALTED`,
`Executed instruction`. New catalogue entry: `halted` (1 bit, binary).

`read_grid()` now **fails loudly** when a cell falls outside the viewport
instead of truncating it:

```
ERROR: Cell (row 46, col 1) = "|" lies outside the 160x45 viewport. The
template must fit the 720p60 text screen exactly; trim it or the content is
lost.
```

### `scripts/trim_screen_templates.py` — the template trim

A one-shot script that trims `scripts/RiscVScreenV3.xlsx` to 160×45. It is
idempotent from the pristine template in git.

*Single-cycle*: the prose block and the three tables move up one row so the
table's closing border lands on the last visible row; the `Clock cycles` box
moves up one row and widens from 8 to 16 characters for the 64-bit counter;
rows 46-50 and column 161 are cleared.

*Pipeline*: the `EXECUTE` box loses its separator and its blank row, the
`MEM/WB` box loses its separator (the arrow row stays aligned with the `ALURes`
row), the `Counters` box shrinks to three rows; rows 46-51 and column 161 are
cleared.

### `scripts/gen_screen_artifacts.sh`

Regenerates every checked-in artifact from the template in one command
(`screen.mif` ×3, `fields.json` ×2, `screen_writer_*.sv` ×2) and normalises
the line endings to CRLF like the rest of the repository.

### `synthesis/*/constraints.sdc`

The pixel-domain reset synchroniser samples the system reset asynchronously,
like every other cross-domain signal:

```tcl
set_false_path -from [get_ports {rst_n}] -to $vga_clk_name
```

### `verification/vga/`

`tb_screen_writer_snapshot.sv` + `Makefile` — regression test for the
snapshot bank (see below).

### Build harness (`Makefile`, `synthesis/*/program.tcl`)

Found while validating the change on hardware:

- **The build target could never fail.** The recipe ended with an `echo`
  after a `;`, so `make` always returned 0 even if Quartus had failed — a
  broken build looked like a successful one and the stale bitstream would be
  programmed. A shared `quartus_compile` macro now runs the flow, propagates
  the exit code and checks that the `.sof` was actually regenerated.

  The artifact check, not only the exit code, is deliberate: Quartus Lite
  crashes with an access violation while the fitter process tears down its
  Tcl interpreter, *after* the fit has succeeded and written every output.
  The flow engine absorbs the crash, so a plain exit-code check would
  already be enough, but the artifact check also catches a flow that
  silently skipped a stage.

- `SHELL := /bin/bash`: `SECONDS` is a bash builtin, so the elapsed time was
  always reported as `0 seconds`.

- `synthesis/pipeline/program.tcl` was missing, so `make program
  ARCH=pipeline` could not work. Added (it is project-agnostic: it derives
  the project name from the `.qpf`).

- `program.tcl` now lists the JTAG chain (`quartus_pgm -c <cable> -a`)
  before programming and reports a clear hint when the scan fails, so a
  board/cable problem is not confused with a bitstream problem.

### Warning noise

The generated screen writer produced 155 `Warning (10230)` (implicit
truncations) per build: the address constants were `localparam int` (32
bits) and the digit helpers masked a 64-bit shift down to 4 bits. The
constants are now `localparam logic [12:0]` and the helpers use an explicit
64-bit temporary, which keeps the same hardware with 26 warnings instead
of 182.

### The writer is split in small round-robin groups

Adding the 256 characters of the register table took the pipeline writer to
541 characters, and the character multiplexer no longer fitted in the
13.5 ns period of the pixel clock: the VGA domain went from +3.0 ns to
**−2.3 ns** of setup slack.

The writer therefore runs several round-robin groups that rotate, one
character per cycle:

```systemverilog
grp_ctr <= (grp_ctr == N_GROUPS - 1) ? '0 : grp_ctr + 1'b1;
case (grp_ctr)
    GRP_PROC:  begin ctr_proc  <= ...; end
    GRP_PROC1: begin ctr_proc1 <= ...; end
    GRP_REGS:  begin ctr_regs  <= ...; end
    ...
endcase
```

Each group has its own counter and its own snapshot load, so the coherence
guarantee is unchanged: within a group the characters of a sweep still come
from a single captured instant. The groups are built by
`gen_screen_writer.py` with at most 128 characters each, which keeps every
character multiplexer local.

### The register table is written in two pipeline stages

Splitting the groups was not enough: the register table alone is a
multiplexer over 256 sources (one per character, each reading a different
nibble of the 32 register values), and that mux is deeper than the pixel
clock allows. Its group is therefore written in two stages:

```systemverilog
// stage 1: select the register row (a multiplexer over 32 rows)
reg_value <= snap_reg_values[32*ctr_regs[7:3] +: 32];
reg_addr  <= REG_ADDR[13*ctr_regs[7:3] +: 13];
reg_col   <= ctr_regs[2:0];

// stage 2: the character inside that row
wr_addr = reg_addr + {10'd0, reg_col};
wr_data = hex_digit(reg_value, 7 - reg_col);
```

Stage 1 selects one of the 32 rows and stage 2 one of the 8 characters of
it, so neither multiplexer has more than 32 inputs. The eight characters of
a register still come from the same captured value, because stage 2 formats
all of them from the same `reg_value` register.

---

## Verification

| Check | Result |
|---|---|
| Frame length | counters return to 0 after exactly 1650 × 750 = 1 237 500 pixel clocks → **60.0000 Hz** at 74.25 MHz |
| Read address | maximum address over a full frame = **7199** (= row 44, col 159); no access outside the array |
| Coherence | `verification/vga` test: the 8 characters of the PC field decode to one captured instant → **PASS** |
| Register table | `verification/vga` test: the x0 row shows the pattern loaded in the register bus → **PASS** |
| Memory tables | the `.mif` carries the real words and byte addresses of the loaded image (`0004: 34202f73`) |
| Unbound placeholders | after regeneration, no `X`/`B` glyph remains in either `screen.mif` except the letters of the labels themselves (`X0`…`X31`, `EX_PC`, `BROp`, …) |
| Single-cycle cocotb | **45/45 PASS** |
| Pipeline cocotb | **80/80 PASS** (run the two suites one at a time: they both regenerate `rtl/shared/mem_config.vh`) |
| Icarus elaboration | both designs elaborate without errors |
| Quartus (single-cycle) | 0 errors, 27 warnings, 11 620 ALM (36 %) |
| Quartus (pipeline) | 0 errors, 30 warnings, 2 343 ALM (7 %) |
| Domain `clk` slack @85 °C | −13,980 ns (single-cycle), −8,357 ns (pipeline) |
| Domain VGA slack @85 °C | **+0,493 ns** (single-cycle), **+0,273 ns** (pipeline) — positive in the four corners |

The figures of this table are the state before the console rework; the rework
and what it costs are recorded in **Results**.

The Fmax isolation of `docs/vga_fmax_isolation.md` is preserved: the sampled
signals still reach the VGA domain only through the false-pathed crossing, and
the snapshot registers actually shorten the VGA-domain encoder path.

---

## Results

The sections above describe the console as it was found: the reported
symptoms, the defects behind them and the fixes for them. This section
records the console as it is now — what it shows, what it costs and what it
still cannot do.

### What the console shows now

**The colour system.** The video-memory cell was already 16 bits wide — an
attribute byte and a character byte — and the writer threw the attribute
away. The attribute is now the palette index of the cell: four bits of
foreground and four of background, so 16 foreground and 16 background
colours, shared by the whole screen (`rtl/shared/vga_text_mode.sv`). The
colours of the template survive the compilation: `gen_screen_mif.py` maps
every colour of the workbook to a palette index — including the colours the
workbook takes from its OOXML theme (`read_theme_colors()`) — and writes the
result into the attribute byte of the cell.

**The semantic colours.** A field whose meaning depends on a signal lights
up while the signal is asserted: a stall, a load-use hazard, a flush, a
data-memory write or a taken branch changes the attribute of its field
(`FIELD_SEMANTICS` in `gen_screen_mif.py`). The instruction in flight is the
brightest thing on the screen (white on black).

**The stage boxes and the flow arrows.** Every character of a stage-box
header and of a flow arrow is a rewrite field whose background follows the
stage it belongs to, so the boxes and the arrows show where the instruction
is (`tb_stage_highlight.sv`).

**The two live memory tables.** The program table follows the PC of the
instruction that executes, the data table the address of the last
data-memory access; each draws a window of 32 rows, and the marked row is
prefixed with a `>`. The window stays where it is while the followed word
remains inside it and re-centres on that word when it leaves the range, so
the listing does not drift under the reader. Both read the shadow copies of
the two memories, so they show what the processor sees and not the image
that was loaded in the bitstream.

**The decoding panel.** A rectangle of the screen decodes the instruction in
flight: the word, the mnemonic, the register numbers and the immediate. The
fields that a format does not have show a placeholder (`--`) instead of the
immediate bits that occupy the field in the encoding (`tb_vga_panel.sv`).

### The measured cost

Quartus 25.1, at the build depths the versioned `synthesis/*/setup.tcl` sets
(IMEM 2048 / DMEM 512):

| | before | after |
|---|---|---|
| pipeline Fmax (clk) | 52.97 MHz | 52.10 MHz (-1.6 %) |
| pipeline ALM | 4 146 / 32 070 (13 %) | 4 625 / 32 070 (14 %) |
| pipeline M10K | 16 / 397 (4 %) | 35 / 397 (9 %) |
| pipeline VGA domain | 145.56 MHz | 127.08 MHz |
| single-cycle Fmax (clk) | 36.13 MHz | 37.86 MHz (+4.8 %) |
| single-cycle ALM | 13 878 / 32 070 (43 %) | 13 880 / 32 070 (43 %) |
| single-cycle M10K | 12 / 397 (3 %) | 31 / 397 (8 %) |
| single-cycle VGA domain | 161.34 MHz | 132.91 MHz |

Two figures of this table must not be read at face value:

- **The VGA domain must reach 74.25 MHz**, and it does with room to spare:
  the achievable period of the pixel clock is 7.87 ns in the pipeline and
  7.52 ns in the single-cycle, against the 13.47 ns the 720p60 mode needs
  (+5.6 ns and +5.9 ns of margin). The negative setup slack the Timing
  Analyzer prints for that clock is an artefact of the SDC, which models the
  derived pixel clock at half its real period (6.734 ns, i.e. 148.5 MHz,
  instead of 13.47 ns; the derived clock inherits the deliberately
  aggressive target the SDC sets on `clk`). The same artefact is in the
  "before" figures.
- **The M10K blocks are the shadow copies.** Both designs grow by 19 blocks
  (16 → 35 in the pipeline, 12 → 31 in the single-cycle): the data shadow
  (four byte lanes) and the program shadow (the ROM), plus the video
  memory, which now needs its full 16-bit width because the attribute byte
  is read; it used to be pruned to 8 bits.

The "before" column is the main tree's own builds of the same sources
without this work. The "after" column was measured on the pipeline at the
state after the program shadow's out-of-range NOP was removed (commit
`75742a9`), and on the single-cycle at the state before the last three
commits (`50abe69`, `f6c488d`, `59c9412`), which change the formatting of
the panel's fields, the index expression of the data shadow and the
out-of-range behaviour of the program shadow, and therefore move no
resource of the single-cycle: its figures are not expected to move.

The program shadow's out-of-range NOP was measured to break the M10K
inference of that ROM — 35 blocks / 4 588 ALM / 52.82 MHz with the NOP
removed, against 28 blocks / 4 835 ALM / 50.21 MHz with it — so it was
removed: the processor's Fmax matters more than a display-only corner case
(a fetch beyond the program image shows an aliased word where the CPU
executes a NOP).

**The -1.6 % of the pipeline is not a clean result.** The same design
measured 52.82 MHz before the last three commits and 52.10 MHz after them,
against a baseline of 52.97 MHz. The critical path of that design runs
from the data memory's RAM through the ALU's multiplier to the PC redirect,
so its length depends on the placement, and a small design edit moves it
by about this much. The project's own measurement protocol quotes
56.61 ± 1.88 MHz for the pipeline across five replicas, so a swing of
this order is inside the protocol's own uncertainty: the console rework
does not demonstrably slow the processor, and the five-replica protocol on
the merged branch is the reference measurement.

### The step mode

`SW[9]` freezes the processor and `KEY[1]` releases it for exactly one
clock. The freeze is built on the clock-enable mechanism each design already
has — the hazard unit's `stall` in the pipeline, the qualified write enables
and the held PC in the single-cycle — and never gates the clock: gating it
would put the enable logic in the global clock network and cost Fmax in both
designs.

One press of `KEY[1]` therefore advances the pipeline by one stage, and the
single-cycle design by one instruction. In the single-cycle design the
divider is suspended while the processor is frozen, so a division is resumed
instead of restarted: it costs one press per clock cycle of the divider's
state machine.

### Residual limitations

- The panel decodes the raw instruction fields, so the immediates are zero
  extended and a negative branch offset appears as a large positive value.
  The fields that a format does not have show a placeholder.
- The console is a snapshot view: the whole screen is rendered from one
  captured instant, but in free-running mode the values change far faster
  than a human can read them. The step mode is what makes the console
  readable.
- The data shadow mirrors the CPU's memory by taking the CPU's own index
  slice, so an access beyond the configured depth is dropped by both in
  simulation and truncated by both in synthesis.

### Pin assignments

The step mode adds two top-level inputs to both designs, `key_step` and
`step_mode`. The DE1-SoC pin file has to assign them to **KEY[1] =
PIN_AA15** and **SW[9] = PIN_AE12**; until that assignment exists, the
build reports the two ports as unassigned ("Missing location assignment")
and the mode is not operable on the board.

---

## Residual risks

- **Clock domain crossing.** The writer samples processor signals in the
  74.25 MHz domain with no synchroniser; `constraints.sdc` declares the
  crossing as a false path. The snapshot reduces the exposure from *eight
  independent samples per field* to *one sample per sweep*, but a multi-bit
  value can still be captured mid-transition. The architecturally clean fix is
  to capture the bank in the processor domain and hand it over with a
  toggle/handshake; that contradicts the existing decision to keep the writer
  in the VGA domain (`docs/vga_fmax_isolation.md`) and needs SDC rework.
- **Monitor lock.** The 60.000 Hz / 45 kHz figures are exact by construction,
  but the monitor's auto-sync behaviour has to be confirmed on hardware.
- **Template.** The trimmed layout is a mechanical transformation of the
  original. The bottom ruler of both sheets was dropped (it duplicated the
  top rulers, which already label every 10th column) and the `Counters` box
  of the Pipeline sheet lost its bottom border.
