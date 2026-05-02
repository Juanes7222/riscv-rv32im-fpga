# ADR 022 — Control Unit: Interface and Implementation

**Status:** Accepted  
**Date:** 2026-05-02

## Context

The control unit is a purely combinational module that decodes the opcode,
funct3, and funct7 fields of the instruction word and produces the control
signals that drive all other modules in the datapath. Three design decisions
require formal justification: the width of `alua_src`, the handling of
`dm_ctrl`, and the constant declaration style.

## Decisions

**1. `alua_src` is a 2-bit signal** consistent with [ADR 005](005_alua_src_2bit.md).
LUI assigns `alua_src = 2'b10` (constant zero).

**2. `dm_ctrl` is assigned directly as `funct3`** for all load and store
instructions, with no intermediate constants or translation table.

**3. All constants are `localparam`**, consistent with [ADR 010](010_systemverilog_style.md).

## Rationale

**`alua_src` 2-bit width and LUI:**  
ADR 005 defines three ALU-A sources: rs1 (`2'b00`), PC (`2'b01`), and
constant zero (`2'b10`). LUI must use constant zero because the U-type
instruction format repurposes `instruction[19:15]` as part of the immediate
field — it is not a valid rs1 address. If the control unit drives `alua_src =
2'b00` for LUI, the ALU receives whatever value is stored in the register
indexed by those bits, which is undefined from the LUI instruction's
perspective and produces incorrect results whenever that register is non-zero.
Constant zero (`2'b10`) guarantees `alu_result = 0 + imm_out = imm_out`
regardless of register file state.

**`dm_ctrl = funct3`:**  
The funct3 encoding for load and store instructions already encodes access
width and sign extension in exactly the form required by `data_memory.sv`.
Passing funct3 directly eliminates a five-row translation table in the control
unit and makes the signal self-documenting to any reader familiar with the
RV32I ISA.

**`localparam`:**  
Control signals and opcode encodings are implementation constants, not module
configuration points. Declaring them as `parameter` allows instantiating
modules to override them, which would silently produce incorrect decode logic.
`localparam` is the correct declaration for values that must not be overridden.

## Normative RTL Specification

See [control_unit.sv](../../rtl/monocycle/control_unit.sv)


## M-Extension Decode Note

M-extension instructions share opcode `OP_REG` with base R-type instructions.
Disambiguation uses `funct7[0]`: base R-type has `funct7 = 7'b0000000` or
`7'b0100000` (bit 0 = 0); M-extension has `funct7 = 7'b0000001` (bit 0 = 1).
Checking `funct7[0]` is sufficient and more concise than checking
`funct7 == 7'b0000001`.

For `funct3 = 3'b101` in OP_REG, M-extension (DIVU) takes priority over the
`funct7[5]` check for SRA/SRL. When `funct7[0] = 1`, the instruction is DIVU
regardless of `funct7[5]`. The ternary chain `funct7[0] ? ALU_DIVU : funct7[5]
? ALU_SRA : ALU_SRL` encodes this priority correctly.

## Consequences

- The control unit is iteration-1 complete: it decodes all RV32I opcodes plus
  the full M-extension (MUL/MULH/MULHSU/MULHU/DIV/DIVU/REM/REMU). Per ADR 003,
  M opcodes are enabled in the control unit only after rv32ui tests pass. The
  structural decode is correct and complete from the first commit; the
  iteration boundary is a verification milestone, not an RTL change.
- `ecall`, `ebreak`, and all CSR instructions fall into the `default` branch:
  `ru_wr = 0`, `dm_wr = 0`, `br_op = {BR_NONE, 3'b000}`. This is a safe
  no-op. riscv-tests pass/fail detection uses the `tohost` memory write
  convention (ADR 012), not `ecall` execution.
- `dm_ctrl` is driven as `funct3` in the default section. For non-memory
  instructions, `dm_ctrl` is a don't-care because `dm_wr = 0` and
  `ru_data_wr_src != WB_MEM`. Setting it to `funct3` in the default avoids
  an undriven output and keeps the always_comb block free of latches.
- `alua_src` uses named localparams (`ALUA_RS1`, `ALUA_PC`, `ALUA_ZERO`) that
  match the 2-bit encoding defined in ADR 005. These localparams must be kept
  synchronized with the mux in `top_single_cycle.sv` and the pipeline ID stage.
