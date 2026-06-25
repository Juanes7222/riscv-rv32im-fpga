#!/usr/bin/env python3
"""Extract Fmax from a Quartus .sta.rpt file and print to stdout.

Usage:
    python3 scripts/extract_fmax.py path/to/timing.rpt

Outputs the Fmax value (MHz) at the Slow 1100mV 85C model, or 0.0 if not found.
A single float is printed so the Makefile can redirect to fmax.txt.
"""

import re
import sys
from pathlib import Path


def parse_fmax_from_sta(sta_path: Path) -> float:
    """Extract Fmax (MHz @85C) from a Quartus .sta.rpt file."""
    if not sta_path.exists():
        return 0.0

    text = sta_path.read_text()

    # Pattern matches the Fmax row, e.g.:
    #   ; 36.73 MHz ; 36.73 MHz       ; clk        ;      ;
    pattern = r';\s*([\d.]+)\s*MHz\s*;\s*[\d.]+\s*MHz\s*;\s*clk\s*;'

    sections = text.split("; Slow 1100mV 85C Model Fmax Summary")
    if len(sections) > 1:
        match = re.search(pattern, sections[1])
        if match:
            return float(match.group(1))

    sections = text.split("; Slow 1100mV 85C model Fmax Summary")
    if len(sections) > 1:
        match = re.search(pattern, sections[1])
        if match:
            return float(match.group(1))

    return 0.0


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_fmax.py <timing.rpt>")
        sys.exit(1)

    path = Path(sys.argv[1])
    fmax = parse_fmax_from_sta(path)
    print(f"{fmax:.2f}")


if __name__ == "__main__":
    main()
