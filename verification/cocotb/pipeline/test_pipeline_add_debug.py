"""
Debug test for the pipeline add.elf hang at PC=0xe8.

Runs the add.elf test and dumps detailed pipeline state when PC approaches
the problem area, so we can diagnose why the pipeline gets stuck.
"""
import cocotb
from cocotb.triggers import Timer, RisingEdge, FallingEdge

from tohost import generate_mem_for_elf, reset_and_reload_memories, monitor_tohost, REPO_ROOT, get_tohost_addr
from conftest import start_clock, apply_reset

_TESTS_DIR = REPO_ROOT / "build" / "riscv-tests" / "rv32ui"

# Pipeline stage index to signal name mapping for top_pipeline
_STAGE_SIGNALS = {
    "if_pc":     "u_pcunit.pc",
    "if_imem_addr": "imem_addr",
    "if_instr":  "u_imem.instruction",
    "if_delayed_pc": "if_pc_delayed",
    "id_pc":     "u_if_id.id_pc",
    "id_instr":  "u_if_id.id_instruction",
    "ex_pc":     "u_id_ex.ex_pc",
    "ex_instr":  "u_id_ex.ex_instruction",
    "mem_pc":    "u_ex_mem.mem_pc",
    "mem_instr": "u_ex_mem.mem_instruction",
    "wb_pc":     "u_mem_wb.wb_pc",
    "wb_instr":  "u_mem_wb.wb_instruction",
    # Control
    "stall":     "stall",
    "flush":     "flush",
    "branch_flush": "branch_flush",
    "trap_flush": "trap_flush",
    "load_use":  "u_hdu.load_use",
    "ex_branch_taken": "ex_branch_taken",
    "div_busy":  "ex_div_busy",
    # EX stage internals
    "ex_alu_op":  "u_id_ex.ex_alu_op",
    "ex_br_op":   "u_id_ex.ex_br_op",
    "ex_alu_result": "ex_alu_result",
    "fwd_a":     "fwd_a_sel",
    "fwd_b":     "fwd_b_sel",
    # MEM stage
    "mem_alu_result": "mem_alu_result",
    "mem_dm_wr": "mem_dm_wr",
    "mem_ru_wr": "mem_ru_wr",
    "mem_rd_addr": "mem_rd_addr",
    "mem_rs2_data": "mem_rs2_data",
    # WB stage
    "wb_ru_wr":  "wb_ru_wr",
    "wb_rd_addr": "wb_rd_addr",
    "wb_trap_entry": "wb_trap_entry",
    "wb_mret_exec": "wb_mret_exec",
    "wb_ru_data_wr_src": "wb_ru_data_wr_src",
    # CSR
    "csr_mepc":  "u_csr.mepc",
    "csr_mtvec": "u_csr.mtvec",
    # HDU
    "ex_rd_addr_hdu": "u_id_ex.ex_rd_addr",
    "ex_ru_data_wr_src_hdu": "u_id_ex.ex_ru_data_wr_src",
    "mem_ru_wr_hdu": "u_ex_mem.mem_ru_wr",
    "mem_rd_addr_hdu": "u_ex_mem.mem_rd_addr",
}


async def _read_hex(dut, signal_path):
    """Safely read a signal as hex int."""
    try:
        val = eval(f"int(dut.{signal_path}.value)")
        return val
    except Exception:
        return None


async def _dump_pipeline_state(dut, cycle):
    """Dump the full pipeline state for one cycle."""
    lines = [f"--- Cycle {cycle} ---"]
    # Stage pipeline in order
    pc = await _read_hex(dut, "u_pcunit.pc")
    imem_addr = await _read_hex(dut, "imem_addr")
    imem_instr = await _read_hex(dut, "u_imem.instruction")
    id_pc = await _read_hex(dut, "u_if_id.id_pc")
    id_instr = await _read_hex(dut, "u_if_id.id_instruction")
    ex_pc = await _read_hex(dut, "u_id_ex.ex_pc")
    ex_instr = await _read_hex(dut, "u_id_ex.ex_instruction")
    mem_pc = await _read_hex(dut, "u_ex_mem.mem_pc")
    mem_instr = await _read_hex(dut, "u_ex_mem.mem_instruction")
    wb_pc = await _read_hex(dut, "u_mem_wb.wb_pc")
    wb_instr = await _read_hex(dut, "u_mem_wb.wb_instruction")

    stall = await _read_hex(dut, "stall")
    flush = await _read_hex(dut, "flush")
    branch_flush = await _read_hex(dut, "branch_flush")
    trap_flush = await _read_hex(dut, "trap_flush")
    ex_branch_taken = await _read_hex(dut, "ex_branch_taken")
    div_busy = await _read_hex(dut, "ex_div_busy")
    load_use = await _read_hex(dut, "u_hdu.load_use")

    ex_alu_result = await _read_hex(dut, "ex_alu_result")
    ex_br_op = await _read_hex(dut, "u_id_ex.ex_br_op")
    ex_alu_op = await _read_hex(dut, "u_id_ex.ex_alu_op")

    wb_trap = await _read_hex(dut, "wb_trap_entry")
    wb_mret = await _read_hex(dut, "wb_mret_exec")
    wb_ru_wr = await _read_hex(dut, "wb_ru_wr")
    wb_rd_addr = await _read_hex(dut, "wb_rd_addr")

    mem_rd_addr = await _read_hex(dut, "mem_rd_addr")
    mem_ru_wr = await _read_hex(dut, "mem_ru_wr")

    csr_mepc = await _read_hex(dut, "u_csr.mepc")
    csr_mtvec = await _read_hex(dut, "u_csr.mtvec")

    lines.append(f"  PC={pc:#010x} IMEM_ADDR={imem_addr:#010x} IMEM_INSTR={imem_instr:#010x}")
    lines.append(f"  IF/ID:  pc={id_pc:#010x} instr={id_instr:#010x}")
    lines.append(f"  ID/EX:  pc={ex_pc:#010x} instr={ex_instr:#010x} alu_op=0x{ex_alu_op:02x} br_op=0x{ex_br_op:02x}")
    lines.append(f"  EX/MEM: pc={mem_pc:#010x} instr={mem_instr:#010x} alu_res={ex_alu_result:#010x} rd=x{mem_rd_addr} ru_wr={mem_ru_wr}")
    lines.append(f"  MEM/WB: pc={wb_pc:#010x} instr={wb_instr:#010x} rd=x{wb_rd_addr} ru_wr={wb_ru_wr} trap={wb_trap} mret={wb_mret}")
    lines.append(f"  CTRL: stall={stall} flush={flush} branch_flush={branch_flush} trap_flush={trap_flush} br_taken={ex_branch_taken} load_use={load_use} div_busy={div_busy}")
    lines.append(f"  CSR:  mepc={csr_mepc:#010x} mtvec={csr_mtvec:#010x}")

    return "\n".join(lines)


