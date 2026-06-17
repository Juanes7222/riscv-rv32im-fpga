"""
Cocotb test layer: model-vs-DUT comparison.

These tests use the Python reference model (verification/reference_model/)
as a golden reference. For each test:

  1. The model and the DUT are initialised to the same program state
     (regs, imem, dmem, CSRs).
  2. Both step one instruction (model via CPU.step(), DUT via step_clock).
  3. The full register file, PC, and CSR state are compared.
  4. On mismatch, the test fails with a diagnostic showing the PC,
     the instruction encoding, the expected state, and the actual state.

This is a fundamentally different style of verification from the
spec-vs-DUT tests in test_alu_rv32i.py and test_branch.py:

  - Spec-vs-DUT: compute expected_value from the ISA spec for one
    specific scenario (e.g., "ADD with overflow returns X").
  - Model-vs-DUT: run the SAME program on the model and the DUT,
    compare full state after each step. No hand-computed expected
    values per test.

The model-vs-DUT style catches:
  - Bugs in instruction encoders (decoder or DUT)
  - Bugs in handlers / control unit (e.g., wrong CSR op)
  - Bugs in PC update logic (e.g., wrong trap_target)
  - Bugs in memory access (e.g., wrong sign extension)

It does NOT catch:
  - Bugs in the model itself (the model and DUT could be wrong in the
    same way). The standalone self-test (reference_model/test_self.py)
    is the cross-check for the model.
  - Bugs in multi-cycle DUT operations (M extension): the model steps
    once, the DUT takes 1/34 cycles for MUL/DIV. The current tests
    focus on single-cycle DUT operations; M extension is left for a
    future test file (test_model_vs_dut_m_extension.py).
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut

# The reference_model package lives outside the cocotb test directory
# (at verification/reference_model/, while this file is in
# verification/cocotb/common/). cocotb 2.0.1 only adds the test
# directory to sys.path, so we load the package via importlib.
#
# Why not just `from reference_model import …`? cocotb 2.0.1 internally
# uses pytest's assertion-rewrite plugin, which re-executes test modules
# in a way that bypasses the `sys.path.insert` we do at module load.
# The path is in sys.path (verified by debug print), but the
# `from reference_model import` statement at the top of this file still
# fails with "No module named 'reference_model'". Loading the package
# via importlib.util bypasses pytest's machinery and works.
# See ADR 036 for the full investigation.
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

CPU        = _reference_model.CPU
encode_r   = _reference_model.encode_r
encode_i   = _reference_model.encode_i
encode_s   = _reference_model.encode_s
encode_b   = _reference_model.encode_b
encode_u   = _reference_model.encode_u
encode_j   = _reference_model.encode_j
encode_csr = _reference_model.encode_csr


# ──────────────────────────────────────────────────────────────────────
# Synchronisation helpers
# ──────────────────────────────────────────────────────────────────────

async def _sync_model_and_dut(dut, model):
    """Initialise the DUT and the model to identical state.

    Steps:
      1. Reset the DUT (PC=0, regs=0, CSRs at reset values).
      2. Copy the model's regs/imem into the DUT via deposit.
      3. Settle the simulator and step the DUT clock once.
      4. Step the model.

    Returns the post-step state on both sides, so the test can assert
    equality without re-reading the DUT."""
    await start_clock(dut)
    await reset_dut(dut)

    # Deposit initial state into the DUT.
    # regs[0] is X (DUT bug) so initialise explicitly.
    dut.u_rf.regs[0].value = 0
    for i in range(32):
        dut.u_rf.regs[i].value = model.regs[i]
    for i in range(len(model.imem) // 4):
        word = int.from_bytes(model.imem[i*4 : (i+1)*4], "little")
        dut.u_imem.mem[i].value = word

    # Settle deposits.
    await Timer(2, unit="ns")
    # Step both: one clock edge on the DUT, one step on the model.
    await step_clock(dut)
    model.step()


def _check_states(dut, model, instr_word, step_n):
    """Compare the full register file, PC, and CSRs after a step.

    On mismatch, raise an AssertionError with PC, instruction encoding,
    expected (model) state, and actual (DUT) state."""
    pc_dut = int(dut.u_pc.pc.value)
    pc_model = model.pc
    if pc_dut != pc_model:
        raise AssertionError(
            f"step {step_n}: PC mismatch after instruction "
            f"{instr_word:#010x}\n"
            f"  model:  PC = {pc_model:#010x}\n"
            f"  DUT:    PC = {pc_dut:#010x}"
        )

    for i in range(32):
        v_dut = int(dut.u_rf.regs[i].value)
        v_model = model.regs[i]
        if v_dut != v_model:
            raise AssertionError(
                f"step {step_n}: x{i} mismatch after instruction "
                f"{instr_word:#010x}\n"
                f"  model:  x{i} = {v_model:#010x}\n"
                f"  DUT:    x{i} = {v_dut:#010x}\n"
                f"  PC = {pc_model:#010x}"
            )


# ──────────────────────────────────────────────────────────────────────
# Demo tests
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_model_matches_dut_for_add(dut):
    """ADD x1, x2, x3: model.regs[1] = a + b matches the DUT after one step."""
    a, b = 0x12345678, 0x9ABCDEF0
    model = CPU()
    model.regs[2] = a
    model.regs[3] = b
    model.store_instruction(0, encode_r(0, 3, 2, 0, 1))  # ADD x1, x2, x3

    await _sync_model_and_dut(dut, model)
    _check_states(dut, model, encode_r(0, 3, 2, 0, 1), 0)


@cocotb.test()
async def test_model_matches_dut_for_taken_branch(dut):
    """BEQ x1, x2, +0x100 (taken): model PC = 0x100 matches the DUT after one step."""
    model = CPU()
    model.regs[1] = 0xDEADBEEF
    model.regs[2] = 0xDEADBEEF
    model.store_instruction(0, encode_b(0, 1, 2, 0x100))

    await _sync_model_and_dut(dut, model)
    _check_states(dut, model, encode_b(0, 1, 2, 0x100), 0)


@cocotb.test()
async def test_model_matches_dut_for_program_five_steps(dut):
    """A 5-instruction program: ADDI, ADDI, ADD, SW, ADDI.

    Runs all 5 instructions; the model and DUT state must match after
    each step. This is differential testing: the model computes the
    result, the DUT computes the result, and we check they agree."""
    program = [
        encode_i(0x100, 1, 0, 2),                # ADDI x2, x1, 0x100  (x1=0, so x2=0x100)
        encode_i(0x200, 0, 0, 3),                # ADDI x3, x0, 0x200  (x3=0x200)
        encode_r(0, 3, 2, 0, 4),                 # ADD  x4, x2, x3     (x4=0x300)
        encode_s(0x10, 4, 2, 0b010),             # SW   x4, 0x10(x2)   (mem[0x110]=0x300)
        encode_i(0x10, 2, 0b010, 5, opcode=0b0000011),  # LW x5, 0x10(x2) (x5=0x300)
    ]
    model = CPU()
    model.regs[1] = 0x0  # x1 starts at 0 so ADDI x2, x1, 0x100 gives x2=0x100
    for i, w in enumerate(program):
        model.store_instruction(i * 4, w)

    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    dut.u_rf.regs[1].value = 0
    for i, w in enumerate(program):
        dut.u_imem.mem[i].value = w
    await Timer(2, unit="ns")

    for step_n, w in enumerate(program):
        await step_clock(dut)
        model.step()
        _check_states(dut, model, w, step_n)


@cocotb.test()
async def test_model_matches_dut_for_ecall_trap(dut):
    """ECALL after setting mtvec=0x100: model PC = 0x100, mcause = 11.

    Two instructions:
      1. CSRRW mtvec, x1  (sets mtvec=0x100)
      2. ECALL            (traps to mtvec=0x100, sets mepc=8, mcause=11)
    """
    model = CPU()
    model.regs[1] = 0x100
    model.store_instruction(0, encode_csr(0x305, 1, 0b001, 0))  # CSRRW mtvec, x1
    model.store_instruction(4, 0b1110011)                       # ECALL
    # Place MRET at 0x100 so the test ends cleanly (the MRET itself is not
    # asserted; we exit after the ECALL step).
    model.store_instruction(0x100, (0x302 << 20) | 0b1110011)   # MRET

    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    dut.u_rf.regs[1].value = 0x100
    dut.u_imem.mem[0].value = encode_csr(0x305, 1, 0b001, 0)
    dut.u_imem.mem[1].value = 0b1110011
    dut.u_imem.mem[0x100 // 4].value = (0x302 << 20) | 0b1110011
    await Timer(2, unit="ns")

    # Step 1: CSRRW
    await step_clock(dut)
    model.step()
    _check_states(dut, model, encode_csr(0x305, 1, 0b001, 0), 0)
    assert model.csrs.mtvec == 0x100, f"mtvec: model={model.csrs.mtvec:#x}"

    # Step 2: ECALL
    await step_clock(dut)
    model.step()
    _check_states(dut, model, 0b1110011, 1)
    assert model.csrs.mcause == 11, f"mcause: model={model.csrs.mcause}"
    assert model.csrs.mepc == 8, f"mepc: model={model.csrs.mepc}"
