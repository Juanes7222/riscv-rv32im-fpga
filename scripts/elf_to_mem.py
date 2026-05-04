#!/usr/bin/env python3
# Converts a flat binary image produced by objcopy -O binary into a .mem file
# readable by $readmemh in SystemVerilog (one 32-bit word per line, little-endian).

import argparse
import sys
from pathlib import Path

WORD_SIZE_BYTES = 4
NOP_WORD = "00002013"  # ADDI x0, x0, 0 — fills memory beyond program end


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a RISC-V flat binary (.bin) to a $readmemh-compatible "
            ".mem file. Words beyond the binary are padded with NOP (0x00002013)."
        )
    )
    parser.add_argument(
        "bin_path",
        type=Path,
        help="Path to the input .bin file produced by objcopy -O binary.",
    )
    parser.add_argument(
        "depth",
        type=int,
        help="Memory depth in 32-bit words (IMEM_DEPTH or DMEM_DEPTH).",
    )
    parser.add_argument(
        "mem_path",
        type=Path,
        help="Path to the output .mem file.",
    )
    return parser.parse_args()


def validate_inputs(bin_path: Path, depth: int) -> None:
    if not bin_path.exists():
        raise FileNotFoundError(f"Binary file not found: {bin_path}")
    if not bin_path.is_file():
        raise ValueError(f"Expected a file, not a directory: {bin_path}")
    if depth <= 0:
        raise ValueError(f"Memory depth must be a positive integer, got: {depth}")

    file_size_bytes = bin_path.stat().st_size
    if file_size_bytes % WORD_SIZE_BYTES != 0:
        raise ValueError(
            f"Binary size ({file_size_bytes} bytes) is not a multiple of "
            f"{WORD_SIZE_BYTES}. The file may be corrupt or misaligned."
        )

    program_word_count = file_size_bytes // WORD_SIZE_BYTES
    if program_word_count > depth:
        raise ValueError(
            f"Program is {program_word_count} words but memory depth is only "
            f"{depth}. Increase DEPTH or reduce the program size."
        )


def read_words_from_binary(bin_path: Path) -> list[str]:
    raw_bytes = bin_path.read_bytes()
    word_count = len(raw_bytes) // WORD_SIZE_BYTES
    return [
        raw_bytes[i * WORD_SIZE_BYTES : (i + 1) * WORD_SIZE_BYTES]
        .hex()  # raw little-endian bytes → hex string, no byteswap needed
        # objcopy -O binary preserves the in-memory byte order of the ELF
        # sections. RV32I stores instructions little-endian, so the byte
        # sequence [b0 b1 b2 b3] in the .bin maps directly to the 32-bit
        # little-endian word that $readmemh expects.
        for i in range(word_count)
    ]


def pad_to_depth(words: list[str], depth: int) -> list[str]:
    padding_count = depth - len(words)
    return words + [NOP_WORD] * padding_count


def write_mem_file(mem_path: Path, words: list[str]) -> None:
    mem_path.parent.mkdir(parents=True, exist_ok=True)
    mem_path.write_text("\n".join(words) + "\n", encoding="ascii")


def convert_binary_to_mem(bin_path: Path, depth: int, mem_path: Path) -> None:
    validate_inputs(bin_path, depth)
    program_words = read_words_from_binary(bin_path)
    padded_words = pad_to_depth(program_words, depth)
    write_mem_file(mem_path, padded_words)

    program_word_count = len(program_words)
    padding_word_count = depth - program_word_count
    print(
        f"[elf_to_mem] {bin_path.name} → {mem_path} "
        f"({program_word_count} program words + {padding_word_count} NOP padding, "
        f"total {depth} words)"
    )


def main() -> None:
    args = parse_arguments()
    try:
        convert_binary_to_mem(args.bin_path, args.depth, args.mem_path)
    except (FileNotFoundError, ValueError) as error:
        print(f"[elf_to_mem] ERROR: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()