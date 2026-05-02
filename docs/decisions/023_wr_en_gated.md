# ADR 023 — Register File Write Inhibit During Division (wr_en_gated)

**Status:** Accepted (updated 2026-05-02 — uses div_done instead of div_busy gate)  
**Date:** 2026-05-02

## Context

In the single-cycle datapath, the control unit asserts `ru_wr = 1` for all
R-type instructions, including DIV/DIVU/REM/REMU. Without intervention, the
register file write port is enabled from the first cycle of a division, when
`alu_res = div_result` is undefined. The correct write must occur exactly once:
on the cycle when `div_result` holds the final correct value.

`div_busy` alone cannot gate the write because it is high during both
`DIV_RUNNING` (result not ready) and `DIV_DONE` (result ready). The correct
gating signal is `div_done` — a 1-cycle pulse from `alu_rv32im` that fires
exactly when the result is valid (see [ADR 019](019_alu_rv32im.md)).

## Decision

`top_single_cycle.sv` introduces a combinational signal `wr_en_gated` that
replaces `ru_wr` as the write enable input to `register_file`:

```systemverilog
logic is_div;
logic wr_en_gated;

assign is_div      = (alu_op inside {ALU_DIV, ALU_DIVU, ALU_REM, ALU_REMU});
assign wr_en_gated = ru_wr & (~is_div | div_done);
```

`wr_en_gated` is the only signal that changes relative to the original
datapath. All other connections are unchanged.

## Rationale

**Cycle-by-cycle analysis — normal division (CPI = 34):**

| Cycle | `div_state` | `is_div` | `div_done` | `~is_div \| div_done` | `wr_en_gated` | Action |
|-------|------------|----------|------------|----------------------|---------------|--------|
| 1 (issue) | IDLE | 1 | 0 | 0 | 0 | ✅ Inhibited — result not ready |
| 2–33 (RUNNING) | RUNNING | 1 | 0 | 0 | 0 | ✅ Inhibited — result not ready |
| 34 (DONE) | DONE | 1 | 1 | 1 | `ru_wr` | ✅ Writes correct result |
| 35+ | IDLE | 1 | 0 | 0 | 0 | ✅ Inhibited — already written |
| Non-division | IDLE | 0 | 0 | 1 | `ru_wr` | ✅ Normal pass-through |

**Corner cases (div-by-zero, signed overflow) — CPI = 1:**

| Cycle | `div_state` | `is_div` | `div_done` | `wr_en_gated` | Action |
|-------|------------|----------|------------|---------------|--------|
| 1 (issue) | IDLE | 1 | 1 | `ru_wr` | ✅ Writes correct result immediately |

In corner cases, `div_done` is asserted in the same IDLE cycle that
`div_result` is set. `div_busy` is never asserted (the FSM stays in IDLE),
so the PC advances normally. CPI = 1.

**Why `div_done` and not a modified `wr_en_gated = ru_wr & (~is_div | div_busy)`:**  
The previous formulation using `div_busy` allowed 32 writes during RUNNING
with intermediate (incorrect) values of `div_result`. Although functionally
harmless (the final write overwrites them), it was architecturally unclean.
`div_done` provides exactly one write, at exactly the right cycle, with zero
incorrect intermediate writes. This requires adding `div_done` to
`alu_rv32im` (ADR 018) but keeps the register file semantically correct at
every clock edge.

## Normative Signal Definition

```systemverilog
// In top_single_cycle.sv, after instantiation of control_unit and alu_rv32im:
logic is_div;
logic wr_en_gated;

assign is_div      = (alu_op inside {ALU_DIV, ALU_DIVU, ALU_REM, ALU_REMU});
assign wr_en_gated = ru_wr & (~is_div | div_done);

// register_file receives wr_en_gated, not ru_wr directly:
register_file u_rf (
    .clk      (clk),
    .rs1_addr (rs1_addr),
    .rs2_addr (rs2_addr),
    .rd_addr  (rd_addr),
    .rd_data  (rd_data),
    .wr_en    (wr_en_gated),   // gated — not ru_wr
    .rs1_data (rs1_data),
    .rs2_data (rs2_data)
);
```

## Consequences

- No changes to `register_file` or `control_unit`. ADR 014 and ADR 022 remain
  closed.
- `alu_rv32im` adds `div_done` output port (ADR 018 updated).
- `shared_modules.md` must reflect `div_done` in the `alu_rv32im` port table.
- `is_div` adds approximately 4 LUT inputs and does not affect Fmax.
- The `inside {}` operator requires Quartus Prime 18.1+.
- The pipeline implementation does not use this logic. In the pipeline,
  division stall is managed by the hazard unit with bubble insertion; the WB
  stage only fires for valid retiring instructions.
- Corner cases produce exactly 1 write (CPI = 1) because `div_done` pulses
  in the IDLE cycle itself (see ADR 018 for timing detail).
