#!/usr/bin/env python3
"""Parses a SignalTap II CSV export and compares against cocotb results.

Usage:
    python scripts/parse_stp_csv.py results/raw/capture_pipeline.csv [--cocotb-csv results/cocotb_pipeline.csv]

The CSV from SignalTap II contains one row per sample.  With sample_depth=1
and trigger_position=1, we expect exactly one data row containing the final
values of cycle_count, instr_retired, and program_done_synced after the
benchmark completes.

Outputs:
    - Prints cycle_count, instr_retired, CPI, and program_done_synced.
    - If --cocotb-csv is provided, compares FPGA values against cocotb.
    - Writes comparison to results/cross_validation_<arch>.csv.
"""

import argparse
import csv
import os
import re
import sys


def parse_stp_csv(filepath: str) -> dict:
    """Extract signal values from a SignalTap II CSV.

    The CSV format from quartus_stp export has column headers with signal
    names (including hierarchy) and data rows.  We search for the row
    where program_done_synced == 1 and extract the counter values.

    Returns:
        dict with keys: cycle_count, instr_retired, program_done_synced (all ints)
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"STP CSV not found: {filepath}")

    with open(filepath, "r") as f:
        reader = csv.reader(f)

        # Read header row to find column indices
        headers = next(reader)
        headers_lower = [h.strip().lower() for h in headers]

        # Find columns by signal name suffix (ignore hierarchy prefix)
        col_cycle = None
        col_instr = None
        col_done = None

        for i, h in enumerate(headers_lower):
            if "cycle_count" in h:
                col_cycle = i
            elif "instr_retired" in h:
                col_instr = i
            elif "program_done_synced" in h:
                col_done = i

        if col_cycle is None:
            raise ValueError(
                f"Column 'cycle_count' not found in CSV headers: {headers}"
            )
        if col_instr is None:
            raise ValueError(
                f"Column 'instr_retired' not found in CSV headers: {headers}"
            )
        if col_done is None:
            raise ValueError(
                f"Column 'program_done_synced' not found in CSV headers: {headers}"
            )

        # Search data rows for the triggered row
        result = None
        for row in reader:
            if len(row) <= max(col_cycle, col_instr, col_done):
                continue  # skip malformed rows

            done_val = _parse_signal_value(row[col_done])
            cycle_val = _parse_signal_value(row[col_cycle])
            instr_val = _parse_signal_value(row[col_instr])

            # Prefer the row where program_done_synced == 1
            if done_val == 1:
                result = {
                    "cycle_count": cycle_val,
                    "instr_retired": instr_val,
                    "program_done_synced": done_val,
                }
                break

            # Fallback: capture first valid data row
            if result is None and cycle_val is not None:
                result = {
                    "cycle_count": cycle_val,
                    "instr_retired": instr_val,
                    "program_done_synced": done_val,
                }

    if result is None:
        raise ValueError("No data rows found in STP CSV")

    return result


def _parse_signal_value(val_str: str):
    """Parse a SignalTap signal value (may be hex or binary or decimal)."""
    if val_str is None:
        return None
    val_str = val_str.strip()

    # Remove hierarchy prefix if present (e.g., "~top_pipeline|u_perf|cycle_count[63..0]")
    val_str = val_str.split("|")[-1]

    # Remove bus width suffix if present
    val_str = re.sub(r"\[\d+\.\.\d+\]", "", val_str)

    # Try hex (STP typically exports hex with 'h suffix)
    if val_str.lower().startswith("h") or val_str.lower().startswith("0x"):
        try:
            return int(val_str, 16)
        except ValueError:
            pass

    # Try binary (b prefix)
    if val_str.lower().startswith("b"):
        try:
            return int(val_str[1:], 2)
        except ValueError:
            pass

    # Try decimal
    try:
        return int(val_str)
    except ValueError:
        pass

    # Try hex without prefix
    try:
        return int(val_str, 16)
    except ValueError:
        pass

    return None


def parse_cocotb_csv(filepath: str) -> dict:
    """Extract cycle_count and instr_retired from a cocotb results CSV.

    Expected format (from cocotb test logging):
        time, test_name, cycle_count, instr_retired, cpi, ...
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"cocotb CSV not found: {filepath}")

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Take the first row (or the one matching our program)
            return {
                "cycle_count": int(row.get("cycle_count", 0)),
                "instr_retired": int(row.get("instr_retired", 0)),
            }

    raise ValueError(f"No data found in cocotb CSV: {filepath}")


def compute_cpi(cycle_count: int, instr_retired: int) -> float:
    """Compute Cycles Per Instruction.

    Returns:
        CPI as a float, or float('inf') if instr_retired == 0.
    """
    if instr_retired == 0:
        return float("inf")
    return cycle_count / instr_retired


