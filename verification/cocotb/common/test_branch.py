"""
Instruction-level cocotb tests for the RV32I branch instructions.

These tests complement the RV32I ALU instruction tests in test_alu_rv32i.py
by exercising the branch unit one instruction at a time. Each test:

  1. Drives clk manually via the `step_clock` / `reset_dut` helpers
     imported from conftest (see "Clock and reset" in conftest.py).
  2. Sets the initial register state by writing directly to
     dut.u_rf.regs[k].
  3. Writes a single branch instruction into dut.u_imem.mem[0].
  4. Steps the clock once. The DUT fetches the instruction at PC=0,
     evaluates the branch condition, and updates the PC to either
     pc_plus4=4 (fall through) or alu_res=PC+imm (branch taken).
  5. Asserts that dut.u_pc.pc matches the expected value (4 for fall
     through, imm for branch taken).
  6. Asserts that no register was written, since branch instructions
     do not write back to the register file (the rd field in the
     encoding is unused and the DUT's ru_wr is 0 for OP_BRANCH).

The PC update path: the DUT's control_unit drives alua_src=ALUA_PC
and alub_src=1 with alu_op=ALU_ADD for OP_BRANCH, so alu_res = PC + imm
regardless of whether the branch is taken. The branch_unit produces the
single-bit `branch` signal based on rs1 vs rs2 and funct3, and the PC
module selects next_pc = (branch ? alu_res : pc_plus4). This means the
test's expected PC is either 4 (sequential) or imm (taken), with no
other possibilities.

The 13-bit branch immediate is sign-extended to 32 bits by the DUT's
imm_gen, so a negative offset (e.g., -8 encoded as 0x1FF8) yields
PC = 0xFFFFFFF8 in the test (since PC=0 at reset). The encoder
encode_b() below handles both positive and negative offsets correctly
via Python's arithmetic right shift and a final mask.

## Clock and reset

The cocotb 2.0 Clock + RisingEdge pattern is unreliable for
instruction-level tests (see the long comment in conftest.py and
ADR 034). The pattern used here is identical: start the cocotb Clock
(for the framework), then drive clk manually inside the test
coroutine via step_clock() and reset_dut(). The two are in sync at
10 ns periods; the manual drives win because the test coroutine
runs after the Clock coroutine yields on every Timer.

## Hierarchy access

Tests access dut.u_rf.regs, dut.u_imem.mem, and dut.u_pc.pc. These
are the instance/signal names in top_single_cycle.sv (u_rf = register
file, u_imem = instruction memory, u_pc = PC module). Icarus exposes
internal signals via VPI; other simulators may require promoting
these to top-level ports.
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut


# ──────────────────────────────────────────────────────────────────────
# Instruction encoders
# ──────────────────────────────────────────────────────────────────────

def encode_b(funct3, rs1, rs2, imm):
    """Encode a B-type (branch) instruction. imm is a 13-bit signed byte
    offset (with bit 0 = 0). Range: -4096 to +4094 in steps of 2.

    Layout of the 13-bit immediate in the 32-bit instruction word:
       bit 31     = imm[12]   (sign)
       bits 30:25 = imm[10:5]
       bits 11:8  = imm[4:1]
       bit  7     = imm[11]
       bit  0     = implicit 0 (not encoded; comes from imm[0])
    """
    imm12   = (imm >> 12) & 0x1
    imm11   = (imm >> 11) & 0x1
    imm10_5 = (imm >> 5)  & 0x3F
    imm4_1  = (imm >> 1)  & 0xF
    opcode  = 0b1100011
    return (imm12 << 31) | (imm10_5 << 25) | (rs2 << 20) | (rs1 << 15) \
         | (funct3 << 12) | (imm4_1 << 8) | (imm11 << 7) | opcode


# ──────────────────────────────────────────────────────────────────────
# Test driver
# ──────────────────────────────────────────────────────────────────────

# Standard offset used in most tests: branch to PC=0x100 if taken, else
# fall through to PC=4. The asymmetry (4 vs 0x100) makes the assertion
# trivial and self-documenting.
FORWARD_OFFSET = 0x100
BACKWARD_OFFSET = 0x1FF8  # -8 sign-extended to 13 bits


async def _setup_and_execute_branch(dut, instruction, initial_regs, expected_pc):
    """Reset the DUT, set up the initial state, execute one branch
    instruction, and assert that the PC matches `expected_pc` and that
    no register was written.

    initial_regs:  dict mapping register index to value (input operands)
    expected_pc:   32-bit value of PC after the branch executes
                   (4 for fall-through, imm for branch taken)
    """
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)

    # Initialise input registers and the instruction. regs[0] is
    # initialised explicitly because the DUT's reset loop is
    # `for (i=1; i<32; i++)` (see ADR 034).
    dut.u_rf.regs[0].value = 0
    for reg, value in initial_regs.items():
        if reg == 0:
            continue
        dut.u_rf.regs[reg].value = value
    dut.u_imem.mem[0].value = instruction

    await Timer(2, unit="ns")
    await step_clock(dut)

    # Assert the PC matches the expected value.
    actual_pc = int(dut.u_pc.pc.value)
    assert actual_pc == expected_pc, (
        f"PC: expected {expected_pc:#010x}, got {actual_pc:#010x}"
    )

    # Branch instructions must not write to any register. The DUT's
    # control_unit sets ru_wr=0 for OP_BRANCH, and the rd field in the
    # encoding is unused by the spec.
    for i in range(1, 32):
        if i in initial_regs:
            continue
        reg_val = int(dut.u_rf.regs[i].value)
        assert reg_val == 0, (
            f"x{i} was modified by a branch instruction (expected 0), got {reg_val:#010x}"
        )


# ──────────────────────────────────────────────────────────────────────
# BEQ tests
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_beq_equal_operands_taken(dut):
    """BEQ x1, x2, +0x100: branch taken when rs1 == rs2 (PC = 0x100)."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b000, 1, 2, FORWARD_OFFSET),  # BEQ x1, x2, +0x100
        initial_regs={1: 0xDEADBEEF, 2: 0xDEADBEEF},
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_beq_different_operands_not_taken(dut):
    """BEQ x1, x2, +0x100: branch not taken when rs1 != rs2 (PC = 4)."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b000, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0xDEADBEEF, 2: 0xCAFEBABE},
        expected_pc=4,
    )


@cocotb.test()
async def test_beq_zero_operands_taken(dut):
    """BEQ x0, x0, +0x100: branch always taken (0 == 0) — the canonical
    unconditional-branch idiom in RISC-V assembly."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b000, 0, 0, FORWARD_OFFSET),
        initial_regs={},
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_beq_max_operands_taken(dut):
    """BEQ x1, x2, +0x100: branch taken when both operands are 0xFFFFFFFF."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b000, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0xFFFFFFFF, 2: 0xFFFFFFFF},
        expected_pc=FORWARD_OFFSET,
    )


# ──────────────────────────────────────────────────────────────────────
# BNE tests
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_bne_different_operands_taken(dut):
    """BNE x1, x2, +0x100: branch taken when rs1 != rs2."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b001, 1, 2, FORWARD_OFFSET),  # BNE x1, x2, +0x100
        initial_regs={1: 0x00000000, 2: 0x00000001},
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_bne_equal_operands_not_taken(dut):
    """BNE x1, x2, +0x100: branch not taken when rs1 == rs2."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b001, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0x12345678, 2: 0x12345678},
        expected_pc=4,
    )


# ──────────────────────────────────────────────────────────────────────
# BLT tests (signed less-than)
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_blt_signed_less_than_taken(dut):
    """BLT x1, x2, +0x100: branch taken when signed x1 < signed x2.

    Here x1 = -1 (0xFFFFFFFF) and x2 = 0; -1 < 0 is true in signed
    comparison. This test catches the bug where BLT is implemented as
    unsigned < (in which case 0xFFFFFFFF < 0 is false)."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b100, 1, 2, FORWARD_OFFSET),  # BLT x1, x2, +0x100
        initial_regs={1: 0xFFFFFFFF, 2: 0x00000000},  # signed: -1 < 0
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_blt_signed_equal_not_taken(dut):
    """BLT x1, x2, +0x100: branch not taken when x1 == x2 (not strictly less)."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b100, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0x12345678, 2: 0x12345678},
        expected_pc=4,
    )


@cocotb.test()
async def test_blt_signed_greater_not_taken(dut):
    """BLT x1, x2, +0x100: branch not taken when signed x1 > signed x2."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b100, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0x00000005, 2: 0x00000003},  # 5 < 3 is false
        expected_pc=4,
    )


