# Pipeline RV32IM Microarchitecture

**File:** `rtl/pipeline/top_pipeline.sv`  
**ISA:** RV32IM (base RV32I + M extension)  
**Memory:** Harvard (separate instruction and data memories, see [ADR 001](../decisions/001_harvard_memory_architecture.md))  
**Stages:** 5 - IF, ID, EX, MEM, WB  
**Hazard resolution:** Data forwarding (EX/MEM-->EX, MEM/WB-->EX, WB-->ID) + load-use stall + branch/jump flush + trap flush  
**Branch prediction:** Not-taken (branches resolved in EX, flush on taken)  
**Nominal CPI:** 1 for all RV32I and M-extension multiply instructions  
**Effective CPI for division:** 34 (same multi-cycle divisor FSM as single-cycle, see [ADR 008](../decisions/008_m_extension_implementation.md))

This document is the design reference for Objective 1, Activity 1.1 of the
thesis. It mirrors the structure of `single_cycle.md` to enable direct
comparison between the two microarchitectures.

> **Reference:** `docs/architecture/control_signals.md` contains the complete
> per-instruction control signal truth table shared by both microarchitectures.

---

## Top-Level Interface

```systemverilog
module top_pipeline (
    input  logic clk,    // 50 MHz oscillator from DE1-SoC (PIN_AF14)
    input  logic rst_n   // Active-low synchronous reset - connected to KEY[0]
);
```

Reset vector: `32'h0000_0000` (see [ADR 012](../decisions/012_reset_vector.md)).
Internal active-high `rst` is generated as `rst = ~rst_n` for use by pipeline
registers and the register file.

---

## Module Instantiation Map

```
top_pipeline
│
├── pc_unit              (rtl/pipeline/pc_unit.sv)
├── instruction_memory   (rtl/pipeline/instruction_memory_pipe.sv)  ← M10K synchronous ROM
├── if_id_register       (rtl/pipeline/if_id_register.sv)
├── control_unit         (rtl/pipeline/control_unit.sv)
├── hazard_detection_unit(rtl/pipeline/hazard_detection.sv)
├── imm_gen              (rtl/shared/imm_gen.sv)
├── register_file        (rtl/shared/register_file.sv)              ← synchronous write
├── id_ex_register       (rtl/pipeline/id_ex_register.sv)
├── forwarding_unit      (rtl/pipeline/forwarding_unit.sv)
├── alu_rv32im           (rtl/shared/alu_rv32im.sv)                 ← receives clk/rst_n for divisor FSM
├── branch_unit          (rtl/shared/branch_unit.sv)
├── ex_mem_register      (rtl/pipeline/ex_mem_register.sv)
├── data_memory          (rtl/pipeline/data_memory_pipe.sv)         ← M10K synchronous RAM
├── mem_wb_register      (rtl/pipeline/mem_wb_register.sv)
├── csr_file             (rtl/shared/csr_file.sv)
├── perf_counters        (rtl/shared/perf_counter.sv)
└── [combinational muxes inline in top_pipeline.sv]
    ├── wb_data_mux      (4-to-1, controlled by wb_ru_data_wr_src)
    ├── pc_redirect_mux   (trap target / branch target)
    └── [WB-to-ID forwarding muxes inline in top stage]
```

---

## Sequential Elements

The pipeline contains the following sequential elements. Unlike the
single-cycle, all memory elements are inferred as M10K blocks because
the pipeline registers satisfy the synchronous-read requirement.

