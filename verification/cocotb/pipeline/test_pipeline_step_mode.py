"""
Step-mode tests against the real top_pipeline.

SW[9] (step_mode) freezes the pipeline, KEY[1] (key_step, the raw
active-low board pin) releases it for exactly one clock cycle, so one
press advances the instruction by exactly one stage.

The tests run on the real top - not on a re-implementation of its freeze
wiring - so they also cover the wiring: the flush suppression, the
`id_ex_hold` term, the EX/MEM and MEM/WB holds and the priority of the
PC unit's stall over the branch redirect.  Dropping the freeze from any
of those nets makes them fail.

The instruction memory is restored at the end of every test, so the tests
do not depend on the order in which the test modules run.
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut

# The reference model provides the instruction encoders.  It lives outside
# the cocotb test directory, and cocotb 2.0.1 + pytest's assertion-rewrite
# plugin break the plain `from reference_model import …` pattern (see ADR
# 036).  Load via importlib instead.
import os
import sys
import importlib.util

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_REF_MODEL = os.path.join(_REPO_ROOT, "reference_model")

_spec = importlib.util.spec_from_file_location(
    "reference_model",
    os.path.join(_REF_MODEL, "__init__.py"),
    submodule_search_locations=[_REF_MODEL],
)
_reference_model = importlib.util.module_from_spec(_spec)
sys.modules["reference_model"] = _reference_model
_spec.loader.exec_module(_reference_model)

encode_i = _reference_model.encode_i
encode_b = _reference_model.encode_b

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

NOP = 0x00000013
# Number of instruction words the tests write (program + NOP padding).
PROGRAM_WORDS = 16


# ──────────────────────────────────────────────────────────────────────
# Drivers and probes
# ──────────────────────────────────────────────────────────────────────

async def freeze(dut) -> None:
    """Engage the freeze and wait until it is active."""
    dut.step_mode.value = 1
    for _ in range(FREEZE_EDGES):
        await step_clock(dut)


async def press_step(dut) -> None:
    """Press KEY[1] once: the pipeline advances for exactly one clock."""
    dut.key_step.value = 0
    for _ in range(PRESS_EDGES):
        await step_clock(dut)
    dut.key_step.value = 1
    for _ in range(RELEASE_EDGES):
        await step_clock(dut)


async def deposit_program(dut, program) -> dict:
    """Write `program` into the instruction memory.

    Returns the overwritten words, so that `restore_program` can put the
    image back the way it was: the tests must not depend on the order in
    which the test modules run.
    """
    original = {}
    for address in range(PROGRAM_WORDS):
        original[address] = int(dut.u_imem.mem[address].value)
        dut.u_imem.mem[address].value = program.get(address, NOP)
    await Timer(2, unit="ns")
    return original


async def restore_program(dut, original: dict) -> None:
    """Put the instruction memory back the way it was."""
    for address, value in original.items():
        dut.u_imem.mem[address].value = value
    await Timer(2, unit="ns")


def stage_state(dut) -> dict:
    """The program counter of every pipeline stage."""
    return {
        "pc": int(dut.u_pcunit.pc.value),
        "if_pc": int(dut.if_pc.value),
        "id_pc": int(dut.u_if_id.id_pc.value),
        "ex_pc": int(dut.u_id_ex.ex_pc.value),
        "mem_pc": int(dut.u_ex_mem.mem_pc.value),
        "wb_pc": int(dut.u_mem_wb.wb_pc.value),
    }


def reg_value(dut, index: int) -> int:
    """The content of register `index` of the register file."""
    return int(dut.u_rf.regs[index].value)


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_pipeline_step_mode_freezes_the_pipeline(dut):
    """The freeze stops the pipeline; one press advances it by one stage."""
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)
    original = await deposit_program(dut, {
        0: encode_i(5, 0, 0, 1),     # ADDI x1, x0, 5
        1: encode_i(7, 0, 0, 2),     # ADDI x2, x0, 7
        2: encode_i(9, 0, 0, 3),     # ADDI x3, x0, 9
        3: encode_i(11, 0, 0, 4),    # ADDI x4, x0, 11
    })
    try:
        # Let the pipeline fill up before freezing it.
        for _ in range(8):
            await step_clock(dut)

        await freeze(dut)
        frozen = stage_state(dut)

        # The pipeline is frozen: no stage moves.
        for _ in range(5):
            await step_clock(dut)
        assert stage_state(dut) == frozen, (
            f"the pipeline advanced while frozen: {frozen} -> {stage_state(dut)}"
        )

        # One press advances the instruction by exactly one stage: every
        # register takes the content of the stage in front of it and the
        # program counter moves by one instruction.
        await press_step(dut)
        after = stage_state(dut)
        assert after["pc"] == frozen["pc"] + 4, (
            f"the press did not advance the PC by one instruction: "
            f"{frozen['pc']:#010x} -> {after['pc']:#010x}"
        )
        assert after["id_pc"] == frozen["if_pc"], "the IF/ID register did not take the IF stage"
        assert after["ex_pc"] == frozen["id_pc"], "the ID/EX register did not take the ID stage"
        assert after["mem_pc"] == frozen["ex_pc"], "the EX/MEM register did not take the EX stage"
        assert after["wb_pc"] == frozen["mem_pc"], "the MEM/WB register did not take the MEM stage"

        # The pipeline is frozen again once the release cycle is over.
        await press_step(dut)
        second = stage_state(dut)
        assert second["pc"] == after["pc"] + 4, "the second press did not advance the PC"
        for _ in range(3):
            await step_clock(dut)
        assert stage_state(dut) == second, "the pipeline advanced after the press"
    finally:
        await restore_program(dut, original)


@cocotb.test()
async def test_pipeline_step_mode_keeps_a_taken_branch(dut):
    """A branch taken while the pipeline is frozen is not swallowed."""
    # The target is not the fall-through address, so that the instruction
    # the IF stage shows can be told apart from the redirect target.
    branch = encode_b(0b000, 0, 0, 12)     # BEQ x0, x0, +12 -> 0x14
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)
    original = await deposit_program(dut, {
        0: encode_i(5, 0, 0, 1),             # ADDI x1, x0, 5
        1: encode_i(7, 0, 0, 2),             # ADDI x2, x0, 7
        2: branch,                           # BEQ  x0, x0, 0x14
        3: encode_i(9, 0, 0, 3),             # ADDI x3, x0, 9 (not executed)
        4: encode_i(11, 0, 0, 4),            # ADDI x4, x0, 11 (fetched, not executed)
        5: encode_i(13, 0, 0, 5),            # ADDI x5, x0, 13 (branch target)
    })
    try:
        await freeze(dut)

        # Advance the frozen pipeline until the branch is in the EX stage.
        for _ in range(10):
            if int(dut.u_id_ex.ex_instruction.value) == branch:
                break
            await press_step(dut)
        assert int(dut.u_id_ex.ex_instruction.value) == branch, (
            "the branch did not reach the EX stage"
        )
        assert int(dut.branch_flush.value) == 1, "the branch was not taken"

        # The pipeline is frozen with the branch in EX.
        frozen = stage_state(dut)
        for _ in range(5):
            await step_clock(dut)
        assert stage_state(dut) == frozen, (
            f"the pipeline advanced while frozen: {frozen} -> {stage_state(dut)}"
        )

        # The IF stage keeps showing the frozen instruction - the one at
        # the program counter - and not the redirect target of the pending
        # branch.
        assert int(dut.if_instruction.value) == encode_i(11, 0, 0, 4), (
            f"the IF stage does not show the frozen instruction: "
            f"{int(dut.if_instruction.value):#010x}"
        )

        # The release applies the redirect: the program counter jumps to
        # the branch target instead of continuing sequentially.
        await press_step(dut)
        assert int(dut.u_pcunit.pc.value) == 0x14, (
            f"the taken branch was swallowed: PC = {int(dut.u_pcunit.pc.value):#010x}"
        )
        assert int(dut.u_ex_mem.mem_instruction.value) == branch, (
            "the branch did not advance to the MEM stage"
        )

        # The fall-through instruction is never executed, the target is.
        for _ in range(8):
            await press_step(dut)
        assert reg_value(dut, 3) == 0, (
            f"the branch was not taken: x3 = {reg_value(dut, 3):#010x}"
        )
        assert reg_value(dut, 5) == 13, (
            f"the branch target was not executed: x5 = {reg_value(dut, 5):#010x}"
        )
    finally:
        await restore_program(dut, original)
