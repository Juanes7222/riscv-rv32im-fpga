"""Functional evidence independent of benchmark termination and timing."""

import importlib.util
import sys
from pathlib import Path

from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))


def memory_words(dut):
    """Read the same word view from either data-memory implementation."""
    memory = dut.u_dmem
    if hasattr(memory, "mem_b0"):
        return [sum(int(getattr(memory, f"mem_b{lane}")[i].value) << (8 * lane)
                    for lane in range(4)) for i in range(len(memory.mem_b0))]
    return [int(word.value) for word in memory.mem]


def validate_coremark(dut, elf_path):
    """Require observed and expected CRCs when the ELF exposes a CMV1 record."""
    with open(elf_path, "rb") as stream:
        elf = ELFFile(stream)
        symbols = elf.get_section_by_name(".symtab").get_symbol_by_name(
            "coremark_validation")
        if not symbols:
            if "coremark" in str(elf_path).lower():
                return {"functional_valid": False, "reason": "missing CRC record"}
            return None
        address = int(symbols[0]["st_value"])
    words = memory_words(dut)
    record = [words[((address >> 2) + i) % len(words)] for i in range(16)]
    valid = (record[0] == 0x434d5631 and record[1] == 1
             and record[3:6] == record[6:9] and record[10] > 0
             and record[11] == 7 and record[12] == 0)
    return {"functional_valid": valid, "record_address": hex(address),
            "seed_crc": record[2], "observed": record[3:6],
            "expected": record[6:9], "final_crc": record[9],
            "iterations": record[10], "errors": record[12],
            "internal_timing_valid": bool(record[13]), "words": record}


def load_reference_model(imem_path, dmem_path):
    """Load the exact simulation images into the independent ISA model."""
    spec = importlib.util.spec_from_file_location(
        "reference_model", ROOT / "verification/reference_model/__init__.py",
        submodule_search_locations=[str(ROOT / "verification/reference_model")])
    module = importlib.util.module_from_spec(spec)
    sys.modules["reference_model"] = module
    spec.loader.exec_module(module)
    instructions = [int(line, 16) for line in imem_path.read_text().splitlines()]
    data = [int(line, 16) for line in dmem_path.read_text().splitlines()]
    model = module.CPU(imem_size=len(instructions) * 4, dmem_size=len(data) * 4)
    model.imem[:] = b"".join(w.to_bytes(4, "little") for w in instructions)
    model.dmem[:] = b"".join(w.to_bytes(4, "little") for w in data)
    return model


async def check_pipeline_retirement(dut, imem_path, dmem_path, tohost_addr):
    """Locate the first divergent instruction or register writeback."""
    from cocotb.triggers import FallingEdge, ReadOnly
    model = load_reference_model(imem_path, dmem_path)
    count = 0
    while True:
        await FallingEdge(dut.clk)
        await ReadOnly()
        if (int(dut.step_hold_effective.value) or int(dut.ex_div_busy.value)
                or not int(dut.wb_valid.value)):
            continue
        pc = int(dut.wb_pc.value)
        instruction = int(dut.wb_instruction.value)
        assert pc == model.pc, f"retire {count}: RTL PC={pc:#x}, model PC={model.pc:#x}"
        assert instruction == model._fetch(pc), f"Instruction mismatch at {pc:#x}"
        model.step()
        count += 1
        rd = int(dut.wb_rd_addr.value)
        if int(dut.wb_ru_wr.value) and rd:
            actual = int(dut.wb_rd_data.value)
            assert actual == model.regs[rd], (
                f"retire {count} PC={pc:#x} instruction={instruction:#010x}: "
                f"x{rd} RTL={actual:#x}, model={model.regs[rd]:#x}")
        if model.load_word(tohost_addr):
            return


def compare_reference_model(dut, imem_path, dmem_path, tohost_addr,
                            max_instructions, retired):
    """Compare all registers, DMEM and instruction count through tohost."""
    model = load_reference_model(imem_path, dmem_path)
    for count in range(1, max_instructions + 1):
        model.step()
        if model.load_word(tohost_addr):
            break
    else:
        raise AssertionError("Reference model did not reach tohost")
    actual_regs = [0] + [int(dut.u_rf.regs[i].value) for i in range(1, 32)]
    assert actual_regs == model.regs, [
        (i, hex(expected), hex(actual)) for i, (expected, actual)
        in enumerate(zip(model.regs, actual_regs)) if expected != actual]
    actual_data = b"".join(w.to_bytes(4, "little") for w in memory_words(dut))
    assert actual_data == model.dmem, "Final DMEM differs from reference model"
    assert count == retired, f"Retirement mismatch: model={count}, RTL={retired}"
    return {"valid": True, "instructions": count, "registers_compared": 32,
            "memory_bytes_compared": len(actual_data)}
