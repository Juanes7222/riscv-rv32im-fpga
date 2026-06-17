# ADR 033: Canonical Bubble Instruction for Pipeline Flush and Stall Insertion

- **Status:** Accepted
- **Date:** 2026-06-12

## Context

The five-stage RV32IM pipeline requires a precise and uniform mechanism to invalidate younger instructions after control-hazard resolution and to insert bubbles when data hazards force a stall. Without a canonical bubble encoding, different parts of the design could invalidate pipeline stages in incompatible ways, leading to mismatches between RTL behavior, hazard handling, visualization logic, and verification infrastructure.

The pipeline control policy already defines that taken branches and jumps are resolved in EX and that younger instructions in IF and ID are invalidated through `flush`. The hazard-handling logic also requires bubble insertion for cases such as load-use dependencies and division-related pipeline holding behavior. These mechanisms must converge on one architecturally safe instruction encoding rather than relying on implicit or ad hoc zeroing of control signals.

Because the project includes both functional verification and a pipeline-state visualization module, the representation of an invalidated instruction must be stable, explicit, and easy to recognize both in simulation and on hardware.

## Decision

The canonical bubble instruction for the pipelined RV32IM processor shall be:

```text
32'h00000013
```

This encoding corresponds to:

```text
ADDI x0, x0, 0
```

This instruction shall be written into the relevant inter-stage register whenever the pipeline inserts a bubble or flushes an in-flight younger instruction.

The same canonical encoding shall be used consistently in all pipeline-specific contexts that require an architecturally inert instruction, including branch flushes, jump flushes, load-use bubble insertion, and any visualization or verification mechanism that needs to represent an invalid instruction slot.

## Rationale

`ADDI x0, x0, 0` is a valid RV32I instruction with architecturally null effect. It does not modify architectural state because the destination register is `x0`, whose writes are discarded by definition. It does not access data memory, does not alter control flow, does not depend on any special side-effect behavior, and remains valid independently of the current values in the register file.

Using a real ISA instruction as the bubble is safer than clearing control signals implicitly or writing an all-zero word into the instruction field without architectural interpretation. A canonical instruction allows the pipeline to preserve a uniform mental model: every stage always holds a syntactically valid instruction word, even when that word represents a bubble.

This decision also improves debuggability. When examining pipeline registers in simulation traces, waveform viewers, cocotb logs, or the on-board visualization module, `32'h00000013` can be recognized unambiguously as a bubble. That is preferable to mixed conventions such as zeroed instructions in one stage, control-signal masking in another, and stage-local invalid bits elsewhere.

## Normative Specification

1. The canonical bubble instruction shall be `32'h00000013`.
2. The semantic meaning of this encoding in the pipeline is `ADDI x0, x0, 0`.
3. When a `flush` invalidates an instruction in an inter-stage register, the instruction field of that register shall be replaced with `32'h00000013`.
4. When a hazard-handling policy inserts a bubble rather than merely holding a register with `stall`, the inserted instruction shall be `32'h00000013`.
5. `stall` and bubble insertion are not equivalent. A `stall` preserves the current contents of a register; bubble insertion overwrites the instruction field with the canonical bubble.
6. Any pipeline visualization module that renders stage contents shall display `32'h00000013` as the canonical bubble state.
7. Any testbench, checker, or trace post-processing logic that needs to recognize an inserted bubble shall use `32'h00000013` as the sole architectural bubble encoding.
8. No alternate bubble encoding shall be introduced unless a future ADR explicitly supersedes this decision.

## Consequences

The pipeline registers now have a single, unambiguous invalidation payload. This simplifies the implementation of IF/ID and ID/EX flush behavior and avoids fragmented conventions across pipeline control logic.

Verification becomes more robust because bubble insertion can be checked directly at the instruction-word level. This is particularly useful when comparing pipeline traces against the verified single-cycle design or when diagnosing incorrect control-hazard recovery.

The visualization module also benefits from this decision, because bubble states can be shown explicitly as a recognizable instruction rather than as an absence of data. The main trade-off is conceptual only: a bubble is represented as a real instruction word rather than as a separate invalid marker. That trade-off is accepted because it improves consistency, observability, and implementation simplicity.
