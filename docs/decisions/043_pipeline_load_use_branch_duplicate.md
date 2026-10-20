# ADR 043: Pipeline - a load-use hazard on a branch executed the branch twice

**Status:** Accepted
**Date:** 2026-10-19
**Related:** ADR 040 (pipeline forwarding hazards), ADR 041 (pipeline
data-hazard limitation)

---

## Context

The pipeline could not run CoreMark: the simulation of `coremark.elf` never
reached the `tohost` write, while the single-cycle completed it.  Comparing
the stream of retired program counters of both designs located the first
divergence at a load followed by a conditional branch:

```
1cc8:  lh    a4, 2032(a5)
1ccc:  beqz  a4, 2028          <- executed twice by the pipeline
1cd0:  addi  t1, sp, 80
```

The minimal reproduction is two instructions:

```systemverilog
lh   a4, 0(a5)      // the load
beqz a4, +8        // the branch that consumes the load
addi x7, x7, 1
addi x8, x8, 1
```

With a non-zero loaded value the branch is not taken, and the pipeline
retired it **twice**.

### Cause

A load-use hazard costs two cycles in this pipeline:

1. The load is in EX and the consumer is in ID: `load_use_hazard` inserts a
   bubble into the ID/EX register and holds the IF/ID, so the consumer stays
   in ID while the load advances to MEM.
2. The load is in MEM and the consumer is in ID: `mem_raw_hazard` stalls the
   pipeline again, so the load reaches WB and the consumer reads the value
   from MEM/WB.

During the second stall the IF/ID register was held (the consumer stayed in
ID) but the ID/EX register kept advancing, because its hold input was wired
to `ex_div_busy` only.  The consumer was therefore copied into EX while it
stayed in ID, and it was executed a second time in the next cycle.

For an ALU consumer the duplication is invisible - the same value is written
twice, and the second execution reads the register file, which already holds
the correct value.  For a branch it is fatal: the second execution evaluates
the condition again, and the redirect it produces either duplicates the
target fetch or, with a stale operand, sends the program down the wrong
path.  The riscv-tests did not catch it because none of them puts a branch
directly behind a load.

## Decision

The MEM-RAW hazard inserts a bubble in the ID/EX register, exactly like the
load-use hazard:

```systemverilog
assign id_ex_flush = flush || load_use_hazard || mem_raw_hazard;
```

The hazard unit exposes the MEM-RAW hazard, so the two stall cycles of a
load-use sequence are handled in the same way.

Holding the ID/EX register instead of inserting a bubble looks equivalent and
is wrong: the EX/MEM register captures the contents of the EX stage at the
same clock edge, so holding the ID/EX duplicates the instruction that is in
the EX stage.  The symptom is the same class of failure - an instruction
executed twice - but it moves to the load instead of the branch.

The regression test
`verification/cocotb/pipeline/test_pipeline_hazards.py::test_load_use_on_branch_executes_branch_once`
counts how many times the branch and the load reach the write-back stage and
requires exactly one each.

## Consequences

* The pipeline executes CoreMark with the same instruction count as the
  single-cycle, which is what the CPI comparison of the anteproyecto
  requires.
* A load-use hazard whose consumer is a branch now costs two stall cycles,
  like any other load-use hazard.
* The hazard unit keeps its outputs: `load_use` and `mem_raw` (the two
  bubbles), `stall` (the PC and the IF/ID) and the division stall.

## Resolution: the CoreMark divergence

With the fix above the pipeline and the single-cycle retire the same
instructions with the same register values.

The bug was found with a comparison of the two designs on the same ELF: the
program counter and the whole register file are logged on every retirement
and the two streams are aligned by program counter.  The alignment matters,
because the pipeline holds the last instruction in the write-back stage
during the 34 cycles of a division, while the single-cycle holds the
division itself.

The comparison showed that the pipeline retired the load of the byte-swap
helper of the CoreMark list operations twice.  The duplication was the one
described above, in the instruction that was in the EX stage during the
MEM-RAW stall.