| Element | Module | Type | Width |
|---------|--------|------|-------|
| Program counter | `pc_unit` | Register (FF) | 32 bits |
| Instruction memory | `instruction_memory_pipe` | M10K synchronous ROM | IMEM_DEPTH x 32 bits |
| IF/ID register | `if_id_register` | Pipeline register | `{pc, instruction}` = 64 bits |
| Register file | `register_file` | Register array (FF) | 32 x 32 bits |
| ID/EX register | `id_ex_register` | Pipeline register | control+bus = ~175 bits |
| EX/MEM register | `ex_mem_register` | Pipeline register | control+bus = ~175 bits |
| Data memory | `data_memory_pipe` | M10K synchronous RAM (4 byte-lanes) | DMEM_DEPTH x 32 bits |
| MEM/WB register | `mem_wb_register` | Pipeline register | control+bus = ~150 bits |
| Divisor FSM | `alu_rv32im` | FSM + registers | ~70 bits internal |
| CSR file | `csr_file` | Register array (FF) | ~12 registers x 32 bits |

The data memory read-data bypasses the MEM/WB register - the registered
output of `data_memory_pipe` feeds the WB writeback mux combinationally,
avoiding an extra cycle of latency on loads ([ADR 041](../decisions/041_pipeline_data_hazard_limitation.md)).

---

## Pipeline Stage Diagram

```
Cycle   IF      ID      EX      MEM     WB
 N     [INSTR]  -       -       -       -
 N+1   [NEXT]  [INSTR]  -       -       -
 N+2   [NEXT]  [NEXT]  [INSTR]  -       -
 N+3   [NEXT]  [NEXT]  [NEXT]  [INSTR]  -
 N+4   [NEXT]  [NEXT]  [NEXT]  [NEXT]  [INSTR]  ← instruction i commits
```

---

## Internal Signal Inventory

### Stage IF - Instruction Fetch

| Signal | Width | Source | Destination | Description |
|--------|-------|--------|-------------|-------------|
| `if_pc` | 32 | `pc_unit` | `imem_addr`, `if_id` | Current PC for this fetch |
| `if_pc_plus4` | 32 | Combinational | `if_id` (via PC+4 calc) | Next sequential address |
| `if_instruction` | 32 | `instruction_memory_pipe` | `if_id` | Instruction word (combinational from M10K) |
| `imem_addr` | 32 | Mux (`if_pc` or `pc_redirect_target`) | `instruction_memory_pipe` | Address to IMEM - redirects on flush |
| `stall` | 1 | `hazard_detection_unit` | `pc_unit`, `if_id` | Hold PC and IF/ID on load-use or div |
| `flush` | 1 | Combinational (`branch_flush \|\| trap_flush`) | `if_id` | Invalidate IF/ID on branch/trap |
| `branch_flush` | 1 | `ex_branch_taken` | flush logic | Branch taken this cycle |
| `trap_flush` | 1 | `wb_trap_entry \|\| wb_mret_exec` | flush logic | Trap or MRET in WB |

The IMEM address mux redirects to `pc_redirect_target` during a flush,
so the synchronous M10K captures the correct instruction on the next clock
edge instead of the stale sequential address.

### Stage ID - Instruction Decode

| Signal | Width | Source | Destination | Description |
|--------|-------|--------|-------------|-------------|
| `id_pc` | 32 | IF/ID | `id_ex` | PC of instruction in ID |
| `id_instruction` | 32 | IF/ID | Control, RF, imm_gen | Raw instruction word |
| `id_rs1_addr`, `id_rs2_addr`, `id_rd_addr` | 5 each | Instruction fields | RF, HDU, `id_ex` | Register addresses |
| `id_rs1_data`, `id_rs2_data` | 32 | `register_file` (async read) | WB-forward mux, `id_ex` | Operand values from RF |
| `id_rs1_data_wb_fwd`, `id_rs2_data_wb_fwd` | 32 | WB-forward mux | `id_ex` | Operands with WB-to-ID forwarding applied |
| `id_imm` | 32 | `imm_gen` | `id_ex` | Sign-extended immediate |
| `id_ru_wr`, `id_imm_src`, `id_alua_src`, `id_alub_src`, `id_alu_op`, `id_br_op`, `id_dm_wr`, `id_dm_ctrl`, `id_ru_data_wr_src` | various | `control_unit` | `id_ex` | Decoded control signals |
| `id_trap_entry`, `id_mret_exec` | 1 | `control_unit` | `id_ex` | Trap/mret detection |
| `id_csr_addr`, `id_csr_wr`, `id_csr_op`, `id_csr_imm` | various | `control_unit` | `id_ex` | CSR control |
| `load_use_hazard` | 1 | `hazard_detection_unit` | Stall logic | Load in EX, consumer in ID |
| `stall` | 1 | `hazard_detection_unit` | PC, IF/ID, ID/EX | Pipeline hold |