@cocotb.test()
async def test_blt_negative_lt_positive_taken(dut):
    """BLT x1, x2, +0x100: branch taken for negative < positive (signed)."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b100, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0xFFFFFFFF, 2: 0x00000001},  # -1 < 1
        expected_pc=FORWARD_OFFSET,
    )


# ──────────────────────────────────────────────────────────────────────
# BGE tests (signed greater-than-or-equal)
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_bge_signed_greater_taken(dut):
    """BGE x1, x2, +0x100: branch taken when signed x1 > signed x2."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b101, 1, 2, FORWARD_OFFSET),  # BGE x1, x2, +0x100
        initial_regs={1: 0x00000005, 2: 0x00000003},
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_bge_signed_equal_taken(dut):
    """BGE x1, x2, +0x100: branch taken when x1 == x2 (>= is true on equal)."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b101, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0x12345678, 2: 0x12345678},
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_bge_signed_less_not_taken(dut):
    """BGE x1, x2, +0x100: branch not taken when signed x1 < signed x2."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b101, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0x00000003, 2: 0x00000005},  # 3 >= 5 is false
        expected_pc=4,
    )


# ──────────────────────────────────────────────────────────────────────
# BLTU tests (unsigned less-than)
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_bltu_unsigned_less_taken(dut):
    """BLTU x1, x2, +0x100: branch taken when unsigned x1 < unsigned x2."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b110, 1, 2, FORWARD_OFFSET),  # BLTU x1, x2, +0x100
        initial_regs={1: 0x00000000, 2: 0xFFFFFFFF},  # 0 < 0xFFFFFFFF (unsigned)
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_bltu_signed_negative_treated_as_huge_taken(dut):
    """BLTU x1, x2, +0x100: when x1 is small positive and x2 is -1
    (0xFFFFFFFF), the unsigned comparison is 1 < 0xFFFFFFFF = true.
    This is the case where BLT and BLTU disagree (signed: 1 < -1 is
    false; unsigned: 1 < 0xFFFFFFFF is true)."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b110, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0x00000001, 2: 0xFFFFFFFF},
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_bltu_neg_not_less_than_positive_not_taken(dut):
    """BLTU x1, x2, +0x100: when x1 is -1 (0xFFFFFFFF) and x2 is small
    positive, the unsigned comparison is 0xFFFFFFFF < 1 = false.
    This confirms BLTU does NOT sign-extend its operands."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b110, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0xFFFFFFFF, 2: 0x00000001},
        expected_pc=4,
    )


# ──────────────────────────────────────────────────────────────────────
# BGEU tests (unsigned greater-than-or-equal)
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_bgeu_unsigned_greater_taken(dut):
    """BGEU x1, x2, +0x100: branch taken when unsigned x1 > unsigned x2."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b111, 1, 2, FORWARD_OFFSET),  # BGEU x1, x2, +0x100
        initial_regs={1: 0xFFFFFFFF, 2: 0x00000000},
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_bgeu_unsigned_equal_taken(dut):
    """BGEU x1, x2, +0x100: branch taken when x1 == x2 (>= is true on equal)."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b111, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0xCAFEBABE, 2: 0xCAFEBABE},
        expected_pc=FORWARD_OFFSET,
    )


@cocotb.test()
async def test_bgeu_unsigned_less_not_taken(dut):
    """BGEU x1, x2, +0x100: branch not taken when unsigned x1 < unsigned x2."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b111, 1, 2, FORWARD_OFFSET),
        initial_regs={1: 0x00000001, 2: 0xFFFFFFFF},  # 1 >= 0xFFFFFFFF is false
        expected_pc=4,
    )


# ──────────────────────────────────────────────────────────────────────
# Backward branch (negative immediate)
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_branch_backward_negative_offset_taken(dut):
    """BGE x0, x0, -8: branch always taken (0 >= 0); PC = 0 + (-8) = 0xFFFFFFF8.

    Tests the sign-extension of a negative branch offset through the
    DUT's imm_gen. With PC=0 at reset, the backward branch target wraps
    to 0xFFFFFFF8, which is the expected PC."""
    await _setup_and_execute_branch(
        dut,
        instruction=encode_b(0b101, 0, 0, -8),  # BGE x0, x0, -8
        initial_regs={},
        expected_pc=0xFFFFFFF8,
    )
