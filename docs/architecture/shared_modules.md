# Shared Module Interfaces

This document defines the port interface and behavioral contract for every
module in `rtl/shared/`. Both the single-cycle and pipelined implementations
instantiate these modules without modification. Any change to an interface
requires a new ADR and a corresponding update to this document.

The boundary between shared and microarchitecture-specific modules is defined
in [ADR 004](../decisions/004_shared_modules_boundary.md).

---

## alu_rv32im

**File:** `rtl/shared/alu_rv32im.sv`  
**Type:** Combinational (RV32I + MUL/MULH/MULHSU/MULHU); multi-cycle FSM for DIV/DIVU/REM/REMU  
**Description:** Performs all RV32I and RV32M integer operations. Division and
remainder operations use a radix-2 restoring divisor (ADR 008). The `div_busy`
output signals that the result is not yet valid. See [ADR 018](../decisions/018_alu_rv32im.md)
for the normative RTL specification and full design rationale.

### Ports

| Port | Direction | Width | Description |
|------|-----------|-------|-------------|
| `clk` | input | 1 | Clock — used by the radix-2 restoring divisor FSM |
| `rst_n` | input | 1 | Active-low synchronous reset — resets all FSM registers |
| `a` | input | 32 | Operand A |
| `b` | input | 32 | Operand B |
| `alu_op` | input | 5 | Operation select (see encoding below) |
| `alu_res` | output | 32 | Result (combinational for non-division; registered for division) |
| `div_busy` | output | 1 | High while division FSM is in DIV_RUNNING or DIV_DONE state |
| `div_done` | output | 1 | 1-cycle pulse when division result is valid (DONE→IDLE transition) |

### ALU Operation Encoding

| `alu_op` | Operation | Latency |
|----------|-----------|---------|
| `5'b00000` | ADD | 1 cycle |
| `5'b00001` | SUB | 1 cycle |
| `5'b00010` | SLL | 1 cycle |
| `5'b00011` | SLT (signed) | 1 cycle |
| `5'b00100` | SLTU (unsigned) | 1 cycle |
| `5'b00101` | XOR | 1 cycle |
| `5'b00110` | SRL | 1 cycle |
| `5'b00111` | SRA | 1 cycle |
| `5'b01000` | OR | 1 cycle |
| `5'b01001` | AND | 1 cycle |
| `5'b01010` | MUL | 1 cycle (DSP block) |
| `5'b01011` | MULH | 1 cycle (DSP block) |
| `5'b01100` | MULHSU (see [ADR 009](../decisions/009_mulhsu_33bit_extension.md)) | 1 cycle (DSP block) |
| `5'b01101` | MULHU | 1 cycle (DSP block) |
| `5'b01110` | DIV (multi-cycle) | 34 cycles nominal |
| `5'b01111` | DIVU (multi-cycle) | 34 cycles nominal |
| `5'b10000` | REM (multi-cycle) | 34 cycles nominal |
| `5'b10001` | REMU (multi-cycle) | 34 cycles nominal |

### Behavioral Notes

- `div_busy` is permanently de-asserted for all non-division operations. The
  FSM remains in `DIV_IDLE` and the module behaves as a pure combinational block.
- For DIV/DIVU/REM/REMU with normal operands, `div_busy` is asserted for
  exactly 33 consecutive cycles: 32 cycles in `DIV_RUNNING` and 1 cycle in
  `DIV_DONE`. The correct result is available on `alu_res` on the clock edge
  that transitions `DIV_DONE → DIV_IDLE`, which is the same edge that
  de-asserts `div_busy`. Effective CPI = 34.
- `div_done` pulses high for exactly 1 cycle when `div_result` holds the
  correct final value: on the `DIV_DONE → DIV_IDLE` transition for normal
  divisions, and on the issue cycle itself for corner cases (div-by-zero,
  signed overflow). `top_single_cycle` uses `div_done` to gate the register
  file write enable (see [ADR 023](../decisions/023_wr_en_gated.md)).
- Division corner cases are resolved in `DIV_IDLE` without asserting `div_busy`.
  `div_done` pulses once; effective CPI = 1.

### Division Corner Cases

| Condition | Operation | Result |
|-----------|-----------|--------|
| `b == 0` | DIV | `0xFFFF_FFFF` (-1 signed) |
| `b == 0` | DIVU | `0xFFFF_FFFF` (2³² − 1) |
| `b == 0` | REM | `a` (dividend) |
| `b == 0` | REMU | `a` (dividend) |
| `a == 0x8000_0000 && b == 0xFFFF_FFFF` | DIV | `0x8000_0000` (overflow) |
| `a == 0x8000_0000 && b == 0xFFFF_FFFF` | REM | `0` |

