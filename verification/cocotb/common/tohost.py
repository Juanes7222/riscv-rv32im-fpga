import os
import pathlib
import subprocess
from typing import Union

from elftools.elf.elffile import ELFFile
import cocotb
from cocotb.triggers import RisingEdge

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


def generate_mem_for_elf(elf_path: pathlib.Path) -> None:
    """
    Convert an ELF to imem.mem + dmem.mem and regenerate mem_config.vh.
    Invokes the same scripts used by 'make flash' in the root Makefile.
    IMEM_DEPTH and DMEM_DEPTH must match RTL parameters (root Makefile: 4096 / 1024).
    """
    imem_depth = int(os.environ.get("IMEM_DEPTH", 4096))
    dmem_depth = int(os.environ.get("DMEM_DEPTH", 1024))

    bin_path  = BUILD_DIR / "program.bin"
    imem_path = BUILD_DIR / "imem.mem"
    dmem_path = BUILD_DIR / "dmem.mem"
    mem_cfg   = RTL_SHARED / "mem_config.vh"

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["riscv-none-elf-objcopy", "-O", "binary", str(elf_path), str(bin_path)],
        check=True,
    )
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
         "--dmem", str(dmem_path)],
        check=True,
    )


async def monitor_tohost(
    dut,
    elf_path: Union[str, pathlib.Path],
    max_cycles: int = MAX_CYCLES_DEFAULT,
) -> str:
    """
    Monitor the DUT data memory write bus for a write to the tohost symbol.

    Returns:
        "pass"       — tohost written with 1
        "timeout"    — max_cycles elapsed with no tohost write
        str(testnum) — tohost written with failure code; TESTNUM = value >> 1
    """
    tohost_byte_addr = get_tohost_addr(elf_path)
    tohost_word_addr = tohost_byte_addr >> 2  # DMEM is word-addressed (ADR 021)

    for _ in range(max_cycles):
        await RisingEdge(dut.clk)
        if (int(dut.dmwr.value)    == 1 and
                int(dut.dm_addr.value) == tohost_word_addr):
            written = int(dut.dm_wdata.value)
            if written == TOHOST_PASS_VALUE:
                return "pass"
            return str(written >> 1)

    return "timeout"