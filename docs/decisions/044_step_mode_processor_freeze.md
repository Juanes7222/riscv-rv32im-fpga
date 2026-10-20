# ADR 044: Step mode - freezing the processor for the VGA console

**Status:** Accepted
**Date:** 2026-10-20
**Related:** ADR 004 (shared module boundary), ADR 023 (register file write
inhibit during division), ADR 031 (division FSM correction), ADR 042
(counters frozen in the console)

---

## Context

The VGA console shows the state of the processor while it runs. The
processor runs at 36.7 MHz (single-cycle) or 56.6 MHz (pipeline) and the
screen refreshes at 60 Hz, so every value on the console changes about a
thousand times per second: the console cannot be read.

The console needs a way to stop the processor while the values on the
screen are inspected, and to advance it one instruction at a time.

The obvious implementation is to gate the clock with the freeze request.
That is rejected: a gated clock inserts the enable logic into the global
clock network, adds insertion delay to every flip-flop in the design and
costs Fmax. The Fmax of both designs is a measured result of this project
(36.73 MHz single-cycle, 56.60 MHz pipeline) and must not regress by more
than 1 %.

Each design already has a clock-enable mechanism that does not touch the
clock path:

* **Pipeline:** the hazard unit produces `stall`, which is the clock
  enable of the IF/ID and ID/EX registers and of the PC unit.
* **Single-cycle:** the PC holds itself while a division is in flight
  (`div_busy`), and the register file, the CSR file and the performance
  counters have write enables that are already qualified.

The freeze is therefore built on those enables.

## Decision

**The step mode is implemented with the existing clock enables of each
design. The clock is never gated.**

A new shared module, `rtl/shared/step_mode_ctrl.sv`, produces the freeze
request. Both tops instantiate it with the processor clock (not the VGA
clock) and get a `step_hold` signal, high while the processor is frozen.

* **SW[9]** (`step_mode`, active high) requests the freeze.
* **KEY[1]** (`key_step`) is the **raw** board pin, which is **active
  low** like every DE1-SoC push button: the pin is 1 while the button is
  released and 0 while it is pressed, and it is wired directly, without
  inversion. The module detects the falling edge of the synchronised pin,
  so the step fires a few clocks after the press. The exact timing is
  documented in the module header.
* One press releases the processor for **exactly one clock**: the
  instruction advances by one stage (pipeline) or one instruction
  (single-cycle), and the processor is frozen again on the next clock.

### New and changed interfaces

| Module | Change |
|--------|--------|
| `rtl/shared/step_mode_ctrl.sv` | **new module**: `clk`, `rst_n`, `key_step`, `step_mode` in, `step_hold` out |
| `rtl/shared/alu_rv32im.sv` | new input `hold`: freezes the divider FSM state |
| `rtl/single_cycle/pc.sv` | new input `step_hold`: holds the program counter |
| `top_single_cycle` | new ports `key_step`, `step_mode` |
| `top_pipeline` | new ports `key_step`, `step_mode` |

`alu_rv32im.hold` is tied to `1'b0` in the pipeline, whose behaviour stays
bit-identical to before (see the limitations below).

### How each design is frozen

**Single-cycle.** The architectural state is the program counter, the
register file, the CSRs and the performance counters:

* the PC holds itself while `step_hold` is high,
* the register file write enable, the CSR write enable and the counter
  enable are qualified with `~step_hold`,
* the divider FSM is held, so a division in flight is suspended instead
  of restarted,
* the data-memory write is left alone: a re-executed store writes the
  same value to the same address, so it is idempotent.

**Pipeline.** The freeze is OR-ed into the clock enable of every pipeline
register and of the PC unit:

* the IF/ID, ID/EX, EX/MEM and MEM/WB registers hold their contents,
* the PC unit holds the program counter,
* the flushes (branch, trap and load-use bubbles) are **suppressed**
  while the pipeline is frozen. They are combinational functions of the
  held state, so applying them would overwrite the frozen instructions
  and a taken branch would be lost. The pending flush is applied on the
  release cycle, when the pipeline advances again,
* the register file write enable, the CSR write enable and the counter
  enable are qualified with `~step_hold`.

## Rationale

* **No clock gating.** The freeze only qualifies enables that already
  exist, so the critical path of the design does not change.
* **One mechanism for both designs.** The same module produces the
  request, so the two tops cannot drift apart.
* **The divider belongs to the frozen state.** A division produces its
  result in a one-cycle `div_done` pulse. If the divider kept running
  while the processor was frozen, the pulse would be consumed inside the
  freeze and the quotient would be lost when the freeze was released.
  Holding the divider state and keeping the `div_done` indication solves
  both problems: the division is suspended rather than restarted, and the
  result reaches the register file on the release cycle.
* **The raw pin, no inversion.** The DE1-SoC push buttons are active
  low, and the tops already take the raw active-low pin for the reset
  (`rst_n` is KEY[0]). The step input follows the same convention, so the
  board wiring needs no inverter and the step fires on the press.

## Consequences

* The console can be read: the values on the screen stay still until the
  next press.
* The step-mode logic is covered by cocotb tests on the real tops:
  `verification/cocotb/single_cycle/test/test_step_mode.py` and
  `verification/cocotb/pipeline/test_pipeline_step_mode.py`.
* The pin assignment of KEY[1] and SW[9] belongs to the board flow and
  is not part of this decision.

### Known limitations

* **A division costs about 34 presses in the single-cycle.** The divider
  is suspended while the processor is frozen, and one press advances the
  processor by one clock, so a DIV needs one press per clock of its
  34-clock FSM. The result is correct and is written exactly once, but
  the user has to press 34 times to step through a division.
* **The pipeline divider is not frozen.** `alu_rv32im.hold` is tied to
  `1'b0` there, so the pipeline behaves exactly as before: the divider
  counters inside the ALU keep running while the pipeline is frozen, even
  though the pipeline state itself is stable. Freezing it as well would
  change the behaviour of the pipeline, which is out of the scope of this
  decision.
* **A press is the only way to advance.** The freeze is released for one
  clock; there is no "run until the next interesting event" mode.
