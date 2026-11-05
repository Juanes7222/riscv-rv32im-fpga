#!/usr/bin/env python3
"""Split an ELF into the instruction and data memory images.

The processor has two independent memories with independent address
decoders, so each one gets its own image:

  * instruction memory: the executable sections (.text*), at their own
    addresses;
  * data memory: every other allocated section (.rodata*, .data*, .bss*,
    .tohost), relative to the base of the data window.  .rodata belongs here
    even though it is read-only: the program reads it with loads, and the
    instruction memory is not addressable by a load.

Words outside the sections are NOP in the instruction image and zero in the
data image.  Before ADR 047 both memories shared one flat image, which forced
the data sections above .text and made a 2 KB data image need 32 KB of
address space.

Usage:
    python3 elf_to_mem_split.py program.elf \
        --imem-depth 4096 --imem-out build/imem.mem \
        --dmem-depth 1024 --dmem-base 0x6000 --dmem-out build/dmem.mem
"""

import argparse
from pathlib import Path

from elftools.elf.elffile import ELFFile

NOP_WORD = 0x00002013
SHF_WRITE = 0x1
SHF_ALLOC = 0x2
SHF_EXECINSTR = 0x4


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf_path", type=Path)
    parser.add_argument("--imem-depth", type=int, required=True,
                        help="instruction memory depth in 32-bit words")
    parser.add_argument("--imem-out", type=Path, required=True)
    parser.add_argument("--dmem-depth", type=int, required=True,
                        help="data memory depth in 32-bit words")
    parser.add_argument("--dmem-base", type=lambda s: int(s, 0), default=None,
                        help="lowest address the data memory answers; the data "
                             "memory decodes the low address bits, so any 4 KB "
                             "multiple works.  Default: the 4 KB boundary at or "
                             "below the lowest writable section.")
    parser.add_argument("--dmem-out", type=Path, required=True)
    return parser.parse_args()


def load_sections(elf_path: Path) -> tuple[list, list]:
    """Split the allocated sections into (instruction, data) section lists.

    A section goes to the data memory when it is writable.  Sections with no
    contents in the file (.bss, .stack) are skipped: the image is zero there.
    """
    instruction = []
    data = []
    with open(elf_path, "rb") as f:
        elf = ELFFile(f)
        for section in elf.iter_sections():
            if not section["sh_flags"] & SHF_ALLOC:
                continue
            if section["sh_type"] == "SHT_NOBITS" or section["sh_size"] == 0:
                continue
            address = int(section["sh_addr"])
            if address % 4:
                raise ValueError(
                    f"section {section.name} at {address:#x} is not word aligned")
            # Executable sections are fetched from the instruction memory; every
            # other allocated section is *read as data* and therefore has to be
            # in the data image too - .rodata holds CoreMark's CRC tables, and a
            # missing copy makes the benchmark fail its own verification.
            target = (instruction if section["sh_flags"] & SHF_EXECINSTR
                      else data)
            target.append((section.name, address, section.data()))
    if not instruction:
        raise ValueError(f"{elf_path}: expected a code section")
    return instruction, data


def build_image(sections: list, base: int, depth: int, pad: int,
                what: str) -> list[int]:
    """Place the sections inside [base, base+depth*4) into a padded word image."""
    limit = base + depth * 4
    words = [pad] * depth
    owner = {}
    for name, address, data in sections:
        if not base <= address:
            raise ValueError(
                f"{what}: section {name} at {address:#x} is below the {base:#x} base")
        if address + len(data) > limit:
            raise ValueError(
                f"{what}: section {name} ends at {address + len(data):#x}, past the "
                f"{limit:#x} limit of {depth} words")
        # The memories decode the low address bits, so the image index is the
        # truncated word address: (address >> 2) & (depth - 1).  Indexing
        # relative to `base` instead only matches when depth * 4 <= 4 KB; with
        # a deeper simulation memory (8192 words) CoreMark's window at 0x6000
        # would land at index 6144 while the image sat at index 0.
        first = (address >> 2) & (depth - 1)
        if first + len(data) // 4 > depth:
            raise ValueError(
                f"{what}: section {name} at {address:#x} crosses the end of the "
                f"{depth}-word window")
        for i in range(len(data) // 4):
            if first + i in owner:
                raise ValueError(
                    f"{what}: section {name} at {address:#x} overlaps {owner[first + i]}")
            owner[first + i] = name
            words[first + i] = int.from_bytes(data[i * 4:i * 4 + 4], "little")
    return words


def write_mem(words: list[int], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{w:08x}\n" for w in words), encoding="ascii")


def main() -> int:
    args = parse_arguments()
    instruction, data = load_sections(args.elf_path)

    # The data memory decodes the low address bits, so the image base is the
    # 4 KB boundary at or below the lowest data section: 0 for a map that
    # starts at 0x708, 0x6000 for CoreMark's window.
    base = args.dmem_base
    if base is None:
        if data:
            lowest = min(address for _, address, _ in data)
            base = (lowest // 4096) * 4096
        else:
            base = 0

    write_mem(build_image(instruction, 0, args.imem_depth, NOP_WORD,
                          "instruction memory"), args.imem_out)
    write_mem(build_image(data, base, args.dmem_depth, 0,
                          "data memory"), args.dmem_out)
    print(f"data memory base {base:#x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