---

## register_file

**File:** `rtl/shared/register_file.sv`  
**Type:** Sequential (synchronous write, asynchronous read)  
**Description:** 32 × 32-bit register file. Register x0 is hardwired to zero
and cannot be written. Reads are combinational (result available same cycle as
address). Writes take effect on the rising clock edge.

### Ports

| Port | Direction | Width | Description |
|------|-----------|-------|-------------|
| `clk` | input | 1 | Clock |
| `rs1_addr` | input | 5 | Read address 1 |
| `rs2_addr` | input | 5 | Read address 2 |
| `rd_addr` | input | 5 | Write address |
| `rd_data` | input | 32 | Write data |
| `wr_en` | input | 1 | Write enable |
| `rs1_data` | output | 32 | Read data 1 (combinational) |
| `rs2_data` | output | 32 | Read data 2 (combinational) |

### Behavioral Notes

- **x0 is hardwired to zero.** Writes to `rd_addr == 5'b00000` are silently
  discarded regardless of `wr_en`.
- **Read-before-write semantics.** When a read address matches the write
  address in the same clock cycle (`rs1_addr == rd_addr` or
  `rs2_addr == rd_addr` while `wr_en == 1`), the output reflects the
  **old value** (before the write). The new value appears on the next cycle.
  This is intentional: in the pipelined implementation, all same-cycle
  RAW dependencies are resolved by the forwarding unit, not by the register
  file. If the register file returned the new value, the forwarding unit
  would forward it a second time, corrupting the result.
- **No internal forwarding.** In the pipeline, the forwarding unit provides
  resolved values to the ALU and branch unit inputs
  (see [ADR 007](../decisions/007_branch_unit_inputs.md)).

---

## instruction_memory

**File:** `rtl/shared/instruction_memory.sv`  
**Type:** Asynchronous read (combinational output)  
**Description:** Read-only instruction memory. The instruction word is
available combinationally in the same cycle as the PC address is presented.
See [ADR 011](../decisions/011_instruction_memory_async_read.md) for rationale.

### Ports

| Port | Direction | Width | Description |
|------|-----------|-------|-------------|
| `addr` | input | 32 | Byte address (PC value) |
| `instruction` | output | 32 | 32-bit instruction word |

### Behavioral Notes

- No `clk` port. The module is purely combinational.
- Byte-addressed interface; `addr[1:0]` are ignored internally.
  All RV32I instructions are 32-bit aligned.
- Initialized from a `.mem` file via `$readmemh` at simulation time:
  ```systemverilog
  parameter MEM_FILE = "program.mem"
  ```
- Memory depth is set via module parameter `IMEM_DEPTH` (default: 16384 words
  = 64 KB, see [ADR 013](../decisions/013_memory_sizes.md)).

---

## data_memory

**File:** `rtl/shared/data_memory.sv`  
**Type:** Synchronous write, asynchronous read  
**Description:** Read-write data memory. Supports byte, halfword, and word
accesses. On loads, the result is sign- or zero-extended to 32 bits as
specified by `dm_ctrl`. On stores, only the relevant byte lanes are written
using byte enables. See [ADR 019](../decisions/019_data_memory_async_read.md),
[ADR 020](../decisions/020_data_memory_organization.md), and
[ADR 021](../decisions/021_dm_ctrl_funct3.md).

### Ports

| Port | Direction | Width | Description |
|------|-----------|-------|-------------|
| `clk` | input | 1 | Clock |
| `addr` | input | 32 | Byte address |
| `wr_data` | input | 32 | Data to write (from rs2) |
| `dm_wr` | input | 1 | Write enable |
| `dm_ctrl` | input | 3 | funct3 direct — encodes access size and load sign mode (ADR 021) |
| `rd_data` | output | 32 | Read data, combinational, extended to 32 bits |

### dm_ctrl Encoding

`dm_ctrl` is the `funct3` field of the load or store instruction passed
directly without translation (ADR 021). Bit [2] encodes sign/zero extension
for loads and is irrelevant for stores; bits [1:0] encode access width.

| `dm_ctrl` | Load result | Store write width |
|-----------|-------------|-------------------|
| `3'b000` | Sign-extended byte (LB) | Byte — 8 bits (SB) |
| `3'b001` | Sign-extended halfword (LH) | Halfword — 16 bits (SH) |
| `3'b010` | Word — 32 bits (LW) | Word — 32 bits (SW) |
| `3'b100` | Zero-extended byte (LBU) | Byte — 8 bits (SB) |
| `3'b101` | Zero-extended halfword (LHU) | Halfword — 16 bits (SH) |

### Behavioral Notes

- Read is asynchronous: `rd_data` is available combinationally in the same
  cycle the address is presented (ADR 019).
