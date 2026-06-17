"""
Instruction-level cocotb tests for the RV32I ALU operations.

These tests exercise the ALU instructions one at a time, bypassing
the riscv-tests ELF loading infrastructure. Each test:

  1. Drives clk manually via the `step_clock` / `reset_dut` helpers
     imported from conftest (the cocotb Clock + RisingEdge pattern
     interferes with the register/imem deposits needed for
     instruction-level tests — see the "Clock and reset" section
     in conftest.py and ADR 034).
  2. Sets the initial register state by writing directly to
     dut.u_rf.regs[k] (the register file instance in top_single_cycle).
  3. Writes a single instruction into dut.u_imem.mem[0].
  4. Steps the clock once, which triggers the DUT to fetch the
     instruction at PC=0, execute it, and write the result back
     to the destination register.
  5. Reads the destination register via dut.u_rf.regs[rd] and
     asserts it equals the expected value (computed from the ISA
     spec).
  6. Asserts that all other registers (except those set as inputs)
     are 0, catching accidental writes.

This style complements the riscv-tests suite (test_rv32i.py):
  - riscv-tests verifies that a complete program produces the
    correct result. Failures are coarse: you know "test 23 in xor.elf
    failed" but not which operand pair.
  - These instruction-level tests verify one specific instruction
    scenario at a time. Failures are fine-grained: you know
    "ADD with overflow returns the wrong value" immediately.

Both layers are needed for thesis Objective 1: the riscv-tests
prove ISA conformance, and these tests prove the DUT produces
the right results for individual operations.

## Clock and reset

Uses the manual clock driver pattern (`step_clock`, `reset_dut`)
imported from conftest.py. The cocotb Clock is also started via
`start_clock(dut)` so the framework knows about the clock signal,
but the manual toggles win because the test coroutine runs after
the Clock coroutine yields on every Timer.

The riscv-tests layer (test_rv32i.py, test_rv32m.py, test_rv32mi.py)
does NOT have this problem because it uses `monitor_tohost` to
wait for a tohost write — the cocotb Clock + RisingEdge pattern
works fine for that style of test.

## Hierarchy access

Tests access dut.u_rf.regs, dut.u_imem.mem, dut.u_dmem.mem, and
dut.u_pc.pc. These are the instance names in top_single_cycle.sv.
This is Icarus-friendly; switching to a different simulator would
require updating the helper layer.
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut


# ──────────────────────────────────────────────────────────────────────
# Instruction encoders
# ──────────────────────────────────────────────────────────────────────

def encode_r(funct7, rs2, rs1, funct3, rd):
    """Encode an R-type instruction (OP_REG opcode 0b0110011)."""
    return (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | 0b0110011


def encode_i(imm12, rs1, funct3, rd, opcode=0b0010011):
    """Encode an I-type ALU instruction. The 12-bit immediate is sign-extended
    to 32 bits by the DUT before use; the encoder stores it as a raw 12-bit
    value (the bit-11 sign bit goes in bit-31 of the encoding)."""
    imm12 &= 0xFFF
    return (imm12 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def encode_u(imm20, rd, opcode):
    """Encode a U-type instruction. imm20 occupies bits 31:12 of the encoding."""
    imm20 &= 0xFFFFF
    return (imm20 << 12) | (rd << 7) | opcode


# ──────────────────────────────────────────────────────────────────────
# Test driver
# ──────────────────────────────────────────────────────────────────────

async def _setup_and_execute(dut, instruction, initial_regs=None,
                              dest_reg=None, expected_value=None):
    """Reset the DUT, set up the initial state, execute one instruction,
    and assert the result plus the no-side-effect invariant.

    initial_regs:    dict mapping register index to value (x0 is always 0)
    dest_reg:        destination register of the instruction under test
    expected_value:  expected 32-bit value of dest_reg after execution
    """
    initial_regs = initial_regs or {}

    # 0. Start the cocotb Clock (needed by the framework). The Clock
    #    also toggles the clock in the background; the manual step_clock
    #    calls in the test coroutine race with the Clock but the
    #    manual drives win because the test coroutine runs after
    #    the Clock yields on every Timer.
    await start_clock(dut)

    # 1. Assert reset and hold for 2 cycles. The DUT resets all regs
    #    to 0 and the PC to 0.
    await reset_dut(dut, hold_cycles=2)

    # 2. Set the input state and the instruction while rst_n is high
    #    (deasserted) but no clock edge has fired yet. The deposits
    #    are applied at the next simulator event, which is the next
    #    clock edge in the manual clock driver.
    #
    #    Note: regs[0] is explicitly initialised to 0 here because the
    #    DUT's reset loop starts at i=1 (`for (i=1; i<32; i++)`),
    #    leaving regs[0] at its X default. The hardwired read port
    #    returns 0 for x0 regardless, but the test reads the internal
    #    storage directly, so it needs to be 0 for the assertion
    #    on x0 (e.g. "writes to x0 are ignored") to work.
    dut.u_rf.regs[0].value = 0
    for reg, value in initial_regs.items():
        if reg == 0:
            continue
        dut.u_rf.regs[reg].value = value
    dut.u_imem.mem[0].value = instruction

    # 2b. Give the simulator time to apply the deposits before the
    #     next clock edge. Without this, the DUT may sample the
    #     pre-deposit (X) values at the rising edge.
    await Timer(2, unit="ns")

    # 3. Step the clock once. This is the cycle that exits reset
    #    (rst_n=1 was already set by reset_dut), fetches the instruction
    #    at PC=0, executes it, and writes the result to dest_reg.
    await step_clock(dut)

    # 4. Assert the destination register holds the expected value.
    if dest_reg is not None:
        actual = int(dut.u_rf.regs[dest_reg].value)
        assert actual == expected_value, (
            f"x{dest_reg}: expected {expected_value:#010x}, got {actual:#010x}"
        )

    # 5. Assert that no other register was modified. Every register
    #    that was not set as an input and that is not the destination
    #    must be exactly 0. x0 is excluded because the register file
    #    never initialises regs[0] (its reset loop is `for (i=1; i<32; i++)`),
    #    so the internal storage is X even after reset — but the read
    #    port is hardwired to return 0 for x0, which is the
    #    architecturally-meaningful value.
    for i in range(1, 32):
        if i == dest_reg:
            continue
        if i in initial_regs:
            continue
        reg_val = int(dut.u_rf.regs[i].value)
        assert reg_val == 0, (
            f"x{i} was modified (expected 0), got {reg_val:#010x}"
        )


# ──────────────────────────────────────────────────────────────────────
# ADD tests
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_add_positive_operands(dut):
    """ADD x1, x2, x3: x1 = x2 + x3 for two positive 32-bit operands, no overflow."""
    a, b = 0x12345678, 0x9ABCDEF0
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x0, 1),  # ADD x1, x2, x3
        initial_regs={2: a, 3: b},
        dest_reg=1,
        expected_value=(a + b) & 0xFFFFFFFF,
    )


@cocotb.test()
async def test_add_unsigned_overflow_wraps(dut):
    """ADD x1, x2, x3: x1 = (x2 + x3) mod 2^32 when the sum overflows unsigned."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x0, 1),
        initial_regs={2: 0xFFFFFFFF, 3: 0x00000001},
        dest_reg=1,
        expected_value=0x00000000,  # 0xFFFFFFFF + 1 = 0x1_00000000 → truncates to 0
    )


