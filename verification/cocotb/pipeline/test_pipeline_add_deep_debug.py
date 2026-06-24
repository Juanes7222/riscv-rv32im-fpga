"""
Debug test: log ALL pipeline state from cycle 0 to diagnose the stall root cause.
"""
import cocotb
from cocotb.triggers import Timer, RisingEdge, FallingEdge

from tohost import generate_mem_for_elf, reset_and_reload_memories, REPO_ROOT, get_tohost_addr
from conftest import start_clock, apply_reset

_TESTS_DIR = REPO_ROOT / "build" / "riscv-tests" / "rv32ui"


async def _r(dut, sig):
    try:
        return int(eval(f"dut.{sig}.value"))
    except:
        return None


@cocotb.test(name="test_pipeline_add_deep_debug")
async def test_pipeline_add_deep_debug(dut):
    """Trace the full pipeline from cycle 0 until stall detected."""
    elf = _TESTS_DIR / "add.elf"

    await start_clock(dut)
    imem_path, dmem_path = generate_mem_for_elf(elf)
    await reset_and_reload_memories(dut, imem_path, dmem_path)
    await apply_reset(dut)

    tohost_byte_addr = get_tohost_addr(elf)
    cocotb.log.info(f"tohost={tohost_byte_addr:#x}")

    last_pc = -1
    same_pc_count = 0

    for cycle in range(500):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")  # small delay for combinational settling

        pc = await _r(dut, "u_pcunit.pc")
        id_instr = await _r(dut, "u_if_id.id_instruction")
        ex_instr = await _r(dut, "u_id_ex.ex_instruction")
        mem_instr = await _r(dut, "u_ex_mem.mem_instruction")
        wb_instr = await _r(dut, "u_mem_wb.wb_instruction")
        stall = await _r(dut, "stall")
        load_use = await _r(dut, "u_hdu.load_use")
        mem_ru_wr_hdu = await _r(dut, "u_ex_mem.mem_ru_wr")
        mem_rd_addr_hdu = await _r(dut, "u_ex_mem.mem_rd_addr")
        id_rs1 = await _r(dut, "u_if_id.id_instruction")  # need to extract
        ex_ru_data_wr_src = await _r(dut, "u_id_ex.ex_ru_data_wr_src")
        mem_ru_data_wr_src = await _r(dut, "u_ex_mem.mem_ru_data_wr_src")
        div_busy = await _r(dut, "ex_div_busy")
        ex_rd_addr = await _r(dut, "u_id_ex.ex_rd_addr")
        id_pc = await _r(dut, "u_if_id.id_pc")
        ex_pc = await _r(dut, "u_id_ex.ex_pc")
        mem_pc = await _r(dut, "u_ex_mem.mem_pc")
        wb_pc = await _r(dut, "u_mem_wb.wb_pc")

        # Extract rs1 from instruction in ID
        if id_instr is not None:
            id_rs1_addr = (id_instr >> 15) & 0x1F
            id_rs2_addr = (id_instr >> 20) & 0x1F
        else:
            id_rs1_addr = id_rs2_addr = 0

        # Also check tohost
        try:
            dm_wr = int(dut.mem_dm_wr.value)
            dm_addr = int(dut.mem_alu_result.value)
            if dm_wr and (dm_addr == tohost_byte_addr or dm_addr == tohost_byte_addr >> 2):
                cocotb.log.info(f"TOHOST at cycle {cycle}: val={int(dut.mem_rs2_data.value):#x}")
                return
        except:
            pass

        # PC tracking
        if pc == last_pc:
            same_pc_count += 1
        else:
            same_pc_count = 0
        last_pc = pc

        # Log every cycle until stall, then log remaining
        stall_detected = same_pc_count >= 3 and stall == 1
        log_it = stall_detected or cycle < 80 or same_pc_count < 5

        if log_it and cycle < 100:
            cocotb.log.info(
                f"C{cycle:3d}: PC={pc:#010x} stall={stall} LU={load_use} div={div_busy} "
                f"id_rs1=x{id_rs1_addr} id_rs2=x{id_rs2_addr} "
                f"ex_rd=x{ex_rd_addr} ex_wsrc={ex_ru_data_wr_src} "
                f"mem_rd=x{mem_rd_addr_hdu} mem_rw={mem_ru_wr_hdu} mem_wsrc={mem_ru_data_wr_src} "
                f"| IFID:{id_instr:#010x}(pc={id_pc:#x}) "
                f"IDEX:{ex_instr:#010x}(pc={ex_pc:#x}) "
                f"EXMEM:{mem_instr:#010x}(pc={mem_pc:#x}) "
                f"MEMWB:{wb_instr:#010x}(pc={wb_pc:#x})"
            )

        if same_pc_count >= 30:
            cocotb.log.error(
                f"DEADLOCK: PC={pc:#x} locked for {same_pc_count} cycles"
            )
            break

    assert False, "Check logs for diagnosis"
