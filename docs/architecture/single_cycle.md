# Single-Cycle RV32IM Microarchitecture

**File:** `rtl/single_cycle/top_single_cycle.sv`  
**ISA:** RV32IM (base RV32I + M extension)  
**Memory:** Harvard (separate instruction and data memories, see [ADR 001](../decisions/001_harvard_memory_architecture.md))  
**Nominal CPI:** 1 for all RV32I instructions and MUL/MULH/MULHSU/MULHU  
**Effective CPI for division:** 34 for DIV/DIVU/REM/REMU (1 issue cycle + 32 RUNNING + 1 DONE, see [ADR 008](../decisions/008_m_extension_implementation.md) and [ADR 019](../decisions/019_alu_rv32im.md))

This document is the design reference for Objective 1, Activity 1.1 of the
thesis. It defines the top-level interface, the complete internal signal
inventory, the datapath for each instruction class, and the critical path
relevant to Fmax measurement.

> **Reference:** `docs/architecture/control_signals.md` contains the complete
> per-instruction control signal truth table. This document describes the
> structural and behavioral design; the control signal table is maintained
> separately to avoid duplication.

---

## Top-Level Interface

The chip boundary is minimal. Memories are synthesized into FPGA fabric and are
not exposed as ports.

```systemverilog
module top_single_cycle (
    input  logic clk,    // 50 MHz oscillator from DE1-SoC (PIN_AF14)
    input  logic rst_n   // Active-low synchronous reset - connected to KEY[0]
);
```

All internal signals are declared as `logic` inside the module body.
Reset vector: `32'h0000_0000` (see [ADR 012](../decisions/012_reset_vector.md)).

---

## Module Instantiation Map

```
top_single_cycle
│
├── pc_unit              (rtl/single_cycle/pc_unit.sv)
├── instruction_memory   (rtl/shared/instruction_memory.sv)
├── control_unit         (rtl/single_cycle/control_unit.sv)
├── register_file        (rtl/shared/register_file.sv)
├── imm_gen              (rtl/shared/imm_gen.sv)
├── branch_unit          (rtl/shared/branch_unit.sv)
├── alu_rv32im           (rtl/shared/alu_rv32im.sv)  ← receives clk/rst_n for divisor FSM
├── data_memory          (rtl/shared/data_memory.sv)
└── [combinational muxes inline in top_single_cycle.sv]
    ├── alu_a_mux        (3-to-1, controlled by alua_src[1:0])
    ├── alu_b_mux        (2-to-1, controlled by alub_src)
    └── wb_mux           (3-to-1, controlled by ru_data_wr_src[1:0])
```

### Note on alu_rv32im sequential behavior

`alu_rv32im` is placed in `rtl/shared/` and is used without modification by
both microarchitectures. Although the module contains a sequential state
machine (the radix-2 restoring divisor, see [ADR 008](../decisions/008_m_extension_implementation.md)),
this does not compromise the single-cycle character of the processor for the
following reasons:

1. **All RV32I instructions and MUL/MULH/MULHSU/MULHU complete in one cycle.**
   For these instructions, `div_busy` is permanently de-asserted and the ALU
   behaves as a pure combinational block. The sequential divisor state machine
   remains in `IDLE` and does not affect the datapath.

2. **DIV/DIVU/REM/REMU are the only instructions that activate the divisor.**
   When one of these instructions is issued, the processor stalls for exactly
   33 cycles via `div_busy` (32 cycles in `DIV_RUNNING` + 1 cycle in
   `DIV_DONE`). During stall cycles the PC does not advance and no instruction
   retires. This is a deliberate design choice (ADR 008) to avoid a fully
   combinational divisor that would collapse Fmax below the value attributable
   to the load instruction critical path, which would invalidate the
   architectural comparison.

3. **A fully combinational divisor is not a valid design option** for this
   project because it would make measured Fmax a function of divider depth
   rather than of the IF-->ID-->EX-->MEM-->WB datapath, undermining the experimental
   validity of the pipeline vs. single-cycle comparison.