@cocotb.test(name="test_pipeline_add_debug")
async def test_pipeline_add_debug(dut):
    """Debug the add.elf hang: log detailed pipeline state near PC=0xe8."""
    elf = _TESTS_DIR / "add.elf"
    if not elf.exists():
        raise FileNotFoundError(f"ELF not found: {elf}")

    await start_clock(dut)
    imem_path, dmem_path = generate_mem_for_elf(elf)
    await reset_and_reload_memories(dut, imem_path, dmem_path)
    await apply_reset(dut)

    tohost_byte_addr = get_tohost_addr(elf)
    tohost_word_addr = tohost_byte_addr >> 2
    cocotb.log.info(f"tohost byte_addr={tohost_byte_addr:#x} word_addr={tohost_word_addr:#x}")

    # Run for up to 2000 cycles with detailed logging, especially around 0xe8
    max_cycles = 2000
    last_pc = None
    pc_lock_count = 0
    stall_entry_cycle = None

    for cycle in range(max_cycles):
        await FallingEdge(dut.clk)

        # Monitor tohost write
        try:
            dm_wr = int(dut.mem_dm_wr.value)
            dm_addr_val = int(dut.mem_alu_result.value)
        except Exception:
            dm_wr = 0
            dm_addr_val = -1

        addr_matches = (dm_addr_val == tohost_byte_addr or dm_addr_val == tohost_word_addr)

        if dm_wr == 1:
            cocotb.log.info(f"Cycle {cycle}: DMEM WRITE addr={dm_addr_val:#x} data={int(dut.mem_rs2_data.value):#x}")

        if dm_wr == 1 and addr_matches:
            written = int(dut.mem_rs2_data.value)
            cocotb.log.info(f"Cycle {cycle}: TOHOST WRITE value={written:#x}")
            if written == 1:
                cocotb.log.info("PASS")
                return
            else:
                cocotb.log.error(f"FAIL: TESTNUM={(written >> 1)}")
                return

        # PC tracking
        try:
            pc_val = int(dut.u_pcunit.pc.value)
        except Exception:
            pc_val = None

        # Detailed logging when PC approaches 0xe8 or gets stuck
        if pc_val is not None and pc_val in [0xdc, 0xe0, 0xe4, 0xe8, 0xec, 0xf0, 0xf4]:
            state = await _dump_pipeline_state(dut, cycle)
            cocotb.log.info(state)

        # Detect PC lock
        if pc_val == last_pc and pc_val is not None:
            pc_lock_count += 1
            if pc_lock_count == 1:
                stall_entry_cycle = cycle
        else:
            pc_lock_count = 0
            stall_entry_cycle = None

        # If PC has been locked for >10 cycles, dump state and break
        if pc_lock_count >= 30:
            cocotb.log.error(f"PC LOCKED at {pc_val:#010x} for {pc_lock_count} cycles (since cycle {stall_entry_cycle})")
            state = await _dump_pipeline_state(dut, cycle)
            cocotb.log.error(state)
            # Dump a few more cycles
            for extra in range(5):
                await RisingEdge(dut.clk)
                await FallingEdge(dut.clk)
                state = await _dump_pipeline_state(dut, cycle + extra + 1)
                cocotb.log.error(state)
            break

        last_pc = pc_val
        await RisingEdge(dut.clk)

    assert False, "PC never locked or tohost never written — check logs"
