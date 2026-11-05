"""
Cocotb tests for the program_loader module, integrated through the top.

The loader writes one of up to 16 test programs into imem/dmem without
recompiling. Select with SW[0:3], load with KEY[2] (active low). Writes
only when the CPU is halted (SW[9] step_mode active).

Tests access signals through dut.u_loader.* (the program_loader instance
inside top_pipeline / top_single_cycle). step_hold is an internal signal,
so the test drives SW[9] (= step_mode) to freeze the CPU instead.
"""
import cocotb
from cocotb.triggers import Timer

from conftest import start_clock, step_clock, reset_dut

PROG_FIRST_WORD = {
    0: 0x00000013,  # halt: nop
    1: 0x00a00513,  # fibonacci: li a0,10
    2: 0x123450b7,  # alu_test: lui ra,0x12345
    3: 0x000010b7,  # mul_div_test: lui ra,0x1
    4: 0x00500093,  # factorial: li x1,5
    5: 0x00a00093,  # accumulator: li x1,10
}

PROG_LEN = {0: 2, 1: 13, 2: 22, 3: 14, 4: 8, 5: 8}


async def _press_key_load(dut):
    """Press KEY[2] (active low) across one rising clock edge, then release.

    The loader detects the press through a two-flop synchroniser, so the
    button must be low when a clock edge samples it."""
    dut.key_load.value = 0
    await step_clock(dut)
    dut.key_load.value = 1
    await Timer(2, unit="ns")


@cocotb.test()
async def test_loader_is_instantiated(dut):
    """Verify the program_loader exists inside the top and starts in IDLE."""
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)

    # After reset, the loader must be idle (no writes).
    assert int(dut.u_loader.imem_wr_en.value) == 0, (\
        "loader should be idle after reset")
    assert int(dut.u_loader.load_done.value) == 0, (\
        "load_done should be 0 after reset")


@cocotb.test()
async def test_loader_writes_fibonacci(dut):
    """Select program 1 (fibonacci) with SW[9]=1 (step_mode), pulse KEY[2], verify words written."""
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)

    # Freeze the CPU so the loader can write: step_mode = 1 (SW[9])
    dut.sw.value = 1              # program 1 (fibonacci)
    dut.step_mode.value = 1       # SW[9] = step_mode = 1, CPU frozen
    dut.key_load.value = 1        # released (active low)
    # The switch goes through a synchroniser: wait for the freeze to engage,
    # otherwise the loader ignores the request.
    for _ in range(6):
        if int(dut.step_hold_effective.value):
            break
        await step_clock(dut)
    await Timer(2, unit="ns")

    await _press_key_load(dut)

    # Step through the copy: wr_en should fire for every word of the program
    for i in range(PROG_LEN[1]):
        await step_clock(dut)
        if i < PROG_LEN[1] - 1:
            assert int(dut.u_loader.imem_wr_en.value) == 1, f"imem_wr_en should be 1 at word {i}"
            assert int(dut.u_loader.imem_wr_addr.value) == i * 4, f"addr should be {i * 4} at word {i}"

    # After the last word, one more cycle lands in S_DONE with load_done = 1
    await step_clock(dut)
    assert int(dut.u_loader.load_done.value) == 1, "load_done should pulse in S_DONE"
    assert int(dut.u_loader.imem_wr_en.value) == 0, "imem_wr_en should be 0 in S_DONE"


@cocotb.test()
async def test_loader_idle_when_not_halted(dut):
    """With step_mode=0 (CPU running), KEY[2] press must not start a copy."""
    await start_clock(dut)
    await reset_dut(dut, hold_cycles=2)

    dut.sw.value = 0x000          # step_mode = 0, CPU running
    dut.key_load.value = 1
    await Timer(2, unit="ns")

    await _press_key_load(dut)

    await step_clock(dut)
    await step_clock(dut)
    assert int(dut.u_loader.imem_wr_en.value) == 0, "imem_wr_en must stay 0 when CPU is not halted"
    assert int(dut.u_loader.load_done.value) == 0, "load_done must stay 0 when CPU is not halted"