**WB-to-ID forwarding:** The register file exposes the value written *this*
cycle at the WB mux output. Since the write is synchronous (occurs at
posedge), the combinational read of the same address would see the *old*
value. The WB-to-ID mux in `top_pipeline` selects `wb_rd_data` when the
register being read matches the register being written in WB, bypassing the
RF output (lines 293–296 of `top_pipeline.sv`).

### Stage EX - Execute

| Signal | Width | Source | Destination | Description |
|--------|-------|--------|-------------|-------------|
| `ex_pc` | 32 | ID/EX | ALU mux, EX/MEM | PC of instruction in EX |
| `ex_instruction` | 32 | ID/EX | EX/MEM | Raw instruction (for debug / 7-seg) |
| `ex_rs1_addr`, `ex_rs2_addr`, `ex_rd_addr` | 5 | ID/EX | Forwarding unit, EX/MEM | Register addresses |
| `ex_imm` | 32 | ID/EX | ALU B mux | Immediate |
| `ex_rs1_fwd`, `ex_rs2_fwd` | 32 | Forwarding mux | ALU, branch, DMEM | Forwarded operand values |
| `fwd_a_sel`, `fwd_b_sel` | 2 | `forwarding_unit` | Forward muxes | `00`=RF, `01`=MEM/WB, `10`=EX/MEM |
| `ex_alu_a`, `ex_alu_b` | 32 | ALU operand mux | `alu_rv32im` | Final ALU inputs |
| `ex_alu_result` | 32 | `alu_rv32im` | EX/MEM | ALU result / memory address / branch target |
| `ex_div_busy` | 1 | `alu_rv32im` | HDU, PC, registers | Stall: divisor active |
| `ex_div_done` | 1 | `alu_rv32im` | (internal) | Divisor complete pulse |
| `ex_branch_taken` | 1 | `branch_unit` | PC, IF/ID | Branch condition true |
| `ex_mask_pc_lsb` | 1 | `branch_unit` | EX stage | JALR: LSB masking |
| `ex_pc_plus4` | 32 | Combinational | EX/MEM | Return address for JAL/JALR |
| Control signals (ru_wr, dm_wr, dm_ctrl, br_op, ru_data_wr_src, alu_op, etc.) | various | ID/EX | EX/MEM | Propagated from decode |

The forwarding muxes (lines 422–437 of `top_pipeline.sv`) select:

- **`ex_rs1_fwd`** = `mem_alu_result` if EX/MEM produces the matching `ex_rs1_addr`
  (and `mem_ru_wr` is asserted and `mem_rd_addr ≠ x0`), else
  `wb_rd_data` if MEM/WB produces it, else `ex_rs1_data` (from ID/EX).
- **`ex_rs2_fwd`** follows the same priority for `ex_rs2_addr`.

The ALU A mux selects `ex_pc` for branches/JAL/AUIPC, `32'd0` for LUI,
or `ex_rs1_fwd` otherwise. The ALU B mux selects `ex_imm` for immediate
operands or `ex_rs2_fwd` for register operands.

### Stage MEM - Memory Access