The single-cycle label in this project refers to the execution model for the
RV32I base instruction set: each base instruction completes in exactly one
clock cycle with CPI = 1. The M-extension division instructions are documented
as exceptions with CPI = 34.

---

## Sequential Elements

The processor contains five sequential elements:

| Element | Module | Type | Width |
|---------|--------|------|-------|
| Program counter | `pc_unit` | Register (FF) | 32 bits |
| Register file | `register_file` | Register array (FF) | 32 x 32 bits |
| Instruction memory | `instruction_memory` | Logic cells (async ROM) † | IMEM_DEPTH x 32 bits |
| Data memory | `data_memory` | Logic cells (async read / sync write RAM) † | DMEM_DEPTH x 32 bits |
| Divisor state machine | `alu_rv32im` | FSM + registers | ~70 bits internal |

† The single-cycle microarchitecture requires combinational (asynchronous) read
for both memories - the instruction word must be available in the same cycle as
the PC, and load data must be available for write-back in the same cycle.
Intel Cyclone V M10K blocks always register the read operation internally
(Intel Corporation, 2016); they cannot implement true combinational read.
Quartus Prime therefore implements these memories in logic cells (LUTs and
flip-flops), ignoring the `ramstyle = "M10K"` attribute present in the RTL.
See [ADR 011](../decisions/011_instruction_memory_async_read.md) and the
Memory Implementation section below.

The pipelined processor, in contrast, uses dedicated synchronous-read modules
(`instruction_memory_pipe.sv`, `data_memory_pipe.sv`) that map to M10K blocks
- 64 for instruction memory and 32 for data memory out of the 308 available
on the Cyclone V 5CSEMA5F31C6.

The divisor FSM is the only sequential element that is not part of the
standard single-cycle datapath. It is dormant for all non-division instructions.

---

## Internal Signal Inventory

### Program Counter and Fetch

| Signal | Width | Source | Destination | Description |
|--------|-------|--------|-------------|-------------|
| `pc` | 32 | `pc_unit` | `instruction_memory`, `alu_a_mux` | Current program counter |
| `pc_plus4` | 32 | `pc_unit` | `wb_mux` | PC + 4, used as return address for JAL/JALR |
| `instruction` | 32 | `instruction_memory` | `control_unit`, `register_file`, `imm_gen` | Raw 32-bit instruction word |

### Instruction Fields (combinational slices of `instruction`)

| Signal | Width | Slice | Destination |
|--------|-------|-------|-------------|
| `opcode` | 7 | `instruction[6:0]` | `control_unit` |
| `rd_addr` | 5 | `instruction[11:7]` | `register_file` |
| `funct3` | 3 | `instruction[14:12]` | `control_unit` |
| `rs1_addr` | 5 | `instruction[19:15]` | `register_file` |
| `rs2_addr` | 5 | `instruction[24:20]` | `register_file` |
| `funct7` | 7 | `instruction[31:25]` | `control_unit` |

### Control Signals

| Signal | Width | Source | Description |
|--------|-------|--------|-------------|
| `ru_wr` | 1 | `control_unit` | Register file write enable |
| `imm_src` | 3 | `control_unit` | Immediate format selector (I/S/B/U/J) |
| `alua_src` | 2 | `control_unit` | ALU operand-A source: `00`=rs1, `01`=PC, `10`=zero (ADR 005) |
| `alub_src` | 1 | `control_unit` | ALU operand-B source: `0`=rs2, `1`=immediate |
| `alu_op` | 5 | `control_unit` | ALU operation code |
| `br_op` | 5 | `control_unit` | `{branch_type[1:0], funct3[2:0]}` |
| `dm_wr` | 1 | `control_unit` | Data memory write enable |
| `dm_ctrl` | 3 | `control_unit` | funct3 passed directly - encodes size and sign (ADR 021) |
| `ru_data_wr_src` | 2 | `control_unit` | Write-back mux: `00`=ALU, `01`=mem, `10`=PC+4 |

