# ADR 053 — Redirect priority and explicit retirement validity

**Status:** Accepted  
**Date:** 2026-11-09

## Evidence

The first CRC-checked CoreMark run passed on the single-cycle processor but
failed on the pipeline. Instruction-by-instruction comparison located the first
control divergence after the call at PC `0x1dec` in the one-iteration ELF used
for diagnosis. A load was in MEM, a JAL in EX, and the sequential instruction in
ID consumed the load destination. The MEM-to-ID dependency held fetch even
though EX redirected control and discarded that consumer. JAL retired, but its
target was never fetched. No earlier register writeback diverged from the model.

## Decision

An EX branch/jump redirect, like a WB trap redirect, overrides the hazard of the
younger ID instruction. Step mode still holds all stages. The focused regression
combines a load, JAL, its dependent sequential instruction and a return.

Carry validity through ID/EX, EX/MEM and MEM/WB independently of instruction
encoding. Reset and flush clear validity; stalls hold it. Count program NOPs,
stores and branches, and count a held WB instruction only when it advances.

The measurement window includes the completing nonzero tohost store. Pipeline
completion occurs in WB; single-cycle completion occurs at execution. Both live
and captured counters include the completing instruction and then remain frozen.
The pipeline cycle count includes fill/drain overhead; single-cycle counting
starts after the initial synchronous fetch. Loader reset clears the counters.

CoreMark captures observed and upstream expected CRCs into a `CMV1` memory
record. Its startup reports `tohost=1` only for functional success and `3` for
failure. Internal timing remains unavailable, so these are workload rates,
not official CoreMark scores.

## Consequences

Historical counts and synthesized implementations cannot be reused as results
of this revision. Preserve them as historical evidence. Run `make verify-audit`
for full register/DMEM/count comparisons and CRC rejection checks; run the ISA
and architecture suites separately. New synthesis and physical measurements are
required before updating the performance comparison.