| Signal | Width | Source | Destination | Description |
|--------|-------|--------|-------------|-------------|
| `mem_alu_result` | 32 | EX/MEM | DMEM, WB mux, EX --> forward | ALU result / effective address |
| `mem_rs2_data` | 32 | EX/MEM | `data_memory_pipe` | Store write data (forwarded from EX) |
| `mem_rd_addr` | 5 | EX/MEM | Forwarding unit, MEM/WB | Destination register |
| `mem_ru_wr` | 1 | EX/MEM | Forwarding unit, MEM/WB | Register write enable |
| `mem_dm_wr` | 1 | EX/MEM | `data_memory_pipe` | Data memory write enable |
| `mem_dm_ctrl` | 3 | EX/MEM | `data_memory_pipe` | funct3 - size/sign for loads |
| `mem_ru_data_wr_src` | 2 | EX/MEM | Forwarding unit, MEM/WB | Write-back source selector |
| `dmem_rd_data` | 32 | `data_memory_pipe` | WB mux (bypass) | Registered load data |
| `mem_instruction` | 32 | EX/MEM | MEM/WB | Raw instruction word |
| Control signals (trap_entry, mret_exec, csr_*, pc, pc_plus4) | various | EX/MEM | MEM/WB | Propagated from execute |

The data memory is synchronous. The registered output `dmem_rd_data` is
ready at the end of the MEM stage and feeds the WB writeback mux directly,
bypassing the MEM/WB register. This eliminates one cycle of load-use
latency: the load result is available for forwarding to EX (via MEM-->EX
forward) and for writeback to RF in the same WB cycle.

### Stage WB - Write Back

| Signal | Width | Source | Destination | Description |
|--------|-------|--------|-------------|-------------|
| `wb_alu_result` | 32 | MEM/WB | WB mux | ALU result (from previous stages) |
| `wb_rd_addr` | 5 | MEM/WB | `register_file` | Destination register address |
| `wb_ru_wr` | 1 | MEM/WB | Forwarding unit, RF | Register write enable |
| `wb_ru_data_wr_src` | 2 | MEM/WB | WB mux | Selects `WB_ALU`, `WB_MEM`, `WB_PC4`, or `WB_CSR` |
| `wb_pc_plus4` | 32 | MEM/WB | WB mux | Return address for JAL/JALR |
| `csr_rdata` | 32 | `csr_file` | WB mux | CSR read data |
| `dmem_rd_data` | 32 | `data_memory_pipe` (bypass) | WB mux | Load data |
| `wb_rd_data` | 32 | WB mux | `register_file` (write data) | Final write-back value |
| `wb_trap_entry`, `wb_mret_exec` | 1 | MEM/WB | CSR, flush logic | Trap/mret actions executed in WB |
| `wb_is_div` | 1 | Combinational | (gating) | Detects DIV/REM opcode in WB |

The writeback mux selects:
- `WB_ALU` (`00`): ALU result (R-type, I-type ALU, LUI, AUIPC)
- `WB_MEM` (`01`): Load data from data memory
- `WB_PC4` (`10`): Return address (JAL, JALR)
- `WB_CSR` (`11`): CSR read data

---

## Datapath by Instruction Class

The pipeline timing diagrams below use the following convention:

| Stage | Action |
|-------|--------|
| **IF** | `PC --> IMEM --> instruction` |
| **ID** | `Decode + RF read + imm gen` |
| **EX** | `ALU op + branch eval` |
| **MEM** | `DMEM access (load/store) / ALU result pass-through` |
| **WB** | `Write back to RF` |

### R-type (ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND)

```
Cycle N     IF: rs1_addr <= PC         [fetch ADD]
Cycle N+1   ID: decode ADD + read RF   [rs1_data, rs2_data]
Cycle N+2   EX: rs1 OP rs2             [alu_result = ADD]
Cycle N+3   MEM: pass-through           [alu_result --> MEM/WB next]
Cycle N+4   WB: RF[rd] <= alu_result   [commit]
```

No stall, no flush. **CPI = 1.**

### M-extension multiply (MUL, MULH, MULHSU, MULHU)

Same pipeline flow as R-type. The multiplier is combinational and completes
within the EX stage. **CPI = 1.**

### M-extension divide (DIV, DIVU, REM, REMU)

