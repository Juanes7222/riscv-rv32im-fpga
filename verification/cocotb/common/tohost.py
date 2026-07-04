import os
import pathlib
import subprocess
from typing import Union

from elftools.elf.elffile import ELFFile
import cocotb
from cocotb.triggers import RisingEdge, FallingEdge

MAX_CYCLES_DEFAULT = 200_000
TOHOST_PASS_VALUE  = 1

REPO_ROOT    = pathlib.Path(os.environ.get("REPO_ROOT", pathlib.Path(__file__).parents[3]))
SCRIPTS_ROOT = pathlib.Path(os.environ.get("SCRIPTS_ROOT", REPO_ROOT / "scripts"))
RTL_SHARED   = pathlib.Path(os.environ.get("RTL_SHARED",   REPO_ROOT / "rtl" / "shared"))
BUILD_DIR    = pathlib.Path(os.environ.get("BUILD_DIR",    REPO_ROOT / "build"))


def get_tohost_addr(elf_path: Union[str, pathlib.Path]) -> int:
    with open(elf_path, "rb") as f:
        elf = ELFFile(f)
        symtab = elf.get_section_by_name(".symtab")
        if symtab is None:
            raise RuntimeError(f"No .symtab in {elf_path}")
        symbols = symtab.get_symbol_by_name("tohost")
        if not symbols:
            raise RuntimeError(f"Symbol 'tohost' not found in {elf_path}")
        return symbols[0].entry["st_value"]


def _elf_to_raw_binary(elf_path: pathlib.Path, bin_path: pathlib.Path) -> None:
    """Generate a raw memory image from ELF PT_LOAD segments without objcopy."""
    with open(elf_path, "rb") as f:
        elf = ELFFile(f)
        load_segments = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]

        if not load_segments:
            raise RuntimeError(f"No PT_LOAD segments in {elf_path}")

        starts = []
        ends = []
        for seg in load_segments:
            start = int(seg["p_paddr"] or seg["p_vaddr"])
            end = start + int(seg["p_filesz"])
            starts.append(start)
            ends.append(end)

        base = min(starts)
        limit = max(ends)
        image = bytearray(limit - base)

        for seg in load_segments:
            start = int(seg["p_paddr"] or seg["p_vaddr"])
            data = seg.data()
            off = start - base
            image[off:off + len(data)] = data

    with open(bin_path, "wb") as out:
        out.write(image)


