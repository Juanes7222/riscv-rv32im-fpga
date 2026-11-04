# ADR 051 - The tohost address parameter reaches Quartus in decimal

**Status:** Accepted
**Date:** 2026-11-03
**Related:** ADR 042 (hardware measurement without SignalTap), ADR 047 (split
memory images), ADR 024 (performance counters), ADR 026 (metric extraction)

## Context

The RTL freezes the counters and raises `program_done` when a store writes 1 to
`TOHOST_ADDR`, a SystemVerilog parameter of both top-levels:

```systemverilog
parameter logic [31:0] TOHOST_ADDR = 32'h708
```

The synthesis flow overrides it from the environment, because CoreMark places
its `tohost` at `0x6000` (ADR 047):

```tcl
set tohost_addr $::env(TOHOST_ADDR)      ;# "0x6000"
set_parameter -name TOHOST_ADDR $tohost_addr
```

Quartus reports the parameter as **Untyped** and takes the value as a plain
number. It does **not** parse the `0x` form, so the string `0x6000` reached the
netlist as **0**: the synthesized comparator was `alu_sum == 0`, never
`alu_sum == 0x6000`.

Evidence, from a three-line project whose only output is `(K == 32'h6000)`:

| `set_parameter -name K ...` | Synthesized output |
|-----------------------------|--------------------|
| `0x6000`                    | `assign o = gnd`   |
| `24576`                     | `assign o = vcc`   |
| `32'h6000`                  | `assign o = gnd`   |

On the board this looked like: CoreMark runs to completion, the console shows
`PC = 0x44` (the final `j 3b` of `start.S`) and the instruction `0000006f`, but
`HALTED` stays 0 and `CyclesToPass` / `InstrToPass` stay 0 forever — the store
to `0x6000` executes, the comparison against `0` does not match, and the
counters are never latched.

The simulation did not catch it: cocotb ran the DUT with the RTL default
(`0x708`) and the CoreMark run only emitted the "program tohost differs from the
RTL freeze address" warning instead of the equality assertion (ADR 024). The
pulse path had therefore never been exercised with a non-default address.

## Decision

1. `build.tcl` (both architectures), `build_fpga.tcl` and `de1soc_pins.tcl` pass
   the parameter through `[expr {...}]`, which reads the `0x` form and hands
   Quartus a decimal:

   ```tcl
   set_parameter -name TOHOST_ADDR [expr {$tohost_addr}]
   ```

2. `scripts/fpga_validate.py` reads the `tohost` symbol of the ELF under test
   and passes it to both the DUT parameter and the test's expectation
   (`TOHOST_ADDR=<hex>` to make, `VALIDATION_TOHOST_ADDR` in the environment),
   so the frozen-counter path is verified in simulation for every program, and
   the `cycles_at_done == cycle_count` assertion actually runs for CoreMark.
   `common.mk` turns the value into the decimal `-P` argument iverilog needs.

## Consequences

* Every bitstream built before this decision that used `TOHOST_ADDR=0x6000`
  has a dead `program_done`: its on-board counters cannot be trusted.
  Bitstreams that used the default (`0x708`) are unaffected, because the
  default is a Verilog literal in the RTL and the environment only overrides it
  when set.
* The measurement protocol must be re-run for the CoreMark bitstreams of both
  architectures.  With the fixed bitstream the single-cycle console reports
  `HALTED = 1`, `CyclesToPass = 0x25689C64` (627 612 772) and
  `InstrToPass = 0x25689C42` (627 612 738) for 2000 iterations, that is
  CPI = 1.0000001 in 15.69 s at 40 MHz; the pipeline reports
  `0x34725683` (879 908 483) and `0x25689A57` (627 612 247), CPI = 1.4020 in
  17.60 s at 50 MHz (`docs/hardware_validation.md` §7).
* Quartus gives no warning when it discards the `0x` prefix. Any other
  `set_parameter` added later with a hex literal has the same trap; use
  decimal or an `int` parameter.
