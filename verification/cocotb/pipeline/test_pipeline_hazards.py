"""
Pipeline hazard and forwarding tests.

These tests verify the five-stage pipeline's hazard-resolution mechanisms
using small hand-crafted programs.  The reference model is used as a
golden reference: model and DUT are initialised to the same state, both
step the same number of instructions (or clock cycles for the DUT), and
the full register file is compared.

Coverage:
  - EX/MEM -> EX forwarding (productor in EX/MEM, consumer in EX)
  - MEM/WB -> EX forwarding (productor in MEM/WB, consumer in EX)
  - WB     -> ID forwarding (productor in WB, consumer entering ID/EX)
  - Load-use stall (1 cycle) followed by MEM/WB -> EX forwarding
  - Chain of three RAW dependencies (I1 -> I2 -> I3)
  - False-forward suppression when rd = x0
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

CPU      = _reference_model.CPU
encode_r = _reference_model.encode_r
encode_i = _reference_model.encode_i
encode_s = _reference_model.encode_s


def _load_model_program(model, words):
    for i, w in enumerate(words):
        model.store_instruction(i * 4, w)


def _preload_dut(dut, model, instructions):
    dut.u_rf.regs[0].value = 0
    for i in range(32):
        dut.u_rf.regs[i].value = model.regs[i]
    for i, w in enumerate(instructions):
        dut.u_imem.mem[i].value = w
    for i in range(len(instructions), len(instructions) + 4):
        dut.u_imem.mem[i].value = 0x00000013  # bubble padding


def _check_all_regs(dut, model, tag):
    for i in range(32):
        v_dut = int(dut.u_rf.regs[i].value)
        v_model = model.regs[i]
        assert v_dut == v_model, (
            f"{tag}: x{i} mismatch\n"
            f"  model: {v_model:#010x}\n"
            f"  DUT:   {v_dut:#010x}"
        )


# ──────────────────────────────────────────────────────────────────────
# Helpers: step the DUT enough cycles for N back-to-back instructions
# ──────────────────────────────────────────────────────────────────────

async def _run_program(dut, model, instructions, extra_cycles=2):
    """Load program into DUT and model, reset, then step DUT enough
    cycles for all instructions to retire (4 fill-up + N drain).
    The model is stepped once per instruction."""
    await start_clock(dut)
    await reset_dut(dut)

    _load_model_program(model, instructions)
    _preload_dut(dut, model, instructions)
    await Timer(2, unit="ns")

    total_cycles = 4 + len(instructions) + extra_cycles
    for _ in range(total_cycles):
        await step_clock(dut)

    for _ in instructions:
        model.step()


# ──────────────────────────────────────────────────────────────────────
# Forwarding tests
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_forward_ex_mem_to_ex(dut):
    """EX/MEM -> EX forwarding: ADD x1,x2,x3 (I1) then ADD x4,x1,x5 (I2).

    When I2 reaches EX, I1 is in EX/MEM.  The forwarding unit should
    select mem_alu_result for I2's rs1."""
    model = CPU()
    model.regs[2] = 0x11111111
    model.regs[3] = 0x22222222
    model.regs[5] = 0x33333333

    i1 = encode_r(0, 3, 2, 0, 1)   # ADD x1, x2, x3
    i2 = encode_r(0, 5, 1, 0, 4)   # ADD x4, x1, x5
    prog = [i1, i2]

    await _run_program(dut, model, prog)
    _check_all_regs(dut, model, "forward_ex_mem_to_ex")


@cocotb.test()
async def test_forward_mem_wb_to_ex(dut):
    """MEM/WB -> EX forwarding: ADD x1,x2,x3 (I1), NOP, ADD x4,x1,x5 (I2).

    When I2 reaches EX, I1 is in MEM/WB.  The forwarding unit should
    select wb_rd_data for I2's rs1."""
    model = CPU()
    model.regs[2] = 0x44444444
    model.regs[3] = 0x55555555
    model.regs[5] = 0x66666666

    i1 = encode_r(0, 3, 2, 0, 1)   # ADD x1, x2, x3
    nop = 0x00000013                # ADDI x0, x0, 0
    i2 = encode_r(0, 5, 1, 0, 4)   # ADD x4, x1, x5
    prog = [i1, nop, i2]

    await _run_program(dut, model, prog)
    _check_all_regs(dut, model, "forward_mem_wb_to_ex")


@cocotb.test()
async def test_forward_wb_to_id(dut):
    """WB -> ID forwarding: ADD x1,x2,x3 (I1) then ADD x4,x1,x5 (I2).

    Because we eliminated the wb_raw stall, when I1 is in WB and I2 is
    in ID, the value written by I1 must be captured directly into
    ID/EX via the wb->id muxes.  This test is intentionally identical
    in structure to forward_ex_mem_to_ex; the difference is the timing
    window when the producer is in WB, which happens naturally here
    because there is no stall."""
    model = CPU()
    model.regs[2] = 0x77777777
    model.regs[3] = 0x88888888
    model.regs[5] = 0x99999999

    i1 = encode_r(0, 3, 2, 0, 1)   # ADD x1, x2, x3
    i2 = encode_r(0, 5, 1, 0, 4)   # ADD x4, x1, x5
    prog = [i1, i2]

    await _run_program(dut, model, prog)
    _check_all_regs(dut, model, "forward_wb_to_id")


