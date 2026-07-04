"""
Smoke tests for the pipelined RV32IM processor.

These tests verify the most basic pipeline operation: a single ADD
instruction completes after 5 cycles (IF, ID, EX, MEM, WB) and the
result is written to the destination register.

The pipeline takes 5 cycles for ONE instruction because each stage is
a separate cycle. A 5-instruction program takes 9 cycles to retire all
(5 fill-up + 4 drain = 9 cycles for 5 instructions, CPI = 9/5 = 1.8).
For a longer program, CPI approaches 1.0 because the pipeline can
overlap the stages.

The tests preload the imem via dut.u_imem.mem[k] (Icarus VPI access)
and step the clock the required number of times.
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut

# The reference_model package lives outside the cocotb test directory
# (at verification/reference_model/, while this file is in
# verification/cocotb/pipeline/). cocotb 2.0.1 + pytest's assertion-rewrite
# plugin break the plain `from reference_model import …` pattern (see ADR
# 036). Load via importlib instead.
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

encode_r = _reference_model.encode_r
encode_i = _reference_model.encode_i


async def _setup_and_run(dut, instruction, initial_regs, cycles):
    """Preload imem, set regs, then step `cycles` clock cycles.

    Returns when the test instruction has had time to retire through WB.
    For a single ADD: 5 cycles (IF, ID, EX, MEM, WB). For N back-to-back
    instructions, more cycles are needed (4 fill-up + N drain)."""
    await start_clock(dut)
    await reset_dut(dut)

    # Preload imem[0] with the test instruction.
    dut.u_imem.mem[0].value = instruction
    # Preload initial register state. regs[0] is never initialised by the
    # DUT's reset loop (`for (i=1; i<32; i++)`) so we set it explicitly.
    dut.u_rf.regs[0].value = 0
    for i in range(1, 32):
        dut.u_rf.regs[i].value = initial_regs.get(i, 0)
    await Timer(2, unit="ns")

    for _ in range(cycles):
        await step_clock(dut)


# ──────────────────────────────────────────────────────────────────────
# Single-instruction smoke tests
# ──────────────────────────────────────────────────────────────────────

@cocotb.test()
async def test_single_add_completes_in_5_cycles(dut):
    """ADD x1, x2, x3: x1 = x2 + x3 after 5 cycles (IF/ID/EX/MEM/WB)."""
    a, b = 0x12345678, 0x9ABCDEF0
    expected = (a + b) & 0xFFFFFFFF
    instr = encode_r(0, 3, 2, 0, 1)  # ADD x1, x2, x3
    await start_clock(dut)
    # Write imem BEFORE reset so sync-IMEM captures the instruction
    # during the reset period (otherwise the first posedge after reset
    # sees stale data and IF/ID captures it).
    for i in range(256):
        dut.u_imem.mem[i].value = 0x00000013
    dut.u_imem.mem[0].value = instr
    await reset_dut(dut)
    # Register init AFTER reset (reset clears registers).
    dut.u_rf.regs[2].value = a
    dut.u_rf.regs[3].value = b
    await Timer(2, unit="ns")
    for _ in range(5):
        await step_clock(dut)
    assert int(dut.u_rf.regs[1].value) == expected, (
        f"x1: expected {expected:#010x}, got {int(dut.u_rf.regs[1].value):#010x}"
    )


@cocotb.test()
async def test_single_sub_completes_in_5_cycles(dut):
    """SUB x1, x2, x3: x1 = x2 - x3 after 5 cycles."""
    a, b = 0x0000000A, 0x00000003
    expected = (a - b) & 0xFFFFFFFF
    instr = encode_r(0x20, 3, 2, 0, 1)  # SUB x1, x2, x3
    await start_clock(dut)
    for i in range(256):
        dut.u_imem.mem[i].value = 0x00000013
    dut.u_imem.mem[0].value = instr
    await reset_dut(dut)
    dut.u_rf.regs[2].value = a
    dut.u_rf.regs[3].value = b
    await Timer(2, unit="ns")
    for _ in range(5):
        await step_clock(dut)
    assert int(dut.u_rf.regs[1].value) == expected, (
        f"x1: expected {expected:#010x}, got {int(dut.u_rf.regs[1].value):#010x}"
    )


@cocotb.test()
async def test_load_use_stall_keeps_load_in_ex(dut):
    """LW x1, 0(x2); ADD x3, x1, x4.

    Without stall: the ADD would read x1 from the register file BEFORE
    the LW writes the loaded value, producing a stale result.
    With stall: the pipeline inserts a 1-cycle bubble so the LW can write
    x1 before the ADD reads it.

    This test exercises fix #1 (id_ex_register stall/flush separation)
    and fix #2 (EX/MEM and MEM/WB stall)."""
    addr = 0x100
    mem_val = 0xDEADBEEF
    expected = (mem_val + 0x42) & 0xFFFFFFFF

    from reference_model.encoders import encode_i
    lw  = encode_i(0, 2, 0b010, 1, opcode=0b0000011)   # LW x1, 0(x2)
    add = encode_r(0, 4, 1, 0, 3)                       # ADD x3, x1, x4

    await start_clock(dut)
    # Write imem and dmem BEFORE reset.
    word_addr = addr // 4
    dut.u_dmem.mem_b0[word_addr].value = (mem_val >>  0) & 0xFF
    dut.u_dmem.mem_b1[word_addr].value = (mem_val >>  8) & 0xFF
    dut.u_dmem.mem_b2[word_addr].value = (mem_val >> 16) & 0xFF
    dut.u_dmem.mem_b3[word_addr].value = (mem_val >> 24) & 0xFF
    for i in range(256):
        dut.u_imem.mem[i].value = 0x00000013
    dut.u_imem.mem[0].value = lw
    dut.u_imem.mem[1].value = add
    await reset_dut(dut)
    # Register init AFTER reset.
    dut.u_rf.regs[2].value = addr
    dut.u_rf.regs[4].value = 0x42
    await Timer(2, unit="ns")

    # Step until both instructions have retired.
    # LW: 5 cycles to retire (5-stage pipeline: IF1/IF2/ID/EX/MEM/WB).
    # ADD: 1 stall + 5 cycles to retire.
    # Total: 8 cycles minimum; we use 12 for margin.
    for cycle in range(12):
        await step_clock(dut)
        cocotb.log.info(
            f"cycle {cycle+1}: "
            f"if_id={int(dut.u_if_id.id_instruction.value):#010x} "
            f"id_ex={int(dut.u_id_ex.ex_instruction.value):#010x} "
            f"ex_mem={int(dut.u_ex_mem.mem_instruction.value):#010x} "
            f"mem_wb={int(dut.u_mem_wb.wb_instruction.value):#010x} "
            f"x1={int(dut.u_rf.regs[1].value):#010x} "
            f"x3={int(dut.u_rf.regs[3].value):#010x}"
        )

    assert int(dut.u_rf.regs[1].value) == mem_val, (
        f"x1 (load result): expected {mem_val:#010x}, "
        f"got {int(dut.u_rf.regs[1].value):#010x}"
    )
    assert int(dut.u_rf.regs[3].value) == expected, (
        f"x3 (add result): expected {expected:#010x}, "
        f"got {int(dut.u_rf.regs[3].value):#010x}"
    )


