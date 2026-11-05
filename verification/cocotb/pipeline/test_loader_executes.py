"""Program-loader end-to-end test for the pipelined processor.

Loads the fibonacci program at runtime and verifies:
  1. imem[] holds the copied program (the loader's write port works), and
  2. the CPU executes it from PC=0 after the loader's automatic reset pulse
     (the first instruction `li a0,10` writes x10 = 10).

This test is pipeline-specific: it depends on the loader->CPU reset pulse
that top_pipeline generates on load_done so the loaded program starts at the
reset vector without a KEY[0] press.  The single-cycle top already runs the
loaded program after a manual KEY[0] reset.
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut

PROG_LEN = {0: 2, 1: 13, 2: 22, 3: 14, 4: 8, 5: 8}

FIBONACCI = [
    0x00a00513, 0x00000593, 0x00100613, 0x00100693, 0x00a6dc63,
    0x00c58733, 0x00060593, 0x00070613, 0x00168693, 0xfedff06f,
    0x00a00893, 0x00000073, 0xff9ff06f,
]


async def _press_key_load(dut):
    """Press KEY[2] (active low) across one rising clock edge, then release."""
    dut.key_load.value = 0
    await step_clock(dut)
    dut.key_load.value = 1
    await Timer(2, unit="ns")


@cocotb.test()
async def test_loader_fibonacci_executes_from_pc0(dut):
    """Load fibonacci, check imem is filled and x10 == 10 after auto-restart."""
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)

    dut.sw.value = 1              # program 1 (fibonacci)
    dut.step_mode.value = 1       # SW[9] = step_mode = 1, CPU frozen
    dut.key_load.value = 1        # released (active low)
    for _ in range(6):
        if int(dut.step_hold_effective.value):
            break
        await step_clock(dut)
    await Timer(2, unit="ns")

    await _press_key_load(dut)

    # Let the copy finish (load_done fires a one-cycle CPU reset pulse that
    # restarts the PC at 0), then release the freeze so execution runs.
    for _ in range(PROG_LEN[1] + 6):
        await step_clock(dut)

    # imem must hold the fibonacci program the loader copied.
    for i, word in enumerate(FIBONACCI):
        assert int(dut.u_imem.mem[i].value) == word, (
            f"imem[{i}] not programmed: "
            f"{int(dut.u_imem.mem[i].value):#010x} (expected {word:#010x})"
        )

    # li a0,10 writes x10 = 10 early in execution.
    dut.step_mode.value = 0
    for _ in range(6):
        if not int(dut.step_hold_effective.value):
            break
        await step_clock(dut)
    for _ in range(30):
        await step_clock(dut)
    assert int(dut.u_rf.regs[10].value) == 10, (
        f"fibonacci did not execute from PC=0: x10 = "
        f"{int(dut.u_rf.regs[10].value):#010x}"
    )
