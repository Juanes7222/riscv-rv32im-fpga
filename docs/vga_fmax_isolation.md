# VGA Fmax isolation

## Problem

The VGA text-mode visualization module shares the same FPGA die as the RISC-V
processor core. Its screen writer (`screen_writer_pipeline.sv` /
`screen_writer_sc.sv`) samples 50--267 processor signals every frame and writes
them to a character buffer (`video_memory`) on the VGA pixel clock domain
(74.25 MHz). Although the processor clock (50 MHz nominal) and the VGA pixel
clock (74.25 MHz from a PLL) are asynchronous, the Quartus Timing Analyzer was
analysing paths between the two clock domains as if they were synchronous. This
introduced false critical paths dominated by the screen writer's combinational
logic (1,186 ALUTs in the pipeline writer), which artificially limited the
reported Fmax.

### Root cause

The constraints file (`constraints.sdc`) attempted to apply `set_false_path`
between the two clock domains using a glob pattern to identify the VGA PLL
output clock:

```tcl
set vga_clk_name [get_clocks -nowarn *u_altpll*outclk*]
```

However, `derive_pll_clocks` assigns the PLL output clock a hierarchical name
that ends in `|divclk`, not `|outclk`:

```
u_vga_pll|u_altpll|auto_generated|generic_pll1~PLL_OUTPUT_COUNTER|divclk
```

The pattern `*u_altpll*outclk*` did not match `*divclk`, so `get_clocks`
returned an empty collection. The `if {[llength $vga_clk_name] > 0}` guard
silently skipped the `set_false_path` commands. The Timing Analyzer then
treated all paths between the two clock domains as synchronous, reporting
a worst-case slack of **-11.666 ns** at the 10 ns (100 MHz) target, which
corresponds to an Fmax of only **46.16 MHz**.

The Quartus compilation log confirmed the problem with these warnings:

```
Warning (332049): Ignored set_false_path at constraints.sdc(42):
  Argument <to> is an empty collection
Warning (332049): Ignored set_false_path at constraints.sdc(43):
  Argument <from> is an empty collection
```

## Solution

Correct the glob pattern to match the actual generated clock name suffix:

### Pipeline (`synthesis/pipeline/constraints.sdc`, line 33)

```tcl
# Before (no match):
set vga_clk_name [get_clocks -nowarn *u_altpll*outclk*]

# After (matches *|divclk):
set vga_clk_name [get_clocks -nowarn *u_altpll*divclk*]
```

### Single-cycle (`synthesis/single_cycle/constraints.sdc`, line 33)

```tcl
# Before (no match):
set vga_clk_name [get_clocks -nowarn *vga*pll*outclk*]

# After (matches *|divclk):
set vga_clk_name [get_clocks -nowarn *vga*pll*divclk*]
```

## Verification

After the fix, the warnings about empty collections disappeared. The
compilation log showed:

```
Info (332050): set_false_path -from [get_clocks clk] -to $vga_clk_name
Info (332050): set_false_path -from $vga_clk_name -to [get_clocks clk]
```

The remaining false paths cut approximately 1,200 ALUTs of screen-writer
combinational logic from the processor's timing analysis.

## Results

| Metric               | Before fix   | After fix    | Improvement |
|----------------------|--------------|--------------|-------------|
| Worst-case slack     | -11.666 ns   | -1.826 ns    | 9.840 ns    |
| Fmax (pipeline)      | 46.16 MHz    | 84.6 MHz     | +83 %       |
| VGA domain slack     | −27.096 ns   | +3.031 ns    | now valid   |
| False path warnings  | 4 warnings   | 0 warnings   | -           |

The remaining **-1.826 ns** slack (Fmax ~84.6 MHz) corresponds to the true
processor critical path, which is internal to the pipeline (a path from the
MEM/WB register output through forwarding logic, the ALU multiplier, PC
redirect, and instruction memory back to the IF/ID register). This is
characteristic of a 5-stage pipeline with single-cycle MUL and is well above
the 50 MHz target.

## Applicable files

- `synthesis/pipeline/constraints.sdc` - corrected clock name pattern
- `synthesis/single_cycle/constraints.sdc` - corrected clock name pattern
- `rtl/pipeline/screen_writer_pipeline.sv` - sampled signals, running on
  VGA pixel clock (74.25 MHz)
- `rtl/single_cycle/screen_writer_sc.sv` - same, for single-cycle
- `rtl/shared/vga_pll.sv` - PLL generating 74.25 MHz from 50 MHz input