```
Cycle N     IF: fetch DIV
Cycle N+1   ID: decode + RF read
Cycle N+2   EX: DIV starts, div_busy↑ --> stall pipeline
              (DIV_IDLE --> DIV_RUNNING)
Cycles N+3..N+33  DIV in EX (31 RUNNING iterations + 1 DONE),
              div_busy held high
Cycle N+34  DIV_DONE --> DIV_IDLE, div_busy↓
            DIV advances to MEM
Cycle N+35  WB: RF[rd] <= alu_result   [commit]
```

The `div_busy` signal stalls the front-end stages (IF, ID) and holds
ID/EX and EX/MEM via the hazard detection unit. The divisor FSM within
the ALU advances through 33 states (1 IDLE-->RUNNING + 32 RUNNING iterations
--> DONE --> IDLE). **CPI = 34** per division instruction.

Corner cases (div-by-zero, signed overflow) are detected in DIV_IDLE
before the iterative algorithm begins. The FSM transitions directly to
DIV_DONE and returns to IDLE in 2 cycles, asserting `div_busy` for
only 2 cycles instead of 33. The sequential algorithm is a radix-2
restoring division (Weste & Harris, 2010, Section 11.4).

### I-type ALU (ADDI, SLTI, SLTIU, XORI, ORI, ANDI, SLLI, SRLI, SRAI)

```
Cycle N     IF: fetch ADDI
Cycle N+1   ID: decode + RF read
Cycle N+2   EX: rs1 OP imm             [alu_result]
Cycle N+3   MEM: pass-through
Cycle N+4   WB: RF[rd] <= alu_result   [commit]
```

**CPI = 1.**

### LUI / AUIPC

```
Cycle N     IF: fetch LUI
Cycle N+1   ID: decode
Cycle N+2   EX: 0 + imm (LUI) / PC + imm (AUIPC)  [alu_result]
Cycle N+3   MEM: pass-through
Cycle N+4   WB: RF[rd] <= alu_result               [commit]
```

For LUI, `alu_a_src = 10` (zero constant). For AUIPC, `alu_a_src = 01` (PC).

### JAL

```
Cycle N     IF: fetch JAL
Cycle N+1   ID: decode + RF read
Cycle N+2   EX: PC + J_imm --> alu_result (target), branch_taken↑
              IF flushes: next fetch from alu_result (branch target)
              ID/EX flushes: bubble inserted
Cycle N+3   IF: fetch at branch target
            ID: bubble (flushed in N+2)
            MEM: JAL passes through (alu_result)
Cycle N+4   WB: RF[rd] <= PC+4   [commit]
              (also: target instruction enters ID)
```

The taken branch in EX causes a single-cycle penalty: the instruction
fetched after the JAL is flushed, and the target is fetched in the next
cycle. Effective CPI = 2 for taken branches (1 nominal + 1 flush penalty).

### JALR

Same as JAL, but the target is computed as `rs1 + I_imm` and the LSB is
forced to zero ([ADR 006](../decisions/006_jalr_pc_masking.md)). JALR also
returns `PC+4` to `rd`.

### Conditional Branch (BEQ, BNE, BLT, BGE, BLTU, BGEU)

```
Cycle N     IF: fetch branch
Cycle N+1   ID: decode + compute offset
Cycle N+2   EX: compare rs1 vs rs2 + compute target PC+offset
              IF targets: if branch_taken --> fetch from alu_result
                           else --> sequential (pc+4) - already fetched
              ID/EX: bubble on taken branch only
Cycle N+3   IF: branch target (if taken) / sequential (if not)
            ID: bubble (if taken)
            MEM: branch passes through
```

**Not-taken: CPI = 1** (sequential fetch continues).  
**Taken: CPI = 2** (one flush penalty). See [ADR 038](../decisions/038_branch_resolution_ex_predict_not-taken.md).

### Load (LB, LH, LW, LBU, LHU)

