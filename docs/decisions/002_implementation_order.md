# ADR 002 — Single-Cycle Before Pipeline

**Status:** Accepted  
**Date:** 2026-04-24

## Context

The project requires two microarchitecture implementations: a single-cycle
RV32IM processor and a five-stage pipelined RV32IM processor. The order of
implementation affects debugging strategy, verification reuse, and risk
management within the undergraduate thesis timeline.

## Decision

The **single-cycle microarchitecture is implemented and fully verified first**.
The pipelined implementation begins only after the single-cycle version passes
the complete riscv-tests RV32I suite.

## Rationale

1. **The single-cycle processor serves as the correctness oracle for the
   pipeline.** Once the single-cycle design passes all riscv-tests, its
   register file and memory state after executing a program are ground truth.
   Any discrepancy in the pipeline's final state is unambiguously a pipeline
   bug, not an ISA misinterpretation.

2. **Testbenches written for the single-cycle design are reused directly for
   the pipeline.** The `verification/cocotb/common/` directory is populated
   during single-cycle development; the pipeline inherits a complete test suite
   on day one.

3. **Risk asymmetry favors early single-cycle completion.** If the timeline
   becomes constrained (see suspension criteria in the thesis document), a
   fully verified single-cycle implementation constitutes a valid partial
   result. Starting with the pipeline would leave no valid result if
   verification is not completed in time.

4. **Hazard bugs in the pipeline are the hardest to diagnose.** RAW dependency
   errors and branch flush errors manifest only under specific instruction
   sequences and are substantially easier to isolate when a known-correct
   reference exists.

## Consequences

- The experimental comparison (Objective 3 in the thesis) cannot begin until
  both implementations are verified.
- Modules in `rtl/shared/` are designed and finalized during single-cycle
  development. They must not require interface changes when the pipeline
  instantiates them.
