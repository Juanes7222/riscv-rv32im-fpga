# ADR 021 — Data Memory: Word-Addressed Organization with Byte Enables

**Status:** Accepted  
**Date:** 2026-05-02

## Context

The RV32I ISA is byte-addressable and requires data memory to support byte
(LB/SB), halfword (LH/SH), and word (LW/SW) accesses at arbitrary naturally
aligned addresses. The memory array must be organized to support these access
widths efficiently on Cyclone V M10K blocks.

## Decision

**1. The memory array is word-addressed:** the internal array is
`logic [31:0] mem [0:DMEM_DEPTH-1]` where `DMEM_DEPTH = 8192`. The word
address is `dm_addr[14:2]`; bits `[1:0]` select the byte or halfword within
the word and are used only for sub-word access logic, not for array indexing.

**2. Writes use byte enables:** a 4-bit byte enable signal `be[3:0]` is
generated combinationally from `dm_ctrl` and `dm_addr[1:0]`. Only the
enabled byte lanes are written to the memory array on the rising clock edge.

**3. Write data is replicated before the memory array:** `rs2_data` is
replicated across all four byte positions before being presented to the
write port. Byte enables select which bytes are actually stored.

**4. Read data extraction and extension are combinational logic outside
the M10K array:** the full 32-bit word is always read; a combinational
block selects the correct byte or halfword and applies sign or zero extension
according to `dm_ctrl`.

**5. Natural alignment is assumed.** No misalignment detection or exception
logic is implemented.

## Rationale

**Word-addressed array:**  
M10K blocks are most efficiently used with a fixed data width. A 32-bit wide
array uses 4 M10K blocks for 32 KB and maps directly to the M10K's native
32-bit port width. Byte-addressed organization (four 8-bit banks) would also
use 4 M10K blocks but requires more complex address routing and read muxing.
The word-addressed approach is simpler and produces equivalent resource usage.

**Byte enables for sub-word writes:**  
M10K simple dual-port blocks on Cyclone V support per-byte write enables
natively (`byteena_a`). Using byte enables is more efficient than a
read-modify-write sequence (which would require an extra clock cycle and a
combinational feedback path from the read port to the write data).

**Write data replication:**  
Replicating the write data to all byte positions (`{rs2[7:0], rs2[7:0], rs2[7:0], rs2[7:0]}`
for SB; `{rs2[15:0], rs2[15:0]}` for SH) decouples the write data path from
the address offset. The byte enables handle positioning. This approach
eliminates a barrel shifter on the write path and is the canonical FPGA
implementation strategy for byte-enable memories.

**Read extraction outside M10K:**  
Sign and zero extension cannot be performed inside an M10K block. The
extraction-and-extension combinational block is a natural fit for the module
wrapper around the M10K instance, keeping the M10K instance clean and the
extension logic visible and testable.

**Natural alignment:**  
The riscv-tests suite uses only naturally aligned accesses. Supporting
misaligned accesses would require a multi-cycle state machine that crosses
word boundaries, adding significant complexity with no benefit to the
experimental comparison. The RISC-V privileged specification allows
implementations to raise a misalignment exception; this implementation
silently produces undefined results for misaligned accesses, which is
acceptable for a processor that will only execute test programs known to be
correctly aligned.

## Byte Enable Truth Table

| Instruction | `dm_addr[1:0]` | `be[3:0]` |
|-------------|----------------|-----------|
| SW | xx | `4'b1111` |
| SH | 2'b00 | `4'b0011` |
| SH | 2'b10 | `4'b1100` |
| SB | 2'b00 | `4'b0001` |
| SB | 2'b01 | `4'b0010` |
| SB | 2'b10 | `4'b0100` |
| SB | 2'b11 | `4'b1000` |

## Read Extension Truth Table

| Instruction | Extracted bits | Operation |
|-------------|---------------|-----------|
| LW | `mem_word[31:0]` | Pass through |
| LH `addr[1]=0` | `mem_word[15:0]` | Sign-extend to 32 bits |
| LH `addr[1]=1` | `mem_word[31:16]` | Sign-extend to 32 bits |
| LHU `addr[1]=0` | `mem_word[15:0]` | Zero-extend to 32 bits |
| LHU `addr[1]=1` | `mem_word[31:16]` | Zero-extend to 32 bits |
| LB `addr[1:0]=00` | `mem_word[7:0]` | Sign-extend to 32 bits |
| LB `addr[1:0]=01` | `mem_word[15:8]` | Sign-extend to 32 bits |
| LB `addr[1:0]=10` | `mem_word[23:16]` | Sign-extend to 32 bits |
| LB `addr[1:0]=11` | `mem_word[31:24]` | Sign-extend to 32 bits |
| LBU `addr[1:0]=00` | `mem_word[7:0]` | Zero-extend to 32 bits |
| LBU `addr[1:0]=01` | `mem_word[15:8]` | Zero-extend to 32 bits |
| LBU `addr[1:0]=10` | `mem_word[23:16]` | Zero-extend to 32 bits |
| LBU `addr[1:0]=11` | `mem_word[31:24]` | Zero-extend to 32 bits |

## Consequences

- `data_memory.sv` contains no M10K-specific primitives. It uses a standard
  SystemVerilog array with byte enables; Quartus infers the M10K blocks
  automatically from the array size and access pattern.
- The module is shared between both microarchitectures without modification.
- The combinational read extraction block is part of the critical load
  instruction path: `ALU → data_memory → (extract+extend) → wb_mux`.
  Its depth is 1 mux level (byte/halfword selection) plus 1 sign-extension
  operation — typically 1–2 LUT levels.
- Misaligned accesses produce undefined results. No exception is raised.
  This must be noted in the experimental protocol.
