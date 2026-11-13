# ADR 004 - Boundary Between Shared and Microarchitecture-Specific Modules

**Status:** Accepted (rewritten 2026-11-12: the original table no longer matched
the tree; the memories were split by architecture and the loader/console changed
several interfaces)
**Date:** 2026-04-24
**Related:** ADR 054 (program loader), ADR 055 (VGA console), ADR 046/048
(registered instruction memory, half-cycle data memory), ADR 056 (forwarding)

## Context

The experimental protocol requires that any measured performance difference
between the two implementations be attributable to the microarchitecture, not to
differences in secondary components. That requires a precise definition of which
modules are shared verbatim, which are shared only in part, and which belong to
one design.

The first version of this ADR listed six shared modules and forbade any interface
change without a new ADR. Since then:

- the instruction and data memories were split into a single-cycle version and a
  pipeline version (ADR 046/048),
- `register_file` gained `dbg_regs` for the console (ADR 055),
- both memories gained the program loader's write port (ADR 054),
- `alu_rv32im` gained `clk`, `rst_n`, `hold` and `alu_sum` (ADR 031/044/050).

The boundary has to be described as it is, not as it was planned.

## Decision

### Shared verbatim (`rtl/shared/`, same file, same interface)

| Module | File | Why it is shareable |
|---|---|---|
| Immediate generator | `imm_gen.sv` | Purely combinational, five formats, no state |
| Branch unit | `branch_unit.sv` | Decision logic only; the pipeline feeds it forwarded operands (ADR 007) |
| CSR file | `csr_file.sv` | Same trap/CSR contract in both designs (ADR 030) |
| Step-mode controller | `step_mode_ctrl.sv` | Produces the freeze request; each top applies it (ADR 044) |
| Performance counters | `perf_counter.sv` | Passive observer, `PIPELINE_MODE` selects the increment (ADR 024) |
| Seven-segment driver | `seven_segment.sv` | Board output only |

### Shared with architecture-specific behaviour (one module, elaborated per top)

| Module | Difference |
|---|---|
| `alu_rv32im.sv` | Same arithmetic; the divider is held by `hold` in single-cycle and tied off in the pipeline; `alu_sum` feeds the address/redirect path (ADR 050) |
| `register_file.sv` | Same array; `dbg_regs` is the console's read-only view (ADR 055); x0 is forced to zero on read (ADR 016) |

### Split by architecture (different files, different interfaces)

| Single-cycle | Pipeline | Why |
|---|---|---|
| `instruction_memory.sv` | `instruction_memory_pipe.sv` | Registered read addressed with `next_pc` (ADR 046) vs. plain registered read |
| `data_memory.sv` | `data_memory_pipe.sv` | Half-cycle M10K read (ADR 048) vs. synchronous read (ADR 020) |
| `control_unit.sv` | `control_unit.sv` (pipeline) | The pipeline version propagates through stages and handles flush/trap timing |
| `pc.sv` | `pc_unit.sv` | The pipeline version takes stall and flush |
| `screen_writer_sc.sv` | `screen_writer_pipeline.sv` | Generated; the displayed fields differ per stage (ADR 055) |
| `top_single_cycle.sv` | `top_pipeline.sv` | By definition |

### Pipeline-only

`id_ex_register.sv`, `ex_mem_register.sv`, `mem_wb_register.sv`,
`hazard_detection.sv`, `forwarding_unit.sv`. `if_id_register.sv` exists but is
**not instantiated**: the IF/ID boundary is the instruction-memory output
register (ADR 057).

### Console and loader

The VGA chain (`vga_pll`, `vga_controller`, `video_memory`, `vga_text_mode`,
the two shadows) is shared hardware, but it is not part of the datapath and is
outside the Fmax comparison of the processor. `program_loader.sv` is shared and
writes into both memories while the processor is frozen (ADR 054).

## Rationale

The criterion is unchanged: a module is shared if both designs can instantiate
the same file with the same ports and the same behaviour. The memories fail that
criterion because their read protocol is the very thing that distinguishes the
two designs (a single-cycle load must complete in its own cycle; a pipeline load
may take one more). Forcing them into one parameterised module would either cost
the single-cycle its CPI or add a runtime multiplexer to both designs.

## Consequences

- A change to a shared module's interface requires a new ADR. This ADR is the one
  that records the changes from ADR 054 and ADR 055: `dbg_regs`,
  the memory write ports, `enable` on the counters and `alu_sum`/`hold` in the
  ALU.
- `docs/architecture/shared_modules.md` documents the current port lists; it is
  the reference for the tables above.
- The two memories are compared as separate implementations. Any CPI or Fmax
  difference caused by the memory protocol is attributable to the
  microarchitecture, which is exactly what the protocol wants to measure.
- The console is identical hardware in both designs, so its cost is a constant of
  the comparison rather than a treatment difference.