### Execute

| Signal | Width | Source | Destination | Description |
|--------|-------|--------|-------------|-------------|
| `imm_out` | 32 | `imm_gen` | `alu_b_mux` | Sign-extended immediate |
| `alu_a` | 32 | `alu_a_mux` | `alu_rv32im` | ALU operand A |
| `alu_b` | 32 | `alu_b_mux` | `alu_rv32im` | ALU operand B |
| `alu_res` | 32 | `alu_rv32im` | `data_memory`, `wb_mux`, `pc_unit` | ALU result / memory address / branch target |
| `div_busy` | 1 | `alu_rv32im` | `pc_unit` | Stall signal: PC holds while high |

### Register File

| Signal | Width | Source | Destination |
|--------|-------|--------|-------------|
| `rs1_data` | 32 | `register_file` | `alu_a_mux`, `branch_unit` |
| `rs2_data` | 32 | `register_file` | `alu_b_mux`, `branch_unit`, `data_memory` |
| `rd_data` | 32 | `wb_mux` | `register_file` write port |

### Branch and PC Selection

| Signal | Width | Source | Destination | Description |
|--------|-------|--------|-------------|-------------|
| `branch` | 1 | `branch_unit` | `pc_unit` | Take branch/jump this cycle |
| `mask_pc_lsb` | 1 | `branch_unit` | `pc_unit` | JALR: force bit 0 of target to zero (ADR 006) |
| `branch_target` | 32 | `pc_unit` (combinational) | NextPC mux | `{alu_res[31:1], 1'b0}` if `mask_pc_lsb`, else `alu_res` |
| `next_pc` | 32 | `pc_unit` (combinational) | PC register input | `branch_target` if `branch`, else `pc_plus4` |

### Memory and Write-Back

| Signal | Width | Source | Destination |
|--------|-------|--------|-------------|
| `dm_rd_data` | 32 | `data_memory` | `wb_mux` |

---

## PC Unit Design (`rtl/single_cycle/pc_unit.sv`)

### Ports

| Port | Direction | Width | Description |
|------|-----------|-------|-------------|
| `clk` | input | 1 | Clock |
| `rst_n` | input | 1 | Active-low synchronous reset |
| `branch` | input | 1 | Take branch/jump signal |
| `mask_pc_lsb` | input | 1 | Force bit 0 of branch target to zero (JALR) |
| `alu_res` | input | 32 | Branch/jump target from ALU |
| `div_busy` | input | 1 | Stall: hold PC while high |
| `pc` | output | 32 | Current PC |
| `pc_plus4` | output | 32 | PC + 4 |

### Behavior

```
pc_plus4      = pc + 32'd4                             // combinational
branch_target = mask_pc_lsb ? {alu_res[31:1], 1'b0}   // combinational
              :                alu_res
next_pc       = branch    ? branch_target               // combinational
              :              pc_plus4

always_ff @(posedge clk) begin
    if (!rst_n)        pc <= 32'h0000_0000   // reset (ADR 012)
    else if (div_busy) pc <= pc               // stall: DIV_RUNNING or DIV_DONE active
    else               pc <= next_pc          // normal advance
end
```

---

## Datapath by Instruction Class

### R-type base (ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND)

```
alu_a = rs1_data  (alua_src = 00)
alu_b = rs2_data  (alub_src = 0)
alu_res = rs1 OP rs2
next_pc = pc + 4  (branch = 0)
register[rd] = alu_res  (ru_wr = 1, ru_data_wr_src = 00)
div_busy = 0  - result valid this cycle
CPI = 1
```

### M-extension multiply (MUL, MULH, MULHSU, MULHU)

```
Same datapath as R-type base.
div_busy = 0  - combinational result, valid this cycle
CPI = 1
```

### M-extension divide (DIV, DIVU, REM, REMU)