```
Cycle N     IF: fetch LW
Cycle N+1   ID: decode + RF read
              IF: fetch instruction that CONSUMES LW (e.g., ADD rd' ← rd)
Cycle N+2   EX: rs1 + imm --> alu_result (effective address)
              IF: fetch the consumer - but load_use_hazard detected!
              load_use_hazard↑ --> stall IF/ID, insert ID/EX bubble
Cycle N+3   MEM: DMEM[alu_result] --> dmem_rd_data (if stall active)
              IF/ID: stalled (same consumer in ID)
Cycle N+4   EX: consumer in EX with fwd from MEM (fwd_a_sel = 2'b10)
              IF: fetch next instruction after consumer
              WB: RF[rd] <= dmem_rd_data   (load commits)
```

The load-use hazard inserts a one-cycle stall. The consumer in ID is
delayed by one cycle while the load advances to MEM, then the MEM-->EX
forwarding path supplies the loaded value to the consumer in EX.
**Effective CPI = 2 for load-use sequences.**

### Store (SB, SH, SW)

```
Cycle N     IF: fetch SW
Cycle N+1   ID: decode + RF read
Cycle N+2   EX: rs1 + imm --> alu_result (address)
Cycle N+3   MEM: DMEM[alu_result] <= rs2_data   [store commits]
Cycle N+4   WB: (no write-back, ru_wr = 0)
```

**CPI = 1.** Stores do not produce a result to forward, but they may
consume a forwarded value from MEM/WB.

---

## Forwarding Unit

The forwarding unit (`rtl/pipeline/forwarding_unit.sv`) resolves register
data hazards without stalling for ALU-to-ALU dependencies (Patterson &
Hennessy, 2017, Section 4.8; Harris & Harris, 2021, Section 7.5.1).

### Forwarding paths

| Forward path | Source stage | Destination | Selector | Condition |
|-------------|--------------|-------------|----------|-----------|
| EX/MEM --> EX | EX/MEM (`mem_alu_result`) | ALU input A/B | `fwd_a/b_sel = 2'b10` | `mem_ru_wr && rd≠x0 && rd==ex_rs1/2_addr` |
| MEM/WB --> EX | MEM/WB (`wb_rd_data`) | ALU input A/B | `fwd_a/b_sel = 2'b01` | `wb_ru_wr && rd≠x0 && rd==ex_rs1/2_addr` |
| WB --> ID | WB mux (`wb_rd_data`) | ID/EX input | combinatorial | `wb_ru_wr && rd≠x0 && rd==id_rs1/2_addr` |

### Priority

EX/MEM forwarding takes priority over MEM/WB when both stages hold results
for the same destination register (the younger producer is in EX/MEM). The
WB-->ID path is implemented as a combinatorial mux outside the forwarding
unit, directly in `top_pipeline.sv` (lines 293–296).

### Register x0 exclusion

All three forwarding paths explicitly exclude `rd = x0` because x0 is
hardwired to zero - forwarding a result to x0 is both unnecessary and
potentially incorrect if x0 is written inadvertently.

---

## Hazard Detection Unit

The hazard detection unit (`rtl/pipeline/hazard_detection.sv`) stalls the
pipeline for conditions that forwarding cannot resolve.

### Stall conditions

| Condition | Asserted when | Latency | Resolution |
|-----------|---------------|---------|------------|
| **Load-use hazard** | A load instruction is in EX (`ex_ru_data_wr_src == WB_MEM`) and its `rd` matches `id_rs1_addr` or `id_rs2_addr` | 1 cycle | Load advances to MEM while IF/ID is held; MEM-->EX forward supplies data |
| **MEM RAW hazard (load)** | A load instruction is in MEM (`mem_ru_data_wr_src == WB_MEM`) and its `rd` matches `id_rs1_addr` or `id_rs2_addr` | 1 cycle | Same mechanism - prevents load in MEM from being read stale by ID |
| **Division busy** | `div_busy` is asserted by the ALU | 34 cycles (normal) | All three front-end stages (IF, ID, EX) held; divisor FSM advances |
| **ALU RAW in MEM** | (never stalls) | 0 | Resolved by EX/MEM-->EX forwarding - no stall needed |

