"""Regression probe for the final `j .` after the tohost write.

The board run of CoreMark reaches the store to tohost and then shows the PC
alternating between 0x0000 and 0x0044 instead of staying at 0x0044.  This test
loads the same tail into the instruction memory and logs the pipeline PCs so the
failure can be reproduced (or ruled out) in RTL simulation.
"""
import cocotb

from conftest import reset_dut, step_clock

# 0x00: addi x5, x0, 1
# 0x04: lui  x6, 0
# 0x08: addi x6, x6, 0x708
# 0x0c: sw   x5, 0(x6)        -> tohost
# 0x10..0x40: nops
# 0x44: j .                   -> 0x0000006f
PROG = [
    0x00100293,
    0x00000337,
    0x70830313,
    0x00532023,
] + [0x00000013] * 13 + [0x0000006F]


@cocotb.test()
async def test_jump_to_self_after_tohost(dut):
    await reset_dut(dut)
    for index, word in enumerate(PROG):
        dut.u_imem.mem[index].value = word

    trace = []
    for _ in range(60):
        await step_clock(dut)
        trace.append((
            int(dut.if_pc.value),
            int(dut.id_pc.value),
            int(dut.ex_pc.value),
            int(dut.ex_instruction.value),
            int(dut.pc_redirect_target.value),
            int(dut.branch_flush.value),
        ))

    dut._log.info("PC trace (if, id, ex, ex_instr, target, branch):")
    for index, row in enumerate(trace):
        dut._log.info("  %02d: if=%08x id=%08x ex=%08x instr=%08x target=%08x br=%d",
                      index, *row)

    pcs = [row[0] for row in trace]
    assert 0x44 in pcs, f"the program never reached 0x44: {[hex(p) for p in pcs]}"
    after = pcs[pcs.index(0x44):]
    assert 0 not in after, (
        "the jump at 0x44 went to 0 in RTL simulation: "
        f"{[hex(p) for p in after[:20]]}"
    )
    assert after.count(0x44) > 1, (
        "the jump at 0x44 did not keep executing at 0x44: "
        f"{[hex(p) for p in after[:20]]}"
    )