```
Same control signals as R-type base.

FSM transitions after issue:
  Cycle 1       : DIV_IDLE --> DIV_RUNNING, div_busy asserts
  Cycles 2..32  : DIV_RUNNING (31 remaining iterations), div_busy = 1
  Cycle 33      : DIV_RUNNING --> DIV_DONE, div_busy = 1
  Cycle 34      : DIV_DONE --> DIV_IDLE, div_busy de-asserts
                  alu_res = div_result (correct final value)
                  PC advances, register[rd] = alu_res (ru_wr = 1)

Effective CPI = 34  (1 issue + 32 RUNNING + 1 DONE)
Corner cases (div-by-zero, signed overflow): resolved in DIV_IDLE,
  div_busy never asserted, CPI = 1.
```

### I-type ALU (ADDI, SLTI, SLTIU, XORI, ORI, ANDI, SLLI, SRLI, SRAI)

```
alu_a = rs1_data  (alua_src = 00)
alu_b = imm_out   (alub_src = 1, imm_src = 000)
alu_res = rs1 OP imm
register[rd] = alu_res  (ru_wr = 1, ru_data_wr_src = 00)
CPI = 1
```

### LUI

```
alu_a = 32'b0    (alua_src = 10 - constant zero, ADR 005)
alu_b = imm_out  (U-type: {imm[31:12], 12'b0})
alu_res = 0 + imm_out = imm_out
register[rd] = alu_res  (ru_wr = 1)
CPI = 1
```

### AUIPC

```
alu_a = pc       (alua_src = 01)
alu_b = imm_out  (U-type)
alu_res = pc + imm_out
register[rd] = alu_res  (ru_wr = 1)
CPI = 1
```

### JAL

```
alu_a = pc       (alua_src = 01)
alu_b = imm_out  (J-type signed offset)
alu_res = pc + J_offset  (jump target)
branch = 1, mask_pc_lsb = 0
next_pc = alu_res
register[rd] = pc_plus4  (ru_data_wr_src = 10)
CPI = 1
```

### JALR

```
alu_a = rs1_data  (alua_src = 00)
alu_b = imm_out   (I-type signed offset)
alu_res = rs1 + I_offset
branch = 1, mask_pc_lsb = 1
next_pc = {alu_res[31:1], 1'b0}  (LSB forced to zero, ADR 006)
register[rd] = pc_plus4  (ru_data_wr_src = 10)
CPI = 1
```

### Conditional Branch (BEQ, BNE, BLT, BGE, BLTU, BGEU)

```
alu_a = pc       (alua_src = 01)
alu_b = imm_out  (B-type signed offset)
alu_res = pc + B_offset  (branch target - computed in parallel with condition)
branch_unit evaluates condition on rs1_data / rs2_data directly (ADR 007)
next_pc = branch ? alu_res : pc_plus4
ru_wr = 0, dm_wr = 0
CPI = 1  (no branch penalty: decision and fetch occur in the same cycle)
```

### Load (LB, LH, LW, LBU, LHU)

```
alu_a = rs1_data  (alua_src = 00)
alu_b = imm_out   (I-type byte offset)
alu_res = rs1 + offset  (memory address)
dm_rd_data = data_memory[alu_res]  (dm_wr = 0, dm_ctrl = funct3, ADR 021)
register[rd] = dm_rd_data  (ru_data_wr_src = 01)
CPI = 1
```

### Store (SB, SH, SW)

```
alu_a = rs1_data  (alua_src = 00)
alu_b = imm_out   (S-type split offset)
alu_res = rs1 + offset  (memory address)
data_memory[alu_res] = rs2_data  (dm_wr = 1, dm_ctrl = funct3, ADR 021)
ru_wr = 0
CPI = 1
```

---

## Control Signal Truth Table (summary by class)

Full per-instruction values: see `docs/architecture/control_signals.md`.

