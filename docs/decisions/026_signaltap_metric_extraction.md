# ADR 026 — Metric Extraction: SignalTap II via JTAG as Definitive Mechanism

**Status:** Accepted  
**Date:** 2026-05-04

## Context

The experimental protocol requires automated extraction of
`cycle_count` and `instr_retired` from hardware after each benchmark execution on the
DE1-SoC FPGA. Five independent synthesis replicas per treatment/benchmark combination
must be executed and the results recorded.

## Decision

**SignalTap II** is adopted as the definitive mechanism for metric extraction.
The USB-Blaster integrated in the DE1-SoC connects directly to the FPGA fabric via JTAG
and is fully accessible from the host PC without any additional hardware.

Automation is achieved through the `quartus_stp` executable, which exposes a complete
TCL API for programmatic capture, trigger control, and data export, all without
launching the Quartus GUI. Intel officially documents and supports this interface.

## Normative Specification

### Signals Captured

The following signals from `perf_counters.sv` (ADR 024) are tapped by SignalTap II:

| Signal | Width | Type | Description |
|--------|-------|------|-------------|
| `cycle_count` | 64 bits | Register (FF) | Total clock cycles elapsed |
| `instr_retired` | 64 bits | Register (FF) | Instructions committed |
| `program_done` | 1 bit | Register (FF) | Benchmark termination flag |

No combinational signals are tapped. All tapped signals are registers, which
guarantees stable capture and eliminates the need for `keep` or `preserve` pragmas
in the RTL (which would affect synthesis results).

**Buffer depth: 1 sample, post-trigger.**  
Only the final state is needed. A depth of 1 minimizes M10K usage.

### SignalTap II File: `stp/perf_capture.stp`

One `.stp` file is committed to the repository. It is identical for both
microarchitectures (single-cycle and pipeline). The `.stp` is configured with:

- Clock: `clk` (the processor master clock)
- Trigger condition: `program_done == 1`, rising edge
- Trigger position: pre-trigger 0 / post-trigger 1 (capture 1 sample after trigger)
- Sample depth: 1
- Signal set: `{cycle_count[63:0], instr_retired[63:0], program_done}`

The `.stp` file is added to both Quartus projects via `.qsf`:

```tcl
set_global_assignment -name SIGNALTAP_FILE stp/perf_capture.stp
set_global_assignment -name ENABLE_SIGNALTAP ON
set_global_assignment -name USE_SIGNALTAP_FILE stp/perf_capture.stp
```

### Automation Script: `scripts/run_capture.tcl`

```tcl
# run_capture.tcl — invoked as: quartus_stp -t scripts/run_capture.tcl
# Captures one sample after program_done trigger and exports to CSV.

package require ::quartus::stp

set instance   "auto_signaltap_0"
set signal_set "signal_set_0"
set trigger    "trigger_0"
set log_name   "log_[clock seconds]"
set out_file   [lindex $argv 0]  ;# first argument: output CSV path

open_session -name stp/perf_capture.stp

run -instance $instance \
    -signal_set $signal_set \
    -trigger    $trigger \
    -data_log   $log_name \
    -timeout    60

# Export captured data to CSV
export_to_csv -instance $instance \
              -data_log $log_name \
              -filename $out_file

close_session
```

Usage:

```bash
quartus_stp -t scripts/run_capture.tcl results/sc_coremark_rep1.csv
```

### Python Orchestration: `scripts/run_replica.py`