@cocotb.test()
async def test_add_signed_overflow_wraps(dut):
    """ADD x1, x2, x3: signed overflow also wraps (e.g., INT_MAX + 1 = INT_MIN)."""
    # 0x7FFFFFFF + 0x00000001 = 0x80000000 = INT_MIN in two's complement.
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x0, 1),
        initial_regs={2: 0x7FFFFFFF, 3: 0x00000001},
        dest_reg=1,
        expected_value=0x80000000,
    )


@cocotb.test()
async def test_add_zero_operands(dut):
    """ADD x1, x2, x3: x1 = x2 when x3 = 0."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x0, 1),
        initial_regs={2: 0xDEADBEEF, 3: 0x00000000},
        dest_reg=1,
        expected_value=0xDEADBEEF,
    )


@cocotb.test()
async def test_add_writes_to_x0_are_ignored(dut):
    """ADD x0, x1, x2: writes to x0 are silently ignored per the ISA spec."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 2, 1, 0x0, 0),  # ADD x0, x1, x2
        initial_regs={1: 0x12345678, 2: 0x9ABCDEF0},
        dest_reg=0,           # x0 is the destination
        expected_value=0,     # x0 stays 0
    )


# ──────────────────────────────────────────────────────────────────────
# SUB tests
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_sub_positive_result(dut):
    """SUB x1, x2, x3: x1 = x2 - x3 when x2 > x3 (positive result)."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x20, 3, 2, 0x0, 1),  # SUB x1, x2, x3
        initial_regs={2: 0x0000000A, 3: 0x00000003},
        dest_reg=1,
        expected_value=0x00000007,
    )


@cocotb.test()
async def test_sub_negative_result(dut):
    """SUB x1, x2, x3: x1 = x2 - x3 when x2 < x3 (negative result, two's complement)."""
    # 3 - 10 = -7 = 0xFFFFFFF9 in unsigned 32-bit.
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x20, 3, 2, 0x0, 1),
        initial_regs={2: 0x00000003, 3: 0x0000000A},
        dest_reg=1,
        expected_value=0xFFFFFFF9,
    )


