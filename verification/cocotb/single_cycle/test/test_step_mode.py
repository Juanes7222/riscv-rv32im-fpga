# verification/cocotb/single_cycle/test/test_step_mode.py
"""
Step-mode tests against the real top_single_cycle.

SW[9] (step_mode) freezes the processor, KEY[1] (key_step, the raw
active-low board pin) releases it for exactly one clock cycle.  The tests
run on the real top - not on a re-implementation of its freeze wiring -
so they also cover the wiring: dropping the freeze from any of the
clock-enable nets in top_single_cycle.sv makes them fail.

The division tests cover the case the freeze used to get wrong: a division
whose result is produced while the processor is frozen must still reach
the register file, and the divider must be suspended rather than restarted.

The instruction memory is restored at the end of every test, so the tests
do not depend on the order in which the test modules run.
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut

# Step-mode timing, defined in rtl/shared/step_mode_ctrl.sv: the press is
# sampled at clock 0, the release request is registered at clock 3 and the
# processor advances at clock 4.  The button is held two clocks longer, so
# that the press is certainly sampled.
STEP_ADVANCE_CLOCK = 4
PRESS_EDGES = STEP_ADVANCE_CLOCK + 2
# The synchroniser needs four clocks to refill with the released level
# before the next press can be detected.
RELEASE_EDGES = 5
# The switch synchroniser needs two clocks to engage the freeze.
FREEZE_EDGES = 3

DIV_RUNNING = 1


# ──────────────────────────────────────────────────────────────────────
# Instruction encoders
# ──────────────────────────────────────────────────────────────────────

def encode_i(imm12, rs1, funct3, rd, opcode=0b0010011):
    """Encode an I-type instruction (OP-IMM opcode 0b0010011)."""
    return ((imm12 & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode


def encode_r(funct7, rs2, rs1, funct3, rd):
    """Encode an R-type instruction (OP opcode 0b0110011)."""
    return (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | 0b0110011


# ──────────────────────────────────────────────────────────────────────
# Drivers and probes
# ──────────────────────────────────────────────────────────────────────

async def freeze(dut) -> None:
    """Engage the freeze and wait until it is active."""
    dut.step_mode.value = 1
    for _ in range(FREEZE_EDGES):
        await step_clock(dut)


async def press_step(dut) -> None:
    """Press KEY[1] once: the processor advances for exactly one clock."""
    dut.key_step.value = 0
    for _ in range(PRESS_EDGES):
        await step_clock(dut)
    dut.key_step.value = 1
    for _ in range(RELEASE_EDGES):
        await step_clock(dut)


def pc_value(dut) -> int:
    """The program counter of top_single_cycle."""
    return int(dut.u_pc.pc.value)


def reg_value(dut, index: int) -> int:
    """The content of register `index` of the register file."""
    return int(dut.u_rf.regs[index].value)


async def deposit_program(dut, program) -> dict:
    """Write the instructions of `program` into the instruction memory.

    Returns the overwritten words, so that `restore_program` can put the
    image back the way it was: the tests must not depend on the order in
    which the test modules run.
    """
    original = {}
    for address, instruction in enumerate(program):
        original[address] = int(dut.u_imem.mem[address].value)
        dut.u_imem.mem[address].value = instruction
    await Timer(2, unit="ns")
    return original


async def restore_program(dut, original: dict) -> None:
    """Put the instruction memory back the way it was."""
    for address, value in original.items():
        dut.u_imem.mem[address].value = value
    await Timer(2, unit="ns")


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────

@cocotb.test(name="test_step_mode_freezes_the_processor")
async def test_freeze(dut):
    """The freeze stops the processor; one press advances one instruction."""
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)
    original = await deposit_program(dut, [
        encode_i(5, 0, 0, 1),   # ADDI x1, x0, 5
        encode_i(7, 0, 0, 2),   # ADDI x2, x0, 7
        encode_i(9, 0, 0, 3),   # ADDI x3, x0, 9
    ])
    try:
        await freeze(dut)

        # The processor is frozen: the PC does not move.
        frozen_pc = pc_value(dut)
        for _ in range(5):
            await step_clock(dut)
        assert pc_value(dut) == frozen_pc, "the PC advanced while the processor was frozen"

        # One press advances the processor by exactly one instruction.
        await press_step(dut)
        assert pc_value(dut) == frozen_pc + 4, (
            f"the press did not advance one instruction: "
            f"PC = {pc_value(dut):#010x}, expected {frozen_pc + 4:#010x}"
        )

        # The processor is frozen again once the release cycle is over.
        for _ in range(5):
            await step_clock(dut)
        assert pc_value(dut) == frozen_pc + 4, "the PC advanced after the press"
    finally:
        await restore_program(dut, original)


@cocotb.test(name="test_step_mode_division_result_is_preserved")
async def test_division(dut):
    """A division that runs while frozen must reach the register file."""
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)
    original = await deposit_program(dut, [
        encode_i(100, 0, 0, 1),                     # ADDI x1, x0, 100
        encode_i(7, 0, 0, 2),                       # ADDI x2, x0, 7
        encode_r(0b0000001, 2, 1, 0b100, 3),        # DIV  x3, x1, x2
        encode_i(1, 0, 0, 4),                       # ADDI x4, x0, 1
    ])
    try:
        # Let the division start.
        for _ in range(10):
            await step_clock(dut)
            if int(dut.u_alu.div_state.value) == DIV_RUNNING:
                break
        assert int(dut.u_alu.div_state.value) == DIV_RUNNING, "the division did not start"

        # Freeze while the division is in flight.
        await freeze(dut)

        # The divider belongs to the frozen state: it must not move.
        state = int(dut.u_alu.div_state.value)
        count = int(dut.u_alu.div_count.value)
        frozen_pc = pc_value(dut)
        for _ in range(5):
            await step_clock(dut)
        assert int(dut.u_alu.div_state.value) == state, "the divider state changed while frozen"
        assert int(dut.u_alu.div_count.value) == count, "the divider was restarted while frozen"
        assert pc_value(dut) == frozen_pc, "the PC advanced while frozen"
        assert reg_value(dut, 3) == 0, "the quotient was written while frozen"

        # Every press advances the division by one iteration.  The division is
        # suspended, never restarted, so the iteration counter only grows.
        previous_count = count
        for _ in range(40):
            await press_step(dut)
            current_count = int(dut.u_alu.div_count.value)
            assert current_count >= previous_count, (
                f"the division was restarted: div_count {previous_count} -> {current_count}"
            )
            previous_count = current_count
            if reg_value(dut, 3) == 14:
                break
        assert reg_value(dut, 3) == 14, (
            f"the quotient was lost: x3 = {reg_value(dut, 3):#010x}, expected 0x0000000e"
        )

        # The processor must be able to leave the division: one more press
        # moves the PC past it.
        for _ in range(4):
            if pc_value(dut) == 12:
                break
            await press_step(dut)
        assert pc_value(dut) == 12, (
            f"the PC did not advance past the division: PC = {pc_value(dut):#010x}"
        )
    finally:
        await restore_program(dut, original)


@cocotb.test(name="test_step_mode_division_by_zero_is_preserved")
async def test_division_by_zero(dut):
    """The divide-by-zero result must survive the freeze as well."""
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)
    original = await deposit_program(dut, [
        encode_i(100, 0, 0, 1),                     # ADDI x1, x0, 100
        encode_r(0b0000001, 0, 1, 0b100, 2),        # DIV  x2, x1, x0 (divide by zero)
        encode_i(1, 0, 0, 4),                       # ADDI x4, x0, 1
    ])
    try:
        await freeze(dut)

        # The divider is suspended, so the divide-by-zero result is produced
        # only on a release cycle - and it must not be lost.
        for _ in range(10):
            await press_step(dut)
            result = reg_value(dut, 2)
            assert result in (0, 0xFFFFFFFF), (
                f"the divide-by-zero result is wrong: x2 = {result:#010x}"
            )
            if result == 0xFFFFFFFF:
                break
        assert reg_value(dut, 2) == 0xFFFFFFFF, (
            f"the divide-by-zero result was lost: x2 = {reg_value(dut, 2):#010x}"
        )
    finally:
        await restore_program(dut, original)