```python
#!/usr/bin/env python3
"""
Run one full synthesis + capture replica for a given treatment and benchmark.
Usage:
    python scripts/run_replica.py \
        --project projects/single_cycle/rv32im_sc.qpf \
        --imem    benchmarks/coremark/coremark.mem \
        --out     results/sc_coremark_rep1.csv \
        --replica 1
"""
import argparse, subprocess, pathlib, sys

parser = argparse.ArgumentParser()
parser.add_argument("--project", required=True)
parser.add_argument("--imem",    required=True)
parser.add_argument("--out",     required=True)
parser.add_argument("--replica", type=int, default=1)
args = parser.parse_args()

# 1. Generate memory config header
subprocess.run(
    ["python", "scripts/gen_mem_config.py", "--imem", args.imem],
    check=True
)

# 2. Full synthesis (new seed per replica via environment or QSF override)
subprocess.run(
    ["quartus_sh", "--flow", "compile", args.project],
    check=True
)

# 3. Program the FPGA
sof = str(pathlib.Path(args.project).parent / "output_files" / "*.sof")
subprocess.run(
    ["quartus_pgm", "-c", "USB-Blaster", "--mode", "JTAG",
     "--operation", f"p;{sof}"],
    check=True
)

# 4. Capture metrics via SignalTap
subprocess.run(
    ["quartus_stp", "-t", "scripts/run_capture.tcl", args.out],
    check=True
)

print(f"Replica {args.replica} complete → {args.out}")
```

### Python Parser: `scripts/parse_stp_csv.py`

```python
#!/usr/bin/env python3
"""
Parse SignalTap CSV export into structured metrics.
The CSV exported by quartus_stp has a fixed header row followed by sample rows.
Column names match the signal names configured in the .stp file.
"""
import csv, sys, json

def parse_stp_export(csv_path: str) -> dict:
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError(f"Empty capture in {csv_path}")

    last = rows[-1]  # only 1 sample, but take last for safety
    return {
        "cycle_count":    int(last["cycle_count"], 0),
        "instr_retired":  int(last["instr_retired"], 0),
        "cpi":            int(last["cycle_count"], 0) /
                          max(1, int(last["instr_retired"], 0)),
    }

if __name__ == "__main__":
    result = parse_stp_export(sys.argv[1])
    print(json.dumps(result, indent=2))
```

## Resource Budget

A SignalTap II instance with 1-sample depth and 129 tapped bits (64 + 64 + 1)
uses approximately:

| Resource | Estimated consumption |
|----------|-----------------------|
| M10K blocks | 1 (minimum, 128 bits × 1 sample fits in one M10K) |
| Logic Elements (LEs) | ~150-250 (trigger logic + JTAG interface) |
| Fmax impact | None, SignalTap reads via JTAG, off the critical path |

The Cyclone V 5CSEMA5F31C6 has 397 M10K blocks and ~85K LEs. The SignalTap overhead
is < 0.3 % of LEs and < 0.3 % of M10K, negligible relative to the processor itself.

## Methodological Requirements

These requirements are normative for the experimental protocol:

1. **Identical `.stp` configuration** for both microarchitectures and all benchmarks.
   The `.stp` file is not modified between treatments — only the loaded program changes.

2. **SignalTap overhead is reported separately** in the resource utilization tables.
   Each table must include two rows:
   - "Processor + memories (excluding SignalTap)"
   - "SignalTap II instrumentation overhead"

   The comparison between monociclo and pipeline uses the processor-only row.

3. **Fmax is extracted from the Timing Analyzer report, not from SignalTap.**
   SignalTap does not affect the critical path. The `quartus_sta` report is the
   authoritative source for Fmax in all five replicas.

4. **Timeout of 60 seconds per capture.** If `program_done` does not trigger within
   60 s, the replica is flagged as failed and must be re-run. This maps to the
   "inestabilidad en las métricas" suspension criterion (Anteproyecto §7.1.7).

5. **Signal preservation:** Since all tapped signals (`cycle_count`, `instr_retired`,
   `program_done`) are registers in `perf_counters.sv`, no `keep` or `preserve`
   pragmas are needed. The Fitter will not remove registered outputs that feed
   SignalTap.


## Files Created/Modified by This ADR

| File | Action |
|------|--------|
| `stp/perf_capture.stp` | New — SignalTap II configuration file |
| `scripts/run_capture.tcl` | New — TCL automation script |
| `scripts/run_replica.py` | New — end-to-end replica orchestration |
| `scripts/parse_stp_csv.py` | New — CSV parser for SignalTap export |
| `projects/single_cycle/rv32im_sc.qsf` | Modified — add STP assignments |
| `projects/pipeline/rv32im_pl.qsf` | Modified — add STP assignments |
