# ADR 032: Branch Resolution in EX with Predict-Not-Taken Policy

- **Status:** Accepted
- **Date:** 2026-06-12

## Context

The five-stage RV32IM pipelined microarchitecture requires an explicit control-hazard policy. Without this decision, it is not possible to define the `pcunit` interface for the pipeline consistently, specify the behavior of the inter-stage registers under `flush` conditions, or establish a reproducible control-hazard penalty for the experimental comparison against the single-cycle implementation.

The project already established that the single-cycle processor must be completed and verified before pipeline development begins, so that the single-cycle design serves as the functional correctness oracle for the pipelined version. It also established that shared modules must preserve their interface across both microarchitectures, while the control unit, `pcunit`, inter-stage registers, and hazard-management logic belong to the pipeline-specific implementation domain. In particular, `branchunit` remains a shared module, and in the pipelined design it receives forwarded operand values without requiring any internal modification.

Because the experimental goal of the thesis is to compare throughput, Fmax, effective CPI, and resource utilization under a homogeneous protocol, branch resolution must favor structural simplicity, verifiability, and low risk of degrading the critical path of the early stages.

## Decision

Conditional branches and unconditional jumps shall be resolved in the **EX** stage of the pipeline. The default frontend policy shall be **predict-not-taken**: unless a taken control transfer is confirmed in EX, instruction fetch shall continue sequentially with `PC + 4`.

When an instruction in EX determines that a branch or jump is taken, `pcunit` shall load the branch target computed in that same stage as the next PC. In the same resolution event, the younger instructions currently in IF and ID shall be invalidated through `flush` signals applied to the corresponding pipeline registers, introducing the associated control-hazard penalty.

The branch target shall be produced by hardware already present in EX, reusing the computation performed in that stage, and no dedicated branch-target adder shall be introduced in ID for early resolution. This keeps control evaluation out of the decode-stage critical path and avoids adding branch-specific datapath logic to ID.

## Rationale

Resolving branches in EX reduces the risk of extending the critical path of ID, which in the pipelined design already performs register-file reads, immediate generation, control decode, and preparation of signals for hazard handling. Moving branch comparison and final target selection to ID would require additional logic in an early stage and would make timing closure more fragile, which is undesirable because Fmax is one of the primary response variables of the experiment.

The predict-not-taken policy is appropriate for this thesis because it provides a simple, deterministic, and academically defensible baseline for a five-stage pipeline. It also makes the control-hazard penalty directly observable in the effective CPI, without introducing the additional complexity of dynamic branch prediction or early branch resolution that would make performance attribution less clean.

This decision is also consistent with the previously established boundary between shared modules and pipeline-specific modules. It does not require any interface change to `branchunit` or to other shared components; the added complexity remains confined to `pcunit_pipeline`, the inter-stage registers, and the pipeline control/flush logic.

## Normative Specification

1. IF shall use `PC + 4` as the default next fetch address while `branch_taken_ex = 0`.
2. A branch or jump decision shall be considered valid only in EX.
3. When `branch_taken_ex = 1`, `pcunit_pipeline` shall select the target computed in EX as the next PC.
4. When `branch_taken_ex = 1`, the instructions currently in IF and ID shall be invalidated through `flush`.
5. Instruction invalidation by `flush` shall be implemented by writing an architecturally safe no-operation into the corresponding inter-stage register.
6. `flush` and `stall` are semantically distinct signals. A `stall` preserves the current contents of an inter-stage register; a `flush` explicitly invalidates them.
7. The data-hazard detection unit shall not redefine control-hazard policy; it may only request `stall` when required by data dependencies.
8. JAL and JALR shall follow the same general EX-stage resolution policy, using the target computed in that stage.

## Consequences

The taken-branch penalty shall be up to two cycles, because when a branch is resolved in EX there may already be younger instructions in IF and ID that must be discarded. This cost is accepted as part of the effective CPI of the pipelined design and shall be reported in the experimental evaluation as a direct consequence of the selected control-hazard policy.

`pcunit_pipeline` shall require explicit support for selecting between sequential flow and the taken-branch target, as well as correct interaction between `flush` and `stall`. Likewise, the IF/ID and ID/EX registers shall require explicit invalidation semantics, separate from their stall-retention behavior.

The main advantage of this decision is methodological and practical: the pipeline remains simple enough for incremental debugging, reuses the verified single-cycle design as a correctness reference, and preserves clean attribution of performance differences to controlled microarchitectural choices. The main disadvantage is the increase in effective CPI relative to earlier branch resolution, but this trade-off is acceptable within the scope and constraints of a single-student undergraduate thesis.