def main():
    parser = argparse.ArgumentParser(
        description="Parse SignalTap II CSV and compare against cocotb"
    )
    parser.add_argument(
        "stp_csv",
        help="Path to SignalTap II CSV export",
    )
    parser.add_argument(
        "--cocotb-csv",
        help="Path to cocotb results CSV for comparison (optional)",
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for comparison results",
        default="results",
    )
    args = parser.parse_args()

    # Parse STP CSV
    print(f"Parsing STP CSV: {args.stp_csv}")
    fpga_data = parse_stp_csv(args.stp_csv)
    fpga_cpi = compute_cpi(fpga_data["cycle_count"], fpga_data["instr_retired"])

    print()
    print("=== FPGA (SignalTap) Results ===")
    print(f"  cycle_count:        {fpga_data['cycle_count']}")
    print(f"  instr_retired:      {fpga_data['instr_retired']}")
    print(f"  CPI:                {fpga_cpi:.4f}")
    print(f"  program_done_synced: {fpga_data['program_done_synced']}")

    # Extract architecture from filename for output paths
    arch_match = re.search(r"capture_(pipeline|single_cycle)", args.stp_csv)
    arch = arch_match.group(1) if arch_match else "unknown"

    # Compare with cocotb if available
    if args.cocotb_csv:
        print()
        print(f"Parsing cocotb CSV: {args.cocotb_csv}")
        cocotb_data = parse_cocotb_csv(args.cocotb_csv)
        cocotb_cpi = compute_cpi(cocotb_data["cycle_count"], cocotb_data["instr_retired"])

        print()
        print("=== Cocotb Results ===")
        print(f"  cycle_count:   {cocotb_data['cycle_count']}")
        print(f"  instr_retired: {cocotb_data['instr_retired']}")
        print(f"  CPI:           {cocotb_cpi:.4f}")

        # Compare
        print()
        print("=== Cross-Validation (FPGA vs Cocotb) ===")
        cycle_match = fpga_data["cycle_count"] == cocotb_data["cycle_count"]
        instr_match = fpga_data["instr_retired"] == cocotb_data["instr_retired"]

        if cycle_match and instr_match:
            print("  ✅ PASS: All counters match!")
        else:
            print("  ❌ FAIL: Counter mismatch detected!")
            if cycle_match:
                print(f"     cycle_count:      ✅ Match ({fpga_data['cycle_count']})")
            else:
                print(
                    f"     cycle_count:      ❌ FPGA={fpga_data['cycle_count']} "
                    f"cocotb={cocotb_data['cycle_count']} "
                    f"diff={fpga_data['cycle_count'] - cocotb_data['cycle_count']}"
                )
            if instr_match:
                print(f"     instr_retired:    ✅ Match ({fpga_data['instr_retired']})")
            else:
                print(
                    f"     instr_retired:    ❌ FPGA={fpga_data['instr_retired']} "
                    f"cocotb={cocotb_data['instr_retired']} "
                    f"diff={fpga_data['instr_retired'] - cocotb_data['instr_retired']}"
                )

        # Write cross-validation result to CSV
        os.makedirs(args.output_dir, exist_ok=True)
        cross_csv = os.path.join(args.output_dir, f"cross_validation_{arch}.csv")
        with open(cross_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "architecture",
                "source",
                "cycle_count",
                "instr_retired",
                "cpi",
                "match",
            ])
            writer.writerow([arch, "fpga", fpga_data["cycle_count"],
                             fpga_data["instr_retired"], f"{fpga_cpi:.4f}",
                             "n/a"])
            writer.writerow([arch, "cocotb", cocotb_data["cycle_count"],
                             cocotb_data["instr_retired"], f"{cocotb_cpi:.4f}",
                             "n/a"])
            writer.writerow([arch, "validation",
                             "match" if cycle_match else "mismatch",
                             "match" if instr_match else "mismatch",
                             "match" if (cycle_match and instr_match) else "mismatch",
                             "PASS" if (cycle_match and instr_match) else "FAIL"])

        print(f"\nCross-validation written to: {cross_csv}")
    else:
        print()
        print("(No cocotb CSV provided for comparison)")
        print("Pass --cocotb-csv to enable cross-validation.")

    # Write FPGA-only results to CSV
    os.makedirs(args.output_dir, exist_ok=True)
    fpga_csv = os.path.join(args.output_dir, f"fpga_results_{arch}.csv")
    with open(fpga_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "architecture",
            "cycle_count",
            "instr_retired",
            "cpi",
            "program_done_synced",
        ])
        writer.writerow([
            arch,
            fpga_data["cycle_count"],
            fpga_data["instr_retired"],
            f"{fpga_cpi:.4f}",
            fpga_data["program_done_synced"],
        ])

    print(f"FPGA results written to: {fpga_csv}")
    print()

    # Return exit code: 0 if validation passes (or no cocotb comparison), 1 if mismatch
    if args.cocotb_csv:
        if cycle_match and instr_match:
            return 0
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