- Write is synchronous: memory is updated on the rising edge of `clk` when
  `dm_wr == 1`.
- Write data `wr_data` is replicated across all byte positions before the
  memory array; byte enables select which lanes are written (ADR 020).
- Natural alignment is assumed. Misaligned accesses produce undefined results;
  no exception is raised (ADR 020).
- Memory depth is set via parameter `DMEM_DEPTH` (default: 8192 words = 32 KB,
  see [ADR 013](../decisions/013_memory_sizes.md)).

---

## imm_gen

**File:** `rtl/shared/imm_gen.sv`  
**Type:** Combinational  
**Description:** Extracts and sign-extends the immediate field from a 32-bit
RV32I instruction. The output is always sign-extended to 32 bits. The format
is selected by `imm_src`.

### Ports

| Port | Direction | Width | Description |
|------|-----------|-------|-------------|
| `instruction` | input | 32 | Full 32-bit instruction word |
| `imm_src` | input | 3 | Immediate format selector |
| `imm_out` | output | 32 | Sign-extended 32-bit immediate |

### imm_src Encoding

| `imm_src` | Format | Bit extraction | Instructions |
|-----------|--------|----------------|--------------|
| `3'b000` | I-type | `inst[31:20]` sign-extended | ADDI, LOAD, JALR, SLLI, SRLI, SRAI |
| `3'b001` | S-type | `{inst[31:25], inst[11:7]}` sign-extended | SB, SH, SW |
| `3'b010` | B-type | `{inst[31], inst[7], inst[30:25], inst[11:8], 1'b0}` sign-extended | BEQ, BNE, BLT, BGE, BLTU, BGEU |
| `3'b011` | U-type | `{inst[31:12], 12'b0}` | LUI, AUIPC |
| `3'b100` | J-type | `{inst[31], inst[19:12], inst[20], inst[30:21], 1'b0}` sign-extended | JAL |

### Behavioral Notes

- Bit extraction follows the RISC-V ISA specification (Waterman & Asanović, 2019).
- For I-type shift instructions (SLLI, SRLI, SRAI), only `inst[24:20]` are
  used as the shift amount by the ALU. The full sign-extended immediate is
  still generated; the ALU masks the lower 5 bits internally.

---

## branch_unit

**File:** `rtl/shared/branch_unit.sv`  
**Type:** Combinational  
**Description:** Evaluates branch conditions and generates PC control signals.
Does not calculate the jump target address — that is the ALU's responsibility
(ADD on PC + offset or rs1 + offset).

### Ports

| Port | Direction | Width | Description |
|------|-----------|-------|-------------|
| `rs1_data` | input | 32 | First comparand (direct from register file or forwarding unit) |
| `rs2_data` | input | 32 | Second comparand (direct from register file or forwarding unit) |
| `br_op` | input | 5 | `{branch_type[1:0], funct3[2:0]}` |
| `branch` | output | 1 | High when a jump or branch is taken |
| `mask_pc_lsb` | output | 1 | High for JALR only — force bit 0 of target to zero (ADR 006) |

### br_op Encoding

`br_op[4:3]` selects the instruction class; `br_op[2:0]` carries funct3 for
conditional branches and is ignored for JAL/JALR.

| `br_op[4:3]` | Class | `branch` | `mask_pc_lsb` |
|--------------|-------|----------|----------------|
| `2'b00` | None | `0` | `0` |
| `2'b01` | Conditional branch | Evaluated from funct3 and rs1/rs2 | `0` |
| `2'b10` | JAL | `1` | `0` |
| `2'b11` | JALR | `1` | `1` |

### Conditional Branch funct3 Mapping

| `br_op[2:0]` | Instruction | Condition |
|--------------|-------------|-----------|
| `3'b000` | BEQ | `rs1 == rs2` |
| `3'b001` | BNE | `rs1 != rs2` |
| `3'b100` | BLT | `$signed(rs1) < $signed(rs2)` |
| `3'b101` | BGE | `$signed(rs1) >= $signed(rs2)` |
| `3'b110` | BLTU | `rs1 < rs2` (unsigned) |
| `3'b111` | BGEU | `rs1 >= rs2` (unsigned) |

### Behavioral Notes

- `rs1_data` and `rs2_data` are connected directly from the register file
  read ports in the single-cycle top-level, bypassing the ALU operand muxes
  (see [ADR 007](../decisions/007_branch_unit_inputs.md)).
- In the pipelined implementation, these inputs receive forwarded values from
  the forwarding unit. The module itself does not change.
- `mask_pc_lsb` is only meaningful when `branch == 1`. Its value when
  `branch == 0` is a combinational don't-care.