| Instruction class | `ru_wr` | `imm_src` | `alua_src` | `alub_src` | `br_op[4:3]` | `dm_wr` | `ru_data_wr_src` |
|-------------------|---------|-----------|------------|------------|--------------|---------|-----------------|
| R-type / M-ext | 1 | - | `00` | 0 | `00` | 0 | `00` |
| I-type ALU | 1 | `000` | `00` | 1 | `00` | 0 | `00` |
| LUI | 1 | `011` | **`10`** | 1 | `00` | 0 | `00` |
| AUIPC | 1 | `011` | `01` | 1 | `00` | 0 | `00` |
| JAL | 1 | `100` | `01` | 1 | `10` | 0 | `10` |
| JALR | 1 | `000` | `00` | 1 | `11` | 0 | `10` |
| Branch | 0 | `010` | `01` | 1 | `01` | 0 | - |
| Load | 1 | `000` | `00` | 1 | `00` | 0 | `01` |
| Store | 0 | `001` | `00` | 1 | `00` | 1 | - |

---

## Critical Path Analysis

The longest combinational path determines Fmax after place-and-route. For
RV32I instructions the critical path is the **load instruction path**
(Patterson & Hennessy, 2017, Section 4.4; Harris & Harris, 2021, Section 7.4.1):

```
PC register output
  --> instruction_memory (combinational read, ADR 011)
  --> control_unit (combinational decode on opcode/funct3/funct7)
  --> register_file (combinational read on rs1_addr)
  --> alu_a_mux
  --> alu_rv32im (ADD: combinational adder)
  --> data_memory (combinational read + byte extraction, ADR 019, ADR 020)
  --> wb_mux
  --> register_file setup time
```

For MUL/MULH/MULHSU/MULHU, the DSP-block multiplication path may compete
with the load path. This is determined empirically by the Timing Analyzer
after place-and-route. The actual critical path is reported in
`results/single_cycle/` after the first synthesis replica.

The divisor path does **not** appear on the critical path because it is
implemented as a multi-cycle FSM using a radix-2 restoring division algorithm
(Weste & Harris, 2010, Section 11.4). Its output is captured in a register and
presented combinationally to `alu_res` only after `div_busy` de-asserts.

---

## Memory Parameters

| Parameter | Synthesis value | Simulation (cocotb) value | Notes |
|-----------|-----------------|---------------------------|-------|
| `IMEM_DEPTH` | 2048 words (8 KB) | 16384 words (64 KB) | Set via `.qsf` `set_parameter` for synthesis; exported as env var for cocotb |
| `DMEM_DEPTH` | 512 words (2 KB) | 8192 words (32 KB) | Same mechanism |
| Reset vector | `0x00000000` | `0x00000000` | First word of instruction memory (ADR 012) |

Synthesis uses smaller depths to keep logic-cell utilisation low and reduce
compilation time. Simulation uses larger depths to test the full address-decoding
logic and accommodate larger programs (e.g. CoreMark) in CI.

---

## Memory Implementation: Logic Cells vs. M10K

A key architectural difference between the single-cycle and pipeline
implementations is how memories are realised in the FPGA fabric.

### Why the single-cycle cannot use M10K blocks

The single-cycle datapath requires **combinational (asynchronous) read** for
both instruction and data memory:

- **Instruction memory:** The PC is presented as an address at the start of the
  cycle, and the instruction word must be valid at the decode logic inputs in
  the *same* cycle, without waiting for a clock edge.
- **Data memory:** For load instructions, the effective address computed by the
  ALU must produce valid read data at the write-back mux inputs within the same
  cycle.

Intel Cyclone V M10K blocks are fundamentally synchronous storage elements.
Every read operation is clocked internally, the address is sampled on a clock
edge and the data appears at the output a fixed access time later (Intel
Corporation, 2016, Section 3-4: M10K Memory Blocks). While the output register
can be bypassed (`OUTDATA_REG_A = "UNREGISTERED"` in the `altsyncram`
megafunction), the memory array itself is still clocked. A true combinational
read cannot be mapped to an M10K block.

When Quartus Prime encounters an unpacked array read written as a continuous
assignment (`assign mem_read = mem[addr]`), it implements the array in logic
cells, LUTs and flip-flops, irrespective of any `ramstyle` attribute attached
to the array declaration. The `ramstyle = "M10K"` attribute present in
`instruction_memory.sv` is silently ignored for this reason.

