# ADR 030 - CSR File and Minimal Trap Handling (ECALL / MRET)

**Status:** Accepted (updated 2026-06-12 - CSR register file extended with mscratch, misa, mhartid, mimpid, marchid, mvendorid, mcounteren, mtval per ADR 033)
**Date:** 2026-06-11
**Depends on:** ADR 022 (control unit), ADR 027 (riscv-tests boot flow), ADR 028 (tohost convention)
**Supersedes:** the implicit assumption in ADR 022, ADR 027, and ADR 028 that `ecall` is a NOP.

---

## Context

ADR 022, ADR 027 and ADR 028 state that the processor does not implement
`ecall`, and that the riscv-tests `env/p/` framework writes the pass/fail code
directly to `tohost`. This is **incorrect**. Investigation of a timeout
failure in the cocotb test suite (June 2026) revealed that `env/p/` uses
`ecall` as the pass/fail signalling mechanism and never writes to `tohost`
through normal sequential code execution.

The actual flow encoded in `verification/riscv-tests/env/p/riscv_test.h`
(lines 262-267, 183-249) is:

```asm
; RVTEST_PASS
fence
li TESTNUM, 1          ; gp = 1
li a7, 93              ; a7 = 93
li a0, 0
ecall                  ; <- signals completion
```

```asm
; trap_vector (in RVTEST_CODE_BEGIN)
trap_vector:
    csrr t5, mcause
    li t6, CAUSE_USER_ECALL      ; 0x8
    beq t5, t6, write_tohost
    ...
write_tohost:
    sw TESTNUM, tohost, t5
    sw zero, tohost + 4, t5
    j write_tohost                ; infinite loop
```

The `tohost` write only happens **inside the trap handler**. A processor
that treats `ecall` as a NOP never enters the trap handler, never writes
to `tohost`, and the cocotb monitor times out after 200,000 cycles.

This was confirmed empirically: parsing the VCD of a failing run showed
`dm_wr` was never asserted across the entire 200,000-cycle simulation,
and the PC eventually drifted to out-of-bounds addresses (0x613e0+)
because the boot code after the ECALL NOP falls into the trap dispatcher
and walks random handler paths.

The boot code also relies on `mret` to enter user mode after writing
`mepc` with the test entry address. Treating `mret` as a NOP means the
processor does not jump to the test entry point, but in practice the
test code is laid out immediately after `mret` in memory, so sequential
execution still reaches it. This masks the missing MRET handling until
the ECALL issue is fixed.

---

## Decision

The single-cycle processor implements a **minimal machine-mode CSR file
and trap mechanism** sufficient to run riscv-tests `env/p/`:

### New module: `rtl/shared/csr_file.sv`

Holds four CSRs (reset values per RISC-V Privileged Spec):

| CSR    | Address | Width | Reset  | Purpose                                  |
|--------|---------|-------|--------|------------------------------------------|
| mstatus| 0x300   | 32    | 0x1800 | MPP[12:11] = 2'b11 (M-mode)              |
| mtvec  | 0x305   | 32    | 0x0    | Trap vector base address                 |
| mepc   | 0x341   | 32    | 0x0    | Saved PC on trap entry                   |
| mcause | 0x342   | 32    | 0x0    | Trap cause (bit 31 = 0 for exceptions)   |

The module supports:

- **CSR read instructions** (CSRRW, CSRRS, CSRRC, CSRRWI, CSRRSI, CSRRCI).
  For CSRRS/CSRRC with `rs1 = x0` the CSR is not written (RISC-V spec).
  The top-level muxes `csr_wdata` between `rs1_data` and the zero-extended
  5-bit immediate (zimm) from `instruction[19:15]`.
- **Trap entry (ECALL/EBREAK)**: captures `mepc = trap_pc4` and
  `mcause = {1'b0, 26'b0, trap_cause}`. The cause is derived from
  `mstatus.MPP`: 8 for U-mode, 9 for S-mode, 11 for M-mode.
- **Trap exit (MRET)**: `mstatus.MPP` is restored to `2'b00` (U-mode).
  Per the spec, MIE should also be restored from MPIE; this is left
  as future work (ADR 030 limit).
- **Combinational read** of all four CSRs (the read is available
  immediately on the cycle after the write edge - sufficient because
  the trap handler reads mcause one full cycle after the ECALL that
  set it).

### Modifications to existing modules

| Module                 | Change |
|------------------------|--------|
| `control_unit.sv`      | Adds `instr_31_20` input, `trap_entry`, `mret_exec`, `csr_addr`, `csr_wr_raw`, `csr_op`, `csr_imm` outputs. ECALL/EBREAK/MRET decoded from `instr_31_20` when `funct3 == 000`. CSR instructions produce the CSR control signals. `csr_op` is computed as `funct3[1:0] - 2'b01` to map 001-->00 (CSRRW), 010-->01 (CSRRS), 011-->10 (CSRRC) and the immediate-form equivalents. |
| `pc.sv`               | Adds `trap_entry`, `mret_exec`, `trap_target`, `mepc_value` inputs. `next_pc` priority becomes: `trap_entry ? trap_target : mret_exec ? mepc_value : branch ? branch_target : pc_plus4`. |
| `top_single_cycle.sv` | Instantiates `csr_file`. `rd_data` mux gains a `WB_CSR = 2'b11` source. `csr_wdata` is muxed between `rs1_data` and zimm based on `csr_imm`. `csr_wr` is gated off for CSRRS/CSRRC with `rs1_addr == 0`. The `opcode == OP_SYSTEM` special case in the old writeback mux is removed. |
| `verification/cocotb/common/Makefile` | Adds `csr_file.sv` to `VERILOG_SOURCES`. |

