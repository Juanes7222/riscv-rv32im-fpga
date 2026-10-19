# ADR 041: Pipeline data-hazard limitation - producer 3+ cycles ahead

**Status:** Superseded by commit `06260fc` (WB-to-ID forwarding)
**Date:** 2026-06-17
**Superseded on:** 2026-06-19

**This ADR documents a pipeline deadlock that was resolved by replacing
the WB-RAW stall with WB-to-ID forwarding and restricting MEM-RAW
stalls to load instructions only. See the "Resolution" section at the
end.**

---

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
  `beq` is in `EX`. The `EX/MEM --> EX` forwarding would deliver `t6=11`.

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
is in `ID/EX` (or `IF/ID`). The `EX/MEM --> EX` forwarding doesn't help
because the `addi` is not in `EX/MEM` yet. The `MEM/WB --> EX` forwarding
delivers `t6=9` (from the earlier `addi` at `0x10`, which is in `WB`).
The `beq` compares `t5=11` (from `csrrs`) against `t6=9` (stale value) -
**not equal** - and falls through to `0x20`, `0x24`, `0x2c`, `0x30`, `0x34`,
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
instruction in `EX` is *not* the `addi` at `0x18` - it's whatever was
fetched *before* the stall began). The stall is re-asserted, `IF/ID` is
held again, the `addi` still doesn't advance. The pipeline is in a
circular dependency: the consumer cannot advance because the producer
hasn't written, and the producer cannot advance because the consumer is
holding `IF/ID`.

The fundamental problem is that the pipeline has **one slot** between `IF`
and `ID/EX`. If the consumer is in `ID` and the producer is in `IF` (1
cycle behind in program order, but many cycles behind in pipeline stages
because of the prior stall), there's no place for the producer to go.

### What a real fix would require (original analysis)

A scoreboard (or a FIFO between `IF` and `ID`):

1. **Scoreboard**: track which architectural register has a pending write
   from an uncommitted instruction. The `mem_raw`/`wb_raw` hazard is
   asserted only if the register is in the scoreboard AND the pending
   write is from the *latest* producer in program order (not just any
   producer). The original `hazard_detection_unit` checked all producers in
   `MEM` and `WB`, which was too aggressive when multiple instructions in
   the pipeline write the same register.

2. **FIFO between IF and ID**: allow multiple instructions to be in flight
   between `IF` and `ID/EX`. The consumer holds `ID`, the producer
   advances to `ID/EX`, and the FIFO absorbs the bubble. This is the
   approach used by the BOOM and XiangShan cores.

Both were considered out of scope for the original pipeline, but a simpler
fix was found.

## Decision (original)
**Document the limitation. Do not implement a fix in this ADR.**

At the time of writing, the pipeline passed:
- 4/4 pipeline smoke tests.
- 5/8 pipeline rv32m tests.
- 6/15 pipeline rv32mi tests.
- 0/37 pipeline rv32i tests.

The monocycle was unaffected: 111/111 riscv-tests passed.

## Resolution (commit `06260fc`, 2026-06-19)

The limitation was resolved by a simpler approach that does not require
a scoreboard or a FIFO:

1. **Remove the WB-RAW stall** from the hazard detection unit. Instead of
   stalling IF/ID when the producer is in WB, add a combinational mux that
   forwards `wb_rd_data` directly into the ID/EX register when the
   consumer in ID reads the same register that WB is about to write.

2. **Restrict MEM-RAW to loads only** (`mem_ru_data_wr_src == WB_MEM`).
   The original design stalled on any instruction in MEM whose destination
   matched ID's source. This caused infinite stalls for ALU→ALU RAW
   sequences (e.g., AUIPC→ADDI) because each copy of the instruction
   entering MEM re-asserted the stall against the stalled copy in ID.
   Since ALU results are available at the end of EX (before MEM), they
   are delivered via EX/MEM→EX forwarding and do not need a stall.

### Why the fix works

The deadlock described in this ADR occurred because the WB-RAW stall
held IF/ID while the producer was stuck behind the consumer. By replacing
the WB-RAW stall with forwarding, the consumer receives the correct data
immediately and no stall is needed. The producer advances through the
pipeline normally, reaching EX/MEM in time for the next consumer.

The root cause was that the stall logic was too aggressive: it stalled
for *any* RAW hazard where the producer was in MEM or WB, even when
forwarding could resolve it. The fix narrows the stall to only the cases
where forwarding cannot help (loads in MEM, where the data is not yet
available).

### Current test results

All 80 pipeline tests pass after the fix:

| Suite | Pass | Fail |
|-------|------|------|
| rv32i | 37   | 0    |
| rv32m | 8    | 0    |
| rv32mi | 15  | 0    |
| Smoke | 4    | 0    |
| Debug | 1    | 0    |
| Hazards | 7  | 0    |
| Control | 4  | 0    |
| CPI | 4      | 0    |
| **Total** | **80** | **0** |

## Consequences (resolved)
- The pipeline now runs the riscv-tests' `trap_vector` correctly.
- All 37 rv32i tests pass, including the `add.elf` test that previously
  failed in the `trap_vector`.
- The `beq`+`addi` pattern described in this ADR is handled correctly
  by WB-to-ID forwarding.
- The fix required no scoreboard or FIFO --- the simpler approach of
  replacing stalls with forwarding was sufficient.
- The pipeline is fully verified for functional correctness (80/80 tests)
  and achieves ~56.6 MHz Fmax on the Cyclone V DE1-SoC.