### How the pipeline uses M10K efficiently

The pipelined processor inserts an IF/ID pipeline register between the
instruction memory output and the decode stage. This register captures the
instruction word on the rising clock edge of each cycle. Because the read
completes during the clock period and the result is sampled at the next edge,
a synchronous (clocked) read is sufficient. The pipeline modules
`instruction_memory_pipe.sv` and `data_memory_pipe.sv` describe synchronous
reads using `always_ff` blocks, which Quartus Prime maps to M10K blocks.

The synthesis results confirm this difference:

| Metric | Single-cycle | Pipeline |
|--------|-------------|----------|
| M10K blocks used | 0 | 96 |
| ALMs (with IMEM_DEPTH=2048, DMEM_DEPTH=512) | ~11 500 | ~2 100 |
| Fmax (Slow 85°C, quartile-based) | 37.54 MHz | 57.59 MHz |

The single-cycle uses ~11 500 ALMs because the 2048 x 32-bit instruction memory
requires ~65 000 flip-flops, each mapped to a logic cell. The pipeline uses
only ~2 100 ALMs because the 16384-word instruction memory fits in 64 M10K
blocks (each M10K = 10 Kbits, configurable as 1024 x 10 bits).

### References

- Intel Corporation (2016). *Cyclone V Device Handbook, Volume 1: Device
  Interfaces and Integration*. Section 3-4: M10K Memory Blocks.
- Intel Corporation (2018). *Quartus Prime Handbook Volume 2: Design
  Implementation and Optimization*. Section 11: Recommended HDL Coding Styles
  - Inference of Memory Functions from HDL Code.

---

## Known Limitations and Explicit Exceptions

1. **CPI = 1 only for RV32I and M-extension multiply.**
   DIV/DIVU/REM/REMU have effective CPI = 34: 1 issue cycle, 32 cycles in
   `DIV_RUNNING`, and 1 cycle in `DIV_DONE` (ADR 018). Division corner cases
   (division by zero, signed overflow) are resolved in `DIV_IDLE` with CPI = 1.
   This must be reported explicitly in the experimental results section.

2. **No branch penalty.** The processor has no speculative execution. The
   branch decision and the fetch of the next instruction occur in the same
   cycle. There are no flush cycles for branches in the single-cycle design.

3. **No exception or interrupt handling.** `ecall`, `ebreak`, and all CSR
   instructions fall into the `default` branch of the control unit:
   `ru_wr = 0`, `dm_wr = 0`, `br_op = {BR_NONE, 3'b000}`. riscv-tests
   pass/fail detection uses the `tohost` memory write convention (ADR 012),
   not `ecall` execution.

4. **No memory-mapped I/O.** Both memories are plain RAM/ROM with no address
   decoding for peripheral registers.

5. **Natural alignment assumed.** Load and store instructions must be
   naturally aligned (LW to 4-byte boundary, LH to 2-byte boundary).
   Misaligned accesses produce undefined results; no exception is raised
   (ADR 020).

---

## References

- Harris, S. L., & Harris, D. M. (2021). *Digital Design and Computer
  Architecture: RISC-V Edition*. Morgan Kaufmann.
- Intel Corporation (2016). *Cyclone V Device Handbook, Volume 1: Device
  Interfaces and Integration*. Section 3-4: M10K Memory Blocks.
- Intel Corporation (2018). *Quartus Prime Handbook Volume 2: Design
  Implementation and Optimization*. Section 11: Recommended HDL Coding Styles.
- Patterson, D. A., & Hennessy, J. L. (2017). *Computer Architecture: A
  Quantitative Approach* (6th ed.). Morgan Kaufmann.
- Weste, N. H. E., & Harris, D. M. (2010). *CMOS VLSI Design: A Circuits and
  Systems Perspective* (4th ed.). Addison-Wesley.