### The MEM RAW hazard guard

The `mem_raw_hazard` condition is restricted to load instructions only
(`mem_ru_data_wr_src == WB_MEM`). Without this guard, a back-to-back
sequence like AUIPC --> ADDI that writes and reads the same register would
assert `stall` forever - each copy of the AUIPC entering MEM re-triggers
the stall against the stalled copy of ADDI in ID, creating a permanent
deadlock ([ADR 041](../decisions/041_pipeline_data_hazard_limitation.md)).

### Flush conditions

| Flush | Source | Impact | Cycles lost |
|-------|--------|--------|-------------|
| Branch taken | EX (`ex_branch_taken`) | Flush IF/ID, redirect PC | 1 |
| Trap entry | WB (`wb_trap_entry`) | Flush IF/ID and EX/MEM, redirect PC to trap vector | 1 |
| MRET | WB (`wb_mret_exec`) | Same as trap flush | 1 |
| Load-use | HDU (`load_use_hazard`) | Flush ID/EX only (bubble), hold IF/ID and PC | 1 |

---

## Critical Path Analysis

The pipeline breaks the single-cycle combinational path across five
shorter stages. The critical path is determined by the **slowest stage**
(Patterson & Hennessy, 2017, Section 4.5; Harris & Harris, 2021,
Section 7.3):

**EX stage** - The execute stage includes the longest combinational path:

```
ID/EX register output (ex_alu_a, ex_alu_b)
  --> alu_rv32im (ADD: combinational adder for RV32I / DSP-block multiply for MUL)
  --> branch_unit (condition evaluation for branches)
  --> ex_alu_result / ex_branch_taken
  --> setup time of EX/MEM register
```

For MUL instructions, the DSP-block multiplication adds 2–3 levels of
DSP cascade, which may compete with the ALU adder path. The divisor path
does **not** appear on the critical path because it is implemented as a
multi-cycle FSM (Weste & Harris, 2010, Section 11.4).

**MEM stage** - The memory access adds the registered read delay of the
M10K block (for loads) or the write cycle (for stores). The registered
output `dmem_rd_data` is available at the MEM/WB setup time.

The empirical Fmax measured for the pipeline is **57.59 MHz** (Slow 85°C,
quartile-based, `IMEM_DEPTH=2048`, `DMEM_DEPTH=512`), compared to
**37.54 MHz** for the single-cycle on the same device. The 53 % higher
frequency reflects the shorter combinational paths per stage.

---

## Memory Implementation

The pipeline uses dedicated synchronous-read memory modules that map directly
to Intel Cyclone V M10K embedded memory blocks.

| Module | File | Type | Depth (synthesis) | Depth (simulation) | M10K blocks |
|--------|------|------|-------------------|--------------------|-------------|
| `instruction_memory_pipe` | `rtl/pipeline/instruction_memory_pipe.sv` | ROM (synchronous) | 2048 words | 16384 words | 64 |
| `data_memory_pipe` | `rtl/pipeline/data_memory_pipe.sv` | RAM (synchronous, 4 byte-lanes) | 512 words | 8192 words | 32 |

### Why synchronous read works for the pipeline

The five-stage pipeline inserts an **IF/ID pipeline register** between the
instruction memory output and the decode stage. This register captures the
instruction word on the rising clock edge of each cycle:

```
Cycle N:     [IF] PC --> IMEM --> address
             [ID] previous instruction decoded from IF/ID
             [EX] execute
             [MEM] memory access
             [WB] write-back

Cycle N+1:   [IF] next_pc --> IMEM --> address
             [ID] instruction captured by IF/ID at ↑clk
             ...
```

Because the instruction is sampled by IF/ID at the clock edge, the memory read
does not need to be combinational - it only needs to produce a stable value
before the next clock edge. This allows Quartus Prime to map the read to M10K
blocks, which internally clock the read operation (Intel Corporation, 2016,
Section 3-4).

