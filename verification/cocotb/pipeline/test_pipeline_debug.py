"""
Debug smoke test: reproduce the add.S TEST 8 scenario.

add.S TEST 8 is: `add x14, x11, x12` with x11=0 (loaded by li), x12=0x7fff
(loaded by li). The pipeline must forward x11 from MEM/WB and x12 from
EX/MEM. If the forwarding is wrong, x14 ends up as 0 (stale x11) or
0xffff8000 (stale x12), not the expected 0x7fff.
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut

# Load the reference_model via importlib (cocotb 2.0 / pytest workaround
# per ADR 036).
import os
import sys
import importlib.util
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_REF_MODEL = os.path.join(_REPO_ROOT, "reference_model")
_spec = importlib.util.spec_from_file_location(
    "reference_model", os.path.join(_REF_MODEL, "__init__.py"),
    submodule_search_locations=[_REF_MODEL],
)
_ref = importlib.util.module_from_spec(_spec)
sys.modules["reference_model"] = _ref
_spec.loader.exec_module(_ref)
encode_i = _ref.encode_i
encode_u = _ref.encode_u
encode_r = _ref.encode_r


@cocotb.test()
async def test_add_with_lui_x12_no_stalls(dut):
    """Reproduce add.S TEST 8: x11=0, x12=0x7fff, x14=0x7fff.

    `li x12, 0x7fff` is a pseudo-instruction that expands to
    `lui x12, 8; addi x12, x12, -1` because 0x7fff doesn't fit in
    a 12-bit signed immediate. So the actual program is 4 instructions:

        addi x11, x0, 0     # x11 = 0
        lui   x12, 8         # x12 = 0x8000
        addi  x12, x12, -1   # x12 = 0x7fff
        add   x14, x11, x12  # x14 = 0 + 0x7fff = 0x7fff

    No stalls: forwarding from MEM/WB (for x11, 3 inst back) and
    EX/MEM (for x12, 1 inst back) should provide the fresh values.
    If forwarding is wrong, x14 will be 0 or 0xffff8000 (stale)."""
    addi_x11 = encode_i(0,    0, 0, 11)          # addi x11, x0, 0
    lui_x12  = encode_u(8, 12, 0b0110111)        # lui x12, 8 (x12 = 0x8000)
    addi_x12 = encode_i(0xfff, 12, 0, 12)        # addi x12, x12, -1 (imm=0xfff, sign-ext to -1)
    add_x14  = encode_r(0, 12, 11, 0, 14)        # add x14, x11, x12

    await start_clock(dut)
    await reset_dut(dut)
    dut.u_rf.regs[0].value = 0
    # Stale values to mimic "previous test" — forwarding must override.
    dut.u_rf.regs[11].value = 0xffffffff80000000 & 0xFFFFFFFF
    dut.u_rf.regs[12].value = 0xffffffffffff8000 & 0xFFFFFFFF
    dut.u_imem.mem[0].value = addi_x11
    dut.u_imem.mem[1].value = lui_x12
    dut.u_imem.mem[2].value = addi_x12
    dut.u_imem.mem[3].value = add_x14
    for i in range(4, 10):
        dut.u_imem.mem[i].value = 0x00000013
    await Timer(2, unit="ns")

    for cycle in range(12):
        await step_clock(dut)
        cocotb.log.info(
            f"cycle {cycle+1}: "
            f"if_id={int(dut.u_if_id.id_instruction.value):#010x} "
            f"id_ex={int(dut.u_id_ex.ex_instruction.value):#010x} "
            f"ex_mem={int(dut.u_ex_mem.mem_instruction.value):#010x} "
            f"mem_wb={int(dut.u_mem_wb.wb_instruction.value):#010x} "
            f"fwd_b={int(dut.dbg_fwd_b_sel.value)} "
            f"rs2_fwd={int(dut.dbg_ex_rs2_fwd.value):#010x} "
            f"x11={int(dut.u_rf.regs[11].value):#010x} "
            f"x12={int(dut.u_rf.regs[12].value):#010x} "
            f"x14={int(dut.u_rf.regs[14].value):#010x}"
        )

    # The add retires after the 1-cycle MEM-RAW stall. The pipeline
    # took 5 cycles (addi) + 5 (lui) + 5 (addi) + 5 (add) + 1 (stall) - 4
    # (overlap) = 12 cycles from the first IF. Read x14 at cycle 12+.
    x14 = int(dut.u_rf.regs[14].value)
    assert x14 == 0x7fff, f"x14: expected 0x7fff, got {x14:#010x}"

