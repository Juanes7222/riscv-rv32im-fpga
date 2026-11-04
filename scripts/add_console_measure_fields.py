#!/usr/bin/env python3
"""Place the on-board measurement fields in the console templates.

The console shows the counters that the processor freezes when the program
writes to tohost (cycles_at_done / instr_at_done).  They are the on-board
counterpart of the values cocotb reports, so a photograph of the console is
comparable with the simulation numbers.

The fields are written into cells that are empty in the trimmed template, so
the layout of the rest of the screen does not move.  The script is idempotent:
it overwrites its own cells and nothing else.

Usage:  python3 scripts/add_console_measure_fields.py
"""

import openpyxl

XLSX = "scripts/RiscVScreenV3.xlsx"

# (sheet, row, first column, label, placeholder char, width) - 1-based.
# The 16 X characters are the placeholder of a 64-bit hexadecimal value; the
# single B is the one-bit halt flag, drawn like the single-cycle console.
FIELDS = [
    ("Single-cycle", 8, 2, "CyclesToPass", "X", 16),
    ("Single-cycle", 9, 2, "InstrToPass", "X", 16),
    ("Pipeline", 2, 45, "CyclesToPass", "X", 16),
    ("Pipeline", 3, 45, "InstrToPass", "X", 16),
    ("Pipeline", 4, 45, "HALTED", "B", 1),
]


def place(ws, row: int, col: int, label: str, marker: str, width: int) -> None:
    """Write "<label>: <marker run>" starting at (row, col)."""
    text = f"{label}: "
    for i, ch in enumerate(text):
        ws.cell(row=row, column=col + i).value = ch
    for i in range(width):
        ws.cell(row=row, column=col + len(text) + i).value = marker


def main() -> None:
    wb = openpyxl.load_workbook(XLSX)
    for sheet, row, col, label, marker, width in FIELDS:
        place(wb[sheet], row, col, label, marker, width)
    wb.save(XLSX)
    print(f"measurement fields placed in {XLSX}")


if __name__ == '__main__':
    main()