@cocotb.test()
async def test_sub_zero_result(dut):
    """SUB x1, x2, x3: x1 = 0 when x2 == x3."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x20, 3, 2, 0x0, 1),
        initial_regs={2: 0xDEADBEEF, 3: 0xDEADBEEF},
        dest_reg=1,
        expected_value=0x00000000,
    )


# ──────────────────────────────────────────────────────────────────────
# Logical tests (AND, OR, XOR)
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_and_with_mask(dut):
    """AND x1, x2, x3: x1 = x2 & x3."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x7, 1),  # AND x1, x2, x3
        initial_regs={2: 0xF0F0F0F0, 3: 0x33333333},
        dest_reg=1,
        expected_value=0x30303030,
    )


@cocotb.test()
async def test_and_with_zero(dut):
    """AND x1, x2, x3: x1 = 0 when x3 = 0."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x7, 1),
        initial_regs={2: 0xFFFFFFFF, 3: 0x00000000},
        dest_reg=1,
        expected_value=0x00000000,
    )


@cocotb.test()
async def test_or_with_mask(dut):
    """OR x1, x2, x3: x1 = x2 | x3."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x6, 1),  # OR x1, x2, x3
        initial_regs={2: 0xF0F0F0F0, 3: 0x33333333},
        dest_reg=1,
        expected_value=0xF3F3F3F3,
    )


@cocotb.test()
async def test_or_with_zero(dut):
    """OR x1, x2, x3: x1 = x2 when x3 = 0 (OR is a no-op)."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x6, 1),
        initial_regs={2: 0xDEADBEEF, 3: 0x00000000},
        dest_reg=1,
        expected_value=0xDEADBEEF,
    )


@cocotb.test()
async def test_xor_with_mask(dut):
    """XOR x1, x2, x3: x1 = x2 ^ x3."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x4, 1),  # XOR x1, x2, x3
        initial_regs={2: 0xAAAAAAAA, 3: 0x55555555},
        dest_reg=1,
        expected_value=0xFFFFFFFF,
    )


@cocotb.test()
async def test_xor_with_self_is_zero(dut):
    """XOR x1, x2, x2: x1 = 0 (XOR is its own inverse)."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 2, 2, 0x4, 1),  # XOR x1, x2, x2
        initial_regs={2: 0xDEADBEEF},
        dest_reg=1,
        expected_value=0x00000000,
    )


# ──────────────────────────────────────────────────────────────────────
# Shift tests (SLL, SRL, SRA)
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_sll_left_shift(dut):
    """SLL x1, x2, x3: x1 = x2 << (x3 & 0x1F)."""
    # 0x00000001 << 4 = 0x00000010
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x1, 1),  # SLL x1, x2, x3
        initial_regs={2: 0x00000001, 3: 4},
        dest_reg=1,
        expected_value=0x00000010,
    )


@cocotb.test()
async def test_sll_shift_by_31(dut):
    """SLL x1, x2, x3: shifting 1 by 31 yields 0x80000000 (MSB in bit 31)."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x1, 1),
        initial_regs={2: 0x00000001, 3: 31},
        dest_reg=1,
        expected_value=0x80000000,
    )


@cocotb.test()
async def test_srl_right_shift(dut):
    """SRL x1, x2, x3: x1 = x2 >> (x3 & 0x1F), zero-filled (logical)."""
    # 0x80000000 >> 4 = 0x08000000 (zero-filled, MSB is shifted out, not sign-extended).
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x5, 1),  # SRL x1, x2, x3
        initial_regs={2: 0x80000000, 3: 4},
        dest_reg=1,
        expected_value=0x08000000,
    )


