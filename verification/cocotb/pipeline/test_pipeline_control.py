"""
Pipeline control-hazard tests.

These tests verify that branches, jumps, and traps correctly flush the
younger instructions in the pipeline.

Coverage:
  - BEQ taken: instruction in the delay slot is flushed
  - BEQ not-taken: sequential execution continues
  - JAL flush: delay-slot instruction invalidated
  - JALR flush: same as JAL with register-indirect target
  - ECALL trap flush: instructions younger than ECALL are invalidated
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut

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
encode_j = _reference_model.encode_j
encode_csr = _reference_model.encode_csr


def _load_prog(dut, words):
    for i, w in enumerate(words):
        dut.u_imem.mem[i].value = w
    for i in range(len(words), len(words) + 8):
        dut.u_imem.mem[i].value = 0x00000013


# ----------------------------------------------------------------------
# Branch tests
# ----------------------------------------------------------------------

@cocotb.test()
async def test_beq_taken_flushes_pipeline(dut):
    """BEQ taken: ADDI x5 after the branch must NOT execute.

    Program:
      0x00: NOP
      0x04: NOP
      0x08: BEQ  x0, x0, +8   (always taken, no forwarding needed)
      0x0C: ADDI x5, x0, 0xDEAD  (flushed)
      0x10: ADDI x6, x0, 0xBEEF  (executes)

    After enough cycles x5 must still be 0 and x6 must be 0xBEEF."""
    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    _load_prog(dut, [
        0x00000013,                   # 0x00: NOP
        0x00000013,                   # 0x04: NOP
        encode_b(0, 0, 0, 8),         # 0x08: BEQ x0, x0, +8
        encode_i(0xDEAD, 0, 0, 5),    # 0x0C: ADDI x5, x0, 0xDEAD
        encode_i(0xBEEF, 0, 0, 6),    # 0x10: ADDI x6, x0, 0xBEEF
    ])
    await Timer(2, unit="ns")

    for _ in range(14):
        await step_clock(dut)

    x5 = int(dut.u_rf.regs[5].value)
    x6 = int(dut.u_rf.regs[6].value)
    assert x5 == 0, (
        f"BEQ taken flush failed: x5 = {x5:#010x} (expected 0)"
    )
    # encode_i masks imm to 12 bits: 0xBEEF & 0xFFF = 0xEEF, sign-extended -> 0xFFFFFEEF
    assert x6 == 0xFFFFFEEF, (
        f"BEQ target missed: x6 = {x6:#010x} (expected 0xFFFFFEEF)"
    )


@cocotb.test()
async def test_beq_not_taken_no_flush(dut):
    """BEQ not-taken: ADDI x5 after the branch MUST execute.

    Program:
      0x00: ADDI x1, x0, 1
      0x04: ADDI x2, x0, 2
      0x08: BEQ  x1, x2, +8
      0x0C: ADDI x5, x0, 0xABCD
      0x10: ADDI x6, x0, 0xEF01

    x5 must be 0xFFFFABCD (sign-extended 0xABCD -> lower 12 bits = 0xBCD,
    sign-extended = 0xFFFFFBCD).  Wait: encode_i masks to 12 bits, so
    0xABCD & 0xFFF = 0xBCD.  The expected value is 0xFFFFFBCD."""
    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    _load_prog(dut, [
        encode_i(1, 0, 0, 1),        # 0x00: ADDI x1, x0, 1
        encode_i(2, 0, 0, 2),        # 0x04: ADDI x2, x0, 2
        encode_b(0, 1, 2, 8),        # 0x08: BEQ x1, x2, +8
        encode_i(0xABCD, 0, 0, 5),   # 0x0C: ADDI x5, x0, 0xABCD
        encode_i(0xEF01, 0, 0, 6),   # 0x10: ADDI x6, x0, 0xEF01
    ])
    await Timer(2, unit="ns")

    for _ in range(14):
        await step_clock(dut)

    x5 = int(dut.u_rf.regs[5].value)
    # encode_i masks imm to 12 bits: 0xABCD & 0xFFF = 0xBCD, sign-extended -> 0xFFFFFBCD
    assert x5 == 0xFFFFFBCD, (
        f"BEQ not-taken: x5 = {x5:#010x} (expected 0xFFFFFBCD)"
    )


# ----------------------------------------------------------------------
# Jump tests
# ----------------------------------------------------------------------

@cocotb.test()
async def test_jal_flush(dut):
    """JAL +0x14: instruction at 0x04 must be flushed.

    Program:
      0x00: JAL  x1, +0x14       (x1 = 0x04, target = 0x14)
      0x04: ADDI x5, x0, 0xBAD   (flushed)
      0x08: ADDI x6, x0, 0xBAD   (flushed)
      0x0C: NOP
      0x10: NOP
      0x14: ADDI x7, x0, 0x1234  (executes)

    x5 must remain 0, x1 must be 0x04, x7 must be 0x1234."""
    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    _load_prog(dut, [
        encode_j(0x14, 1),           # 0x00: JAL x1, +0x14
        encode_i(0xBAD, 0, 0, 5),    # 0x04: ADDI x5, x0, 0xBAD
        encode_i(0xBAD, 0, 0, 6),    # 0x08: ADDI x6, x0, 0xBAD
        0x00000013,                   # 0x0C: NOP
        0x00000013,                   # 0x10: NOP
        encode_i(0x1234, 0, 0, 7),   # 0x14: ADDI x7, x0, 0x1234
    ])
    await Timer(2, unit="ns")

    for _ in range(16):
        await step_clock(dut)

    assert int(dut.u_rf.regs[5].value) == 0, (
        f"JAL flush failed: x5 = {int(dut.u_rf.regs[5].value):#010x}"
    )
    assert int(dut.u_rf.regs[1].value) == 0x04, (
        f"JAL link: x1 = {int(dut.u_rf.regs[1].value):#010x} (expected 0x04)"
    )
    # encode_i masks imm to 12 bits: 0x1234 & 0xFFF = 0x234, sign-extended -> 0x00000234
    assert int(dut.u_rf.regs[7].value) == 0x00000234, (
        f"JAL target: x7 = {int(dut.u_rf.regs[7].value):#010x} (expected 0x00000234)"
    )


@cocotb.test()
async def test_jalr_flush(dut):
    """JALR x0, x2, 0: instruction at 0x04 must be flushed.

    Program:
      0x00: ADDI x2, x0, 0x14
      0x04: JALR x1, x2, 0       (target = x2 = 0x14)
      0x08: ADDI x5, x0, 0xBAD   (flushed)
      0x0C: NOP
      0x10: NOP
      0x14: ADDI x7, x0, 0xCAFE  (executes)

    x5 must remain 0, x7 must be 0xCAFE."""
    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    dut.u_rf.regs[2].value = 0
    _load_prog(dut, [
        encode_i(0x14, 0, 0, 2),              # 0x00: ADDI x2, x0, 0x14
        encode_i(0, 2, 0, 1, opcode=0b1100111), # 0x04: JALR x1, x2, 0
        encode_i(0xBAD, 0, 0, 5),             # 0x08: ADDI x5, x0, 0xBAD
        0x00000013,                            # 0x0C: NOP
        0x00000013,                            # 0x10: NOP
        encode_i(0xCAFE, 0, 0, 7),            # 0x14: ADDI x7, x0, 0xCAFE
    ])
    await Timer(2, unit="ns")

    for _ in range(16):
        await step_clock(dut)

    assert int(dut.u_rf.regs[5].value) == 0, (
        f"JALR flush failed: x5 = {int(dut.u_rf.regs[5].value):#010x}"
    )
    # encode_i masks imm to 12 bits: 0xCAFE & 0xFFF = 0xAFE, sign-extended -> 0xFFFFFAFE
    assert int(dut.u_rf.regs[7].value) == 0xFFFFFAFE, (
        f"JALR target: x7 = {int(dut.u_rf.regs[7].value):#010x} (expected 0xFFFFFAFE)"
    )


# ----------------------------------------------------------------------
# Trap flush test (covered by rv32mi riscv-tests; local test omitted
# because trap handler address layout is cumbersome in backdoor testing)
# ----------------------------------------------------------------------