### Limitations (deliberate, ADR 030 scope)

- **No interrupt support.** `mstatus.MIE` and `mip` are not implemented.
  Trap entry only fires for synchronous exceptions (ECALL/EBREAK). Timer
  and software interrupts are not triggered.
- **mtvec.MODE** is forced to `2'b00` (direct). Vectored mode is
  unsupported.
- **No exception code distinction beyond ECALL.** Illegal-instruction
  traps, misaligned access traps, page faults, etc. are not produced.
- **No sret / uret / wfi.** Only MRET is decoded; the other
  `funct12` values in `OP_SYSTEM` with `funct3 == 000` are NOPs.
- **No atomic CSR operations.** CSRRS/CSRRC read-modify-write is
  implemented as a single combinational step. If a CSR is read and
  written in the same cycle by different sources, the trap entry
  path has priority for mepc/mcause; the CSR instruction write has
  priority for the addressed CSR (mstatus/mtvec).

---

## Rationale

The minimal subset was selected by tracing the exact instructions
emitted by the riscv-tests `env/p/` boot code:

1. `csrw mtvec, t0`     --> requires CSRRW write to mstatus-class CSR.
2. `csrw mstatus, t0`   --> CSRRW write to mstatus, sets MPP.
3. `csrw mepc, t0`      --> CSRRW write to mepc.
4. `mret`               --> must jump to mepc.
5. `csrr t5, mcause`    --> CSRRS read with rs1=x0, read-only.
6. `ecall`              --> must trap to mtvec with mcause=8, mepc=PC+4.
7. `sw TESTNUM, tohost` --> already implemented via standard store path.

Any implementation that satisfies 1-7 is sufficient for the
verification goal of running rv32ui/rv32um instruction tests. The
narrowest such implementation is the four CSRs above plus the trap
redirect logic.

---

## Normative RTL Specification

### Module interface - `csr_file.sv`

```systemverilog
module csr_file (
    input  logic        clk,
    input  logic        rst_n,

    input  logic [11:0] csr_addr,
    input  logic [31:0] csr_wdata,
    input  logic        csr_wr,
    input  logic [1:0]  csr_op,
    output logic [31:0] csr_rdata,

    input  logic        trap_entry,
    input  logic [31:0] trap_pc4,

    input  logic        mret_exec,

    output logic [31:0] trap_target,
    output logic [31:0] mepc_value
);
```

### PC redirect priority - `pc.sv`

```systemverilog
assign next_pc = trap_entry ? trap_target :
                 mret_exec  ? mepc_value  :
                 branch     ? branch_target : pc_plus4;
```

### Control unit decode - `control_unit.sv`

For `OP_SYSTEM` with `funct3 == 3'b000`:

| instr_31_20 | trap_entry | mret_exec | Notes                       |
|-------------|------------|-----------|-----------------------------|
| 12'h000     | 1          | 0         | ECALL                       |
| 12'h001     | 1          | 0         | EBREAK (treated as ECALL)   |
| 12'h302     | 0          | 1         | MRET                        |
| other       | 0          | 0         | NOP (WFI, etc.)             |

For `OP_SYSTEM` with `funct3 != 3'b000`:
`ru_wr = 1`, `ru_data_wr_src = WB_CSR`, `csr_addr = instr_31_20`,
`csr_wr_raw = 1`, `csr_op = funct3[1:0] - 2'b01`, `csr_imm = funct3[2]`.

The top-level further gates `csr_wr = csr_wr_raw & ~((funct3 inside
{3'b010,3'b011}) & (rs1_addr == 0))` to suppress writes for read-only
CSRRS/CSRRC.

---

## Consequences

- **All riscv-tests pass.** The cocotb `test_rv32i_*` and `test_rv32m_*`
  tests now pass in the same number of cycles as the assembly code
  expects (well under 200,000).
- **Pipeline update required.** The pipeline implementation must
  replicate the same CSR/trap logic. See `rtl/pipeline/` (future
  iteration, not part of this ADR).
- **`ecall`/`mret` are no longer NOPs.** ADR 022 §"M-Extension Decode
  Note" must be updated to reflect this; the rest of ADR 022 (decode
  rules, R-type / M-extension, alua_src) is unaffected.
- **Boot code behaviour.** With CSR support, the riscv-tests boot code
  actually transitions M-mode --> U-mode via `mret` and triggers a real
  trap on `ecall`. PC now follows the documented RISC-V path rather
  than falling through sequentially.
- **No synthesis impact estimate yet.** The csr_file adds 4 x 32-bit
  registers plus modest combinational logic. Fmax impact is expected
  to be negligible.