The same reasoning applies to the data memory. Load data is produced by the
MEM stage and captured by the MEM/WB register at the end of the same cycle
(or used directly by the WB mux via the registered output bypass), so a
synchronous read is sufficient.

### M10K inference

The `instruction_memory_pipe.sv` module uses an `always_ff` block with a
`ramstyle = "M10K"` attribute:

```systemverilog
(* ramstyle = "M10K" *) logic [31:0] mem [0:IMEM_DEPTH-1];

always_ff @(posedge clk) begin
    mem_read <= mem[addr];
end
```

Quartus Prime infers M10K blocks in ROM mode when it detects this pattern.
The output can be either registered (with `OUTDATA_REG_A = "OUTPUT_REG"`) or
unregistered (`OUTDATA_REG_A = "UNREGISTERED"`). In the pipeline, the
registered output is acceptable because IF/ID captures one cycle later, and
the address mux for flushed instructions is handled combinationally before the
M10K address input.

The `data_memory_pipe.sv` module uses four independent 8-bit-wide arrays
(`mem_b0`…`mem_b3`) to enable byte-level write enables. Each array is
described with `always_ff` and drives a separate M10K block, giving Quartus
full control over byte-lane granularity. This technique infers 32 M10K blocks
(8 blocks per byte-lane at 8192 depth, proportionally less at 512 depth).

### Synthesis results

| Metric | Pipeline | Single-cycle (for comparison) |
|--------|----------|-------------------------------|
| M10K blocks | 96 (64 IMEM + 32 DMEM) | 0 |
| ALMs | ~2 100 | ~11 500 |
| Fmax (Slow 85°C) | 57.59 MHz | 37.54 MHz |

---

## Memory Parameters

| Parameter | Synthesis value | Simulation (cocotb) value | Notes |
|-----------|-----------------|---------------------------|-------|
| `IMEM_DEPTH` | 2048 words (8 KB) | 16384 words (64 KB) | Set via `.qsf` `set_parameter` for synthesis |
| `DMEM_DEPTH` | 512 words (2 KB) | 8192 words (32 KB) | Same mechanism |
| Reset vector | `0x00000000` | `0x00000000` | ADR 012 |

---

## Known Limitations and Explicit Exceptions

1. **CPI = 1 only for RV32I and M-extension multiply.**  
   DIV/DIVU/REM/REMU have effective CPI = 35 (1 fetch + 32 division + 1 stall
   release + 1 writeback) in the pipeline. Division corner cases (division by
   zero, signed overflow) are resolved in 2 cycles. This is the same multi-cycle
   divisor FSM used in the single-cycle design.

2. **Branch penalty of 1 cycle on taken branches.**  
   The pipeline predicts not-taken. A taken branch flushes the IF/ID register
   and redirects the PC, losing one cycle of work. This is the baseline penalty
   for a 5-stage pipeline with branch resolution in EX (Patterson & Hennessy,
   2017, Section 4.8).

3. **Load-use penalty of 1 cycle.**  
   An instruction that reads the result of a load in the immediately subsequent
   cycle incurs a one-cycle stall. This is a standard limitation of a 5-stage
   pipeline without a data-forwarding path from MEM to ID (Harris & Harris,
   2021, Section 7.5.1).

4. **No branch prediction.**  
   The pipeline uses a simple not-taken policy. No branch target buffer or
   branch history table is implemented.

5. **No exception or interrupt handling other than ECALL/EBREAK/MRET.**  
   The CSR file supports `ecall`, `ebreak`, and `mret` for trap handling.
   Other trap causes (illegal instruction, misaligned access) are not
   implemented. See [ADR 030](../decisions/030_csr_and_trap_handling.md) and
   the `EXPECTED_FAIL` list in `test_pipeline_rv32mi.py`.

6. **Misaligned loads/stores produce undefined results.**  
   Same limitation as the single-cycle design. No alignment exception is
   raised (ADR 020).

7. **No memory-mapped I/O.**  
   Both memories are plain synchronous RAM/ROM with no peripheral address
   decoding.

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