def generate_mem_for_elf(elf_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """
    Convert an ELF to imem.mem + dmem.mem and regenerate mem_config.vh.
    Invokes the same scripts used by 'make flash' in the root Makefile.
    IMEM_DEPTH and DMEM_DEPTH must match RTL parameters (root Makefile: 4096 / 1024).
    """
    # In synthesis (rtl/shared/): IMEM_DEPTH=16384, DMEM_DEPTH=8192.
    # The cocotb Makefiles export these; fallback matches the RTL defaults.
    imem_depth = int(os.environ.get("IMEM_DEPTH", 16384))
    dmem_depth = int(os.environ.get("DMEM_DEPTH", 8192))

    bin_path  = BUILD_DIR / "program.bin"
    imem_path = BUILD_DIR / "imem.mem"
    dmem_path = BUILD_DIR / "dmem.mem"
    mem_cfg   = RTL_SHARED / "mem_config.vh"

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # Build raw binary from ELF in pure Python to avoid host objcopy dependency.
    _elf_to_raw_binary(elf_path, bin_path)

    subprocess.run(
        ["python3", str(SCRIPTS_ROOT / "elf_to_mem.py"),
         str(bin_path), str(imem_depth), str(imem_path)],
        check=True,
    )
    subprocess.run(
        ["python3", str(SCRIPTS_ROOT / "elf_to_mem.py"),
         str(bin_path), str(dmem_depth), str(dmem_path)],
        check=True,
    )
    subprocess.run(
        ["python3", str(SCRIPTS_ROOT / "gen_mem_config.py"),
         "--imem", str(imem_path),
         "--dmem", str(dmem_path),
         "--relative-to", os.getcwd(),
         "--validate-linux-path", str(imem_path),
         "--validate-linux-dmem", str(dmem_path)],
        check=True,
    )
    return imem_path, dmem_path


def _parse_mem_file(mem_file: pathlib.Path) -> list[int]:
    words = []
    with open(mem_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("//"):
                words.append(int(line, 16))
    return words

def _write_mem_array(mem_handle, words: list[int]) -> None:
    for addr, word in enumerate(words):
        mem_handle[addr].value = word


def _write_dmem_pipe(dmem, words: list[int]) -> None:
    """Write words to the pipeline DMEM's four byte-lane arrays.

    The pipeline's data_memory_pipe uses mem_b0..mem_b3 (8-bit arrays)
    to enable M10K inference. Each 32-bit word is split across the four
    lanes: mem_b0 = bits[7:0], mem_b1 = bits[15:8], mem_b2 = bits[23:16],
    mem_b3 = bits[31:24]."""
    for addr, word in enumerate(words):
        dmem.mem_b0[addr].value = (word >>  0) & 0xFF
        dmem.mem_b1[addr].value = (word >>  8) & 0xFF
        dmem.mem_b2[addr].value = (word >> 16) & 0xFF
        dmem.mem_b3[addr].value = (word >> 24) & 0xFF

async def _apply_reset(dut, reset_cycles: int = 5) -> None:
    # Assert active-low reset, hold for `reset_cycles` clocks, then deassert.
    dut.rst_n.value = 0
    for _ in range(reset_cycles):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

def reload_memories(dut, imem_path: pathlib.Path, dmem_path: pathlib.Path) -> None:
    imem_words = _parse_mem_file(imem_path)
    dmem_words = _parse_mem_file(dmem_path)
    _write_mem_array(dut.u_imem.mem, imem_words)
    # The pipeline DMEM uses four byte-lane arrays (mem_b0..mem_b3) for
    # M10K inference; the single-cycle DMEM uses a single mem[addr] array.
    # Try the pipeline path first, fall back to the shared path.
    try:
        _ = dut.u_dmem.mem_b0
        _write_dmem_pipe(dut.u_dmem, dmem_words)
    except AttributeError:
        _write_mem_array(dut.u_dmem.mem, dmem_words)

async def reset_and_reload_memories(
    dut,
    imem_path: pathlib.Path,
    dmem_path: pathlib.Path,
    reset_cycles: int = 5,
) -> None:
    await _apply_reset(dut, reset_cycles)
    reload_memories(dut, imem_path, dmem_path)
    await _apply_reset(dut, reset_cycles)

async def monitor_tohost(
    dut,
    elf_path: Union[str, pathlib.Path],
    max_cycles: int = MAX_CYCLES_DEFAULT,
) -> str:
    """
    Monitor the DUT data memory write bus for a write to the tohost symbol.

    Returns:
        "pass"       - tohost written with 1
        "timeout"    - max_cycles elapsed with no tohost write
        str(testnum) - tohost written with failure code; TESTNUM = value >> 1
    """
    tohost_byte_addr = get_tohost_addr(elf_path)
    tohost_word_addr = tohost_byte_addr >> 2
    cocotb.log.info(f"tohost byte_addr={tohost_byte_addr:#x} word_addr={tohost_word_addr:#x}")

    # Detect whether the DUT is the single-cycle or the pipelined design.
    # The pipeline exposes MEM-stage signals; single-cycle exposes top-level
    # dm_wr/dm_addr/dm_wdata.
    try:
        _ = dut.mem_dm_wr
        _pipeline = True
    except Exception:
        _pipeline = False

    # In single-cycle designs dm_wr/addr/data are combinational for the
    # current instruction and can change right after the rising edge when PC
    # advances. Sample on falling edge to observe stable intent for the write.
    for cycle in range(max_cycles):
        await FallingEdge(dut.clk)
        if _pipeline:
            try:
                dm_wr = int(dut.mem_dm_wr.value)
                dm_addr_val = int(dut.mem_alu_result.value)
            except Exception:
                dm_wr = 0
                dm_addr_val = -1
        else:
            try:
                dm_wr = int(dut.dm_wr.value)
                dm_addr_val = int(dut.dm_addr.value)
            except Exception:
                dm_wr = 0
                dm_addr_val = -1

        addr_matches = (dm_addr_val == tohost_byte_addr or dm_addr_val == tohost_word_addr)

        # Debug: log any store in MEM and PC
        if dm_wr == 1 and cycle < 200:
            cocotb.log.info(f"Cycle {cycle}: DM write: addr={dm_addr_val:#x} data={int(dut.mem_rs2_data.value if _pipeline else dut.dm_wdata.value):#x}")
        if cycle % 1000 == 0 and _pipeline:
            try:
                pc_val = int(dut.u_pcunit.pc.value)
                cocotb.log.info(f"Cycle {cycle}: PC={pc_val:#x} dm_wr={dm_wr}")
            except:
                pass

        if dm_wr == 1 and addr_matches:
            if _pipeline:
                written = int(dut.mem_rs2_data.value)
            else:
                written = int(dut.dm_wdata.value)
            if written == TOHOST_PASS_VALUE:
                return "pass"
            return str(written >> 1)

        await RisingEdge(dut.clk)

    return "timeout"