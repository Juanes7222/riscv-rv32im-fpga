# ADR 041: Pipeline data-hazard limitation — producer 3+ cycles ahead

## Status
Accepted (limitation documented, no fix implemented in this ADR).

## Context
While debugging why `riscv-tests/rv32ui/add.elf` fails on the pipeline (the
program writes `tohost=0x539` = `gp | 1337` = handle_exception path, with
`gp=0`), the debug test `test_pipeline_debug_add.py` revealed a fundamental
limitation in the pipeline's forwarding + stall logic.

The riscv-tests `trap_vector` at `0x04` reads `mcause`, then compares it
against `8`, `9`, `11` in three consecutive `beq` instructions. The pattern
is:

```
0x04: csrrs t5, mcause, zero        # writes t5 = mcause
0x08: addi t6, zero, 8              # writes t6 = 8
0x0c: beq  t5, t6, write_tohost     # reads t5 (from 0x04) and t6 (from 0x08)
0x10: addi t6, zero, 9              # writes t6 = 9
0x14: beq  t5, t6, write_tohost     # reads t5 (from 0x04) and t6 (from 0x10)
0x18: addi t6, zero, 11             # writes t6 = 11
0x1c: beq  t5, t6, write_tohost     # reads t5 (from 0x04) and t6 (from 0x18)
```

### What happens on the pipeline (without any fix)

For the `beq` at `0x1c`:
- It needs `t5` (from `csrrs` at `0x04`) and `t6` (from `addi` at `0x18`).
- The `csrrs` commits after 5 cycles (IF at T+0, ID at T+1, EX at T+2,
  MEM at T+3, WB at T+4). Register-file write at the END of T+4.
- The `addi` at `0x18` is 1 cycle after the `beq` in program order. In
  normal flow (no prior stall), the `addi` would be in `EX/MEM` when the
  `beq` is in `EX`. The `EX/MEM → EX` forwarding would deliver `t6=11`.

**The actual problem** is the chain of `mem_raw`/`wb_raw` stalls from
*previous* `beq` instructions:

The `beq` at `0x0c` triggers `mem_raw` (the `csrrs` at `0x04` is in `MEM`
and writes `t5`). The stall holds `IF/ID` and `PC` for 1 cycle. But because
`csrrs` is still in `WB` (or another addi writes `t6` from `MEM`/`WB`) the
following cycle, `wb_raw` is asserted again, holding the pipeline a second
cycle. The `IF/ID` and `PC` are held for **multiple cycles**, so the
fetched instructions *behind* the stalled `beq` (the `addi t6, zero, 9` at
`0x10`, the `beq` at `0x14`, the `addi t6, zero, 11` at `0x18`) are also
held in `IF`. The `addi` at `0x18` never reaches `EX/MEM` before the
consumer `beq` at `0x1c` enters `EX`.

When the `beq` at `0x1c` finally advances to `EX`, the `addi` at `0x18`
is in `ID/EX` (or `IF/ID`). The `EX/MEM → EX` forwarding doesn't help
because the `addi` is not in `EX/MEM` yet. The `MEM/WB → EX` forwarding
delivers `t6=9` (from the earlier `addi` at `0x10`, which is in `WB`).
The `beq` compares `t5=11` (from `csrrs`) against `t6=9` (stale value) —
**not equal** — and falls through to `0x20`, `0x24`, `0x2c`, `0x30`, `0x34`,
`0x38` (handle_exception). The program writes `gp=0 | 1337 = 0x539` to
tohost, and the test reports `TESTNUM=668`.

### Why an `ex_raw` fix deadlocks

A natural fix is to also detect a RAW hazard against the producer in `EX`
(the `addi` at `0x18`) and stall the consumer (`beq` at `0x1c`) until the
producer reaches `EX/MEM`. The pipeline was modified to add `ex_raw_hazard`
to the stall calculation. The smoke tests still pass, but the riscv-tests
**time out** at 200 000 cycles with the PC stuck at `0xd4`.

The deadlock mechanism: the `ex_raw` stall holds `IF/ID` and `PC` for
2+ cycles. During those cycles, the producer (the `addi` at `0x18`) is
held in `IF` because the `IF/ID` register is held. The `addi` never reaches
`EX`. The next cycle, the `ex_raw` hazard is still asserted (the
instruction in `EX` is *not* the `addi` at `0x18` — it's whatever was
fetched *before* the stall began). The stall is re-asserted, `IF/ID` is
held again, the `addi` still doesn't advance. The pipeline is in a
circular dependency: the consumer cannot advance because the producer
hasn't written, and the producer cannot advance because the consumer is
holding `IF/ID`.

The fundamental problem is that the pipeline has **one slot** between `IF`
and `ID/EX`. If the consumer is in `ID` and the producer is in `IF` (1
cycle behind in program order, but many cycles behind in pipeline stages
because of the prior stall), there's no place for the producer to go.

### What a real fix would require

A scoreboard (or a FIFO between `IF` and `ID`):

1. **Scoreboard**: track which architectural register has a pending write
   from an uncommitted instruction. The `mem_raw`/`wb_raw` hazard is
   asserted only if the register is in the scoreboard AND the pending
   write is from the *latest* producer in program order (not just any
   producer). The current `hazard_detection_unit` checks all producers in
   `MEM` and `WB`, which is too aggressive when multiple instructions in
   the pipeline write the same register.

2. **FIFO between IF and ID**: allow multiple instructions to be in flight
   between `IF` and `ID/EX`. The consumer holds `ID`, the producer
   advances to `ID/EX`, and the FIFO absorbs the bubble. This is the
   approach used by the BOOM and XiangShan cores.

Both are out of scope for the current pipeline.

## Decision
**Document the limitation. Do not implement a fix in this ADR.**

The current pipeline passes:
- 4/4 pipeline smoke tests (`verification/cocotb/pipeline/test_pipeline_smoke.py`).
- 5/8 pipeline rv32m tests (the `MUL`/`MULH`/`MULHSU` tests pass; the
  `DIV`/`DIVU` tests fail for unrelated reasons documented in ADR 039).
- 6/15 pipeline rv32mi tests (the `EXPECTED_FAIL` tests pass; the
  `EXPECTED_PASS` tests fail for the reason documented in this ADR or
  for the reason documented in ADR 039).
- 0/37 pipeline rv32i tests, because the very first test (`add.elf`) hits
  this limitation in the `trap_vector`.

The monocycle is unaffected: it passes 111/111 riscv-tests because it has
no pipeline and no forwarding — the producer writes the register file
before the consumer reads it, by construction.

## Consequences
- The pipeline cannot run the riscv-tests' `trap_vector` correctly.
- The pipeline cannot run any program that has a `beq`/`bne` followed
  within 1–2 instructions by the producer of one of its source registers
  *and* where a prior `mem_raw`/`wb_raw` stall delayed the consumer.
- This is a known, documented limitation. Future work would address it
  with a scoreboard or a FIFO, but neither is in scope for this project.
- The pipeline is still useful for the instruction-level cocotb tests
  (smoke, ALU, branch) and for measuring Fmax and resource usage, which
  is the primary goal of the comparison with the monocycle.