@cocotb.test()
async def test_sra_arithmetic_shift_sign_extends(dut):
    """SRA x1, x2, x3: x1 = x2 >> (x3 & 0x1F), sign-filled (arithmetic)."""
    # 0x80000000 (= INT_MIN) >> 4 sign-extended = 0xF8000000.
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x20, 3, 2, 0x5, 1),  # SRA x1, x2, x3
        initial_regs={2: 0x80000000, 3: 4},
        dest_reg=1,
        expected_value=0xF8000000,
    )


@cocotb.test()
async def test_sra_negative_stays_negative(dut):
    """SRA x1, x2, x3: shifting -1 right by any amount yields -1 (all-ones)."""
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x20, 3, 2, 0x5, 1),
        initial_regs={2: 0xFFFFFFFF, 3: 5},
        dest_reg=1,
        expected_value=0xFFFFFFFF,
    )


# ──────────────────────────────────────────────────────────────────────
# Comparison tests (SLT, SLTU)
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_slt_signed_less_than(dut):
    """SLT x1, x2, x3: x1 = 1 if signed x2 < x3 else 0."""
    # -1 < 0 (signed) -> 1
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x2, 1),  # SLT x1, x2, x3
        initial_regs={2: 0xFFFFFFFF, 3: 0x00000000},  # -1, 0
        dest_reg=1,
        expected_value=1,
    )


@cocotb.test()
async def test_slt_signed_not_less_than(dut):
    """SLT x1, x2, x3: 0x7FFFFFFF (INT_MAX) is not less than 0x80000000 (INT_MIN)."""
    # As signed: INT_MAX < INT_MIN is false.
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x2, 1),
        initial_regs={2: 0x7FFFFFFF, 3: 0x80000000},  # INT_MAX, INT_MIN
        dest_reg=1,
        expected_value=0,
    )


@cocotb.test()
async def test_sltu_unsigned_less_than(dut):
    """SLTU x1, x2, x3: x1 = 1 if unsigned x2 < x3 else 0."""
    # As unsigned: 0 < 0xFFFFFFFF is true.
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x3, 1),  # SLTU x1, x2, x3
        initial_regs={2: 0x00000000, 3: 0xFFFFFFFF},
        dest_reg=1,
        expected_value=1,
    )


@cocotb.test()
async def test_sltu_unsigned_not_less_than(dut):
    """SLTU x1, x2, x3: -1 (as unsigned) is the maximum, not less than 0."""
    # As unsigned: 0xFFFFFFFF < 0 is false.
    await _setup_and_execute(
        dut,
        instruction=encode_r(0x00, 3, 2, 0x3, 1),
        initial_regs={2: 0xFFFFFFFF, 3: 0x00000000},
        dest_reg=1,
        expected_value=0,
    )


# ──────────────────────────────────────────────────────────────────────
# Upper-immediate tests (LUI, AUIPC)
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_lui_loads_upper_immediate(dut):
    """LUI x1, imm: x1 = imm << 12 (lower 12 bits are zero)."""
    await _setup_and_execute(
        dut,
        instruction=encode_u(0x12345, 1, 0b0110111),  # LUI x1, 0x12345
        initial_regs={},
        dest_reg=1,
        expected_value=0x12345000,
    )


@cocotb.test()
async def test_lui_with_zero_immediate(dut):
    """LUI x1, 0: x1 = 0."""
    await _setup_and_execute(
        dut,
        instruction=encode_u(0, 1, 0b0110111),
        initial_regs={},
        dest_reg=1,
        expected_value=0x00000000,
    )


@cocotb.test()
async def test_lui_max_immediate(dut):
    """LUI x1, 0xFFFFF: x1 = 0xFFFFF000 (sign-extended upper 20 bits)."""
    # 0xFFFFF is the maximum 20-bit immediate. Shifted left by 12 gives
    # 0xFFFFF000, which is -4096 in two's complement.
    await _setup_and_execute(
        dut,
        instruction=encode_u(0xFFFFF, 1, 0b0110111),
        initial_regs={},
        dest_reg=1,
        expected_value=0xFFFFF000,
    )


@cocotb.test()
async def test_auipc_adds_pc(dut):
    """AUIPC x1, imm: x1 = PC + (imm << 12). At PC=0, x1 = imm << 12."""
    await _setup_and_execute(
        dut,
        instruction=encode_u(0xCAFE0, 1, 0b0010111),  # AUIPC x1, 0xCAFE0
        initial_regs={},
        dest_reg=1,
        expected_value=0xCAFE0000,  # PC=0 at reset, so just imm << 12
    )