@cocotb.test()
async def test_wb_instruction_propagates_for_valid_wb(dut):
    """wb_instruction is the instruction in WB (not X). Validates fix #3.

    After 5 cycles, the ADD in imem[0] is in WB. wb_instruction should
    be the ADD encoding, not 32'h00000013 (the bubble).

    Note: the instruction_memory module loads its program from
    mem_config.vh's IMEM_FILE (a previously-built riscv-test ELF).
    We overwrite imem[0] with our test instruction AND overwrite
    imem[1..7] with bubbles so the test's pipeline state is
    deterministic - the loaded program doesn't follow our ADD."""
    instr = encode_r(0, 3, 2, 0, 1)  # ADD x1, x2, x3
    await start_clock(dut)
    for i in range(256):
        dut.u_imem.mem[i].value = 0x00000013
    dut.u_imem.mem[0].value = instr
    await reset_dut(dut)
    await Timer(2, unit="ns")
    # Step 4 cycles: at cycle 4 the ADD is in MEM/WB (and in wb_top).
    # At cycle 5 the ADD retires and the bubble overtakes it.
    for _ in range(4):
        await step_clock(dut)

    wb_instr = int(dut.wb_instruction.value)
    assert wb_instr == instr, (
        f"wb_instruction: expected {instr:#010x} (the ADD), "
        f"got {wb_instr:#010x}"
    )
