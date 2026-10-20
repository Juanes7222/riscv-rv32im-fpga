#!/usr/bin/env python3
"""Verify that the memory images compiled into the FPGA bitstream are the intended ones.

The program reaches the hardware through two files:

  * rtl/shared/mem_config.vh  -> $readmemh paths for IMEM and DMEM
  * synthesis/<arch>/screen.mif -> video memory template (console layout)

Quartus turns both into .hdl.mif files under synthesis/<arch>/db/.  This script
reads those generated files back and compares them with the .mem sources, so a
mismatch between "the program I asked for" and "the program inside the .sof"
cannot pass unnoticed.

Usage:
    python3 scripts/check_mem_init.py --project synthesis/pipeline
    python3 scripts/check_mem_init.py --project synthesis/single_cycle
"""

import argparse
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def parse_quartus_mif(path: pathlib.Path) -> dict[int, int]:
    """Parse a Quartus .mif into {address: value}."""
    cells: dict[int, int] = {}
    width = 0
    radix = "HEX"
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("WIDTH="):
            width = int(stripped.split("=")[1].rstrip(";"))
            continue
        if stripped.startswith("DATA_RADIX="):
            radix = stripped.split("=")[1].rstrip(";")
            continue
        match = re.match(r"(\d+)\s*:\s*([0-9A-Fa-f]+)\s*;", stripped)
        if not match:
            continue
        value = int(match.group(2), 16 if radix == "HEX" else 2)
        cells[int(match.group(1))] = value & ((1 << width) - 1)
    return cells


def parse_mem_file(path: pathlib.Path) -> list[int]:
    """Parse a $readmemh image: one 32-bit hex word per line."""
    words: list[int] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            words.append(int(line, 16))
    return words


def read_defines(header: pathlib.Path) -> dict[str, str]:
    """Extract the `define macros from the generated memory configuration header."""
    defines: dict[str, str] = {}
    for line in header.read_text().splitlines():
        match = re.match(r"`define\s+(\w+)\s+\"([^\"]*)\"", line.strip())
        if match:
            defines[match.group(1)] = match.group(2)
    return defines


def resolve(project_dir: pathlib.Path, relative: str) -> pathlib.Path:
    """Quartus resolves $readmemh paths against the project directory."""
    return (project_dir / relative).resolve()


def compare_words(label: str, generated: dict[int, int], expected: list[int],
                  depth: int) -> bool:
    """Compare {address: word} against the expected word list."""
    mismatches = []
    for address in range(depth):
        got = generated.get(address)
        want = expected[address] if address < len(expected) else 0
        if got != want:
            mismatches.append((address, got, want))
    if not mismatches:
        print(f"  PASS  {label}: {depth} words identical")
        return True
    print(f"  FAIL  {label}: {len(mismatches)}/{depth} words differ")
    for address, got, want in mismatches[:5]:
        print(f"          addr {address:#06x}: bitstream {got!r} != source {want!r}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True,
                        help="Quartus project directory (e.g. synthesis/pipeline)")
    parser.add_argument("--imem", default=None,
                        help="Expected IMEM .mem (default: resolve from mem_config.vh)")
    parser.add_argument("--dmem", default=None,
                        help="Expected DMEM .mem (default: resolve from mem_config.vh)")
    args = parser.parse_args()

    project_dir = (REPO_ROOT / args.project).resolve()
    header = REPO_ROOT / "rtl" / "shared" / "mem_config.vh"
    db_dir = project_dir / "db"

    if not header.exists():
        print(f"ERROR: {header} not found. Run the memory generation step first.")
        return 2

    defines = read_defines(header)
    print(f"Project      : {project_dir}")
    print(f"mem_config.vh: IMEM={defines.get('IMEM_FILE')} DMEM={defines.get('DMEM_FILE')}")

    ok = True

    # ---- 1. The $readmemh paths must resolve from the project directory ----
    sources = {}
    for macro, override in (("IMEM_FILE", args.imem), ("DMEM_FILE", args.dmem)):
        if override is not None:
            path = (REPO_ROOT / override).resolve()
        else:
            raw = defines.get(macro, "")
            if not raw:
                continue
            path = resolve(project_dir, raw)
        if not path.exists():
            print(f"  FAIL  {macro}: {path} does not exist "
                  f"(relative to the project directory)")
            ok = False
            continue
        print(f"  ok    {macro} -> {path}")
        sources[macro] = path

    # ---- 2. The instruction memory inside the bitstream ----
    imem_mifs = sorted(db_dir.glob("*instruction_memory*.hdl.mif"))
    if not imem_mifs:
        print("  WARN  no instruction memory .hdl.mif found (memory not inferred as RAM)")
    else:
        imem_words = parse_mem_file(sources["IMEM_FILE"]) if "IMEM_FILE" in sources else []
        for mif in imem_mifs:
            cells = parse_quartus_mif(mif)
            depth = max(cells) + 1 if cells else 0
            print(f"IMEM {mif.name} (depth {depth})")
            if not imem_words:
                print("  FAIL  no IMEM source to compare against")
                ok = False
                continue
            ok &= compare_words("IMEM", cells, imem_words, depth)

    # ---- 3. The data memory inside the bitstream ----
    dmem_mifs = sorted(db_dir.glob("*data_memory*.hdl.mif"))
    if not dmem_mifs:
        print("  INFO  no data memory .hdl.mif (data memory implemented in logic cells)")
    elif "DMEM_FILE" in sources:
        dmem_words = parse_mem_file(sources["DMEM_FILE"])
        # The pipelined data memory uses one .mif per byte lane; the single-cycle
        # one uses a single 32-bit-wide .mif.
        lanes = [parse_quartus_mif(m) for m in dmem_mifs]
        if len(lanes) == 4:
            depth = max(lanes[0]) + 1 if lanes[0] else 0
            print(f"DMEM {len(lanes)} byte lanes (depth {depth})")
            merged = {}
            for address in range(depth):
                merged[address] = (lanes[0].get(address, 0)
                                   | (lanes[1].get(address, 0) << 8)
                                   | (lanes[2].get(address, 0) << 16)
                                   | (lanes[3].get(address, 0) << 24))
            ok &= compare_words("DMEM", merged, dmem_words, depth)
        else:
            depth = max(lanes[0]) + 1 if lanes[0] else 0
            print(f"DMEM {dmem_mifs[0].name} (depth {depth})")
            ok &= compare_words("DMEM", lanes[0], dmem_words, depth)

    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
