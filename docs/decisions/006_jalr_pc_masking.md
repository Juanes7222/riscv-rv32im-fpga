# ADR 006 — JALR LSB Masking Assigned to branch_unit

**Status:** Accepted  
**Date:** 2026-04-24

## Context

The RISC-V specification requires that for JALR, the least-significant bit of
the computed jump target is forced to zero before loading it into the PC:

```
PC = (rs1 + I_immediate) & ~1
```

The ALU computes `rs1 + I_immediate` correctly. Without explicit masking, the
resulting PC value may have bit 0 set, causing misaligned instruction fetch
and undefined behavior.

No existing module in the design applies this masking. The question is where to
assign this responsibility.

## Decision

The `branch_unit` module is extended with an additional output `mask_pc_lsb`.
This signal is asserted (`1'b1`) exclusively when `branch_type == BR_TYPE_JALR`
and de-asserted (`1'b0`) in all other cases.

The NextPC mux in the datapath applies the mask conditionally:

```systemverilog
logic [31:0] branch_target;
assign branch_target = mask_pc_lsb ? {alu_res[31:1], 1'b0} : alu_res;
assign next_pc = branch ? branch_target : pc_plus4;
```

## Rationale

The `branch_unit` is the only module that knows the instruction type at the
point where the PC decision is made. Placing the masking signal here keeps all
jump-and-link-register behavior in one module. Alternatives considered:

- **Mask inside the ALU:** The ALU has no knowledge of whether its result is
  used as a PC. Adding this would couple the ALU to PC semantics.
- **Mask in the NextPC mux directly from a control signal:** Requires an
  additional signal from the control unit, duplicating information already
  present in `br_op`.

## Consequences

- `branch_unit.sv` gains one output port: `output logic mask_pc_lsb`.
- The top-level module and the pipeline's PC unit must route this signal to the
  NextPC mux.
- The `mask_pc_lsb` signal is only meaningful when `branch == 1'b1`; its value
  when `branch == 1'b0` is irrelevant and can be left as combinational default.
