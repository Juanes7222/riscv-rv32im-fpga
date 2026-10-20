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

The ID/EX register holds its contents while the pipeline is stalled for a
reason other than the load-use bubble:

```systemverilog
logic id_ex_hold;
assign id_ex_hold = ex_div_busy || (stall && !load_use_hazard);
```

The IF/ID register and the ID/EX register now advance together: the IF/ID is
held only while the ID/EX is held, so an instruction can no longer be in two
stages at the same time.

Holding the ID/EX also fixes a second consequence of the same defect: the PC
unit gives the stall priority over the branch redirect, so a taken branch in
EX during a stall lost its redirect.  With the ID/EX held, the branch stays
in EX until the stall is over and its redirect is applied.

The regression test
`verification/cocotb/pipeline/test_pipeline_hazards.py::test_load_use_on_branch_executes_branch_once`
counts how many times the branch reaches the write-back stage and requires
exactly one.

## Consequences

* The pipeline executes CoreMark with the same instruction count as the
  single-cycle, which is what the CPI comparison of the anteproyecto
  requires.
* A load-use hazard whose consumer is a branch now costs two stall cycles,
  like any other load-use hazard.
* The hazard unit keeps its three outputs: `load_use` (the bubble), `stall`
  (the PC and the IF/ID) and the division stall.

## Open issue: the pipeline still differs from the single-cycle in CoreMark

With the defect above fixed the pipeline terminates CoreMark, but it does not
execute the same instruction stream as the single-cycle: the first
divergence is in `core_list_mergesort`, at the branch

```
3ec:  bgtz s0, 3cc        <- taken by the pipeline, not taken by the single-cycle
```

and at that point the registers `s0`, `s2` and `s3` already differ (the
pipeline is one node behind in the list traversal).  The four synthetic
benchmarks and the riscv-tests execute identically in both designs, so the
defect is not in the hazard logic itself.

The comparison method is documented in `docs/hardware_validation.md`: both
designs are run with the same ELF and the stream of retired program counters
is compared; the single-cycle repeats a program counter during a division
(the counter only advances when an instruction retires) and the pipeline
repeats the previous counter during the same division, so the streams have
to be compressed before they are compared.

Until the divergence is located, the CoreMark rows of
`results/results_synthetic_benchmarks.csv` are not valid measurements of the
pipeline CPI; the synthetic benchmarks are.