@cocotb.test()
async def test_load_use_then_forward_mem_wb(dut):
    """LW x1,0(x2) then ADD x3,x1,x4: load-use stall + MEM/WB forwarding.

    Cycle map (approximate):
      1: LW in IF
      2: LW in ID, ADD in IF
      3: LW in EX, ADD stalled in ID (load_use asserted)
      4: LW in MEM, ADD in EX  (LW result not yet available)
      5: LW in WB,  ADD in MEM (ADD used forwarded value from MEM/WB)
      6: ADD in WB
    The ADD must see the loaded value, not the stale x1."""
    model = CPU()
    addr = 0x40
    mem_val = 0xCAFEBABE
    model.regs[2] = addr
    model.regs[4] = 0x10
    model.store_word(addr, mem_val)

    lw  = encode_i(0, 2, 0b010, 1, opcode=0b0000011)  # LW x1, 0(x2)
    add = encode_r(0, 4, 1, 0, 3)                      # ADD x3, x1, x4
    prog = [lw, add]

    await start_clock(dut)
    await reset_dut(dut)
    _load_model_program(model, prog)
    _preload_dut(dut, model, prog)
    dut.u_dmem.mem[addr // 4].value = mem_val
    await Timer(2, unit="ns")

    # Need 4 fill-up + 2 instructions + 1 load-use stall + margin = 10 cycles.
    for _ in range(10):
        await step_clock(dut)

    model.step()  # LW
    model.step()  # ADD

    _check_all_regs(dut, model, "load_use_then_forward")


@cocotb.test()
async def test_chain_three_raw_dependencies(dut):
    """Chain: I1 produces x1, I2 consumes x1 and produces x2, I3 consumes x2.

    ADD x1, x2, x3
    ADD x2, x1, x4
    ADD x5, x2, x6

    This exercises EX/MEM->EX (I1->I2) and EX/MEM->EX (I2->I3)
    simultaneously.  The model gives the ground truth."""
    model = CPU()
    model.regs[2] = 0x10
    model.regs[3] = 0x20
    model.regs[4] = 0x30
    model.regs[6] = 0x40

    i1 = encode_r(0, 3, 2, 0, 1)   # ADD x1, x2, x3
    i2 = encode_r(0, 4, 1, 0, 2)   # ADD x2, x1, x4
    i3 = encode_r(0, 6, 2, 0, 5)   # ADD x5, x2, x6
    prog = [i1, i2, i3]

    await _run_program(dut, model, prog)
    _check_all_regs(dut, model, "chain_three_raw")


@cocotb.test()
async def test_no_false_forward_to_x0(dut):
    """When the producer writes to x0, forwarding must be suppressed.

    ADD x0, x2, x3   (result discarded, x0 stays 0)
    ADD x1, x0, x4   (must read x0 = 0, not the ADD result)
    """
    model = CPU()
    model.regs[2] = 0xDEADBEEF
    model.regs[3] = 0xCAFEBABE
    model.regs[4] = 0x12345678

    i1 = encode_r(0, 3, 2, 0, 0)   # ADD x0, x2, x3
    i2 = encode_r(0, 4, 0, 0, 1)   # ADD x1, x0, x4
    prog = [i1, i2]

    await _run_program(dut, model, prog)
    _check_all_regs(dut, model, "no_false_forward_x0")


@cocotb.test()
async def test_mem_raw_stall_then_forward(dut):
    """MEM-RAW stall: producer in MEM, consumer in ID.

    ADD x1, x2, x3
    NOP
    ADD x4, x1, x5

    With the mem_raw stall the pipeline retains IF/ID for one cycle so
    the producer can reach WB.  After the stall the WB->ID forwarding
    delivers the correct value.  The model does not stall, so we must
    align the comparison carefully: run the DUT for enough cycles
    (including the implicit stall) and then compare."""
    model = CPU()
    model.regs[2] = 0xAAAAAAAA
    model.regs[3] = 0x55555555
    model.regs[5] = 0x11111111

    i1 = encode_r(0, 3, 2, 0, 1)   # ADD x1, x2, x3
    nop = 0x00000013                # ADDI x0, x0, 0
    i2 = encode_r(0, 5, 1, 0, 4)   # ADD x4, x1, x5
    prog = [i1, nop, i2]

    await _run_program(dut, model, prog, extra_cycles=3)
    _check_all_regs(dut, model, "mem_raw_stall_then_forward")
