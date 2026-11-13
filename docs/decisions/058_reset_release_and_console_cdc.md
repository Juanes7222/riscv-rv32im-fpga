# ADR 058 - Local reset release and coherent console transfers

Status: Accepted, verified in simulation and on fitted candidate netlists.
Date: 2026-11-13.
Supersedes the direct state sampling and global timing exclusions of ADR 055.

## Context

The physical-clock audit of the frozen replica-5 databases found a -2.122 ns
setup slack from the raw reset input to a single-cycle register-file bit
under the old input-delay model. Processor state and final counters also
reached pixel-clock snapshot registers directly, behind global clock-to-clock
false paths. Per-field formatting snapshots prevented mixed character
updates but did not establish a safe clock-domain crossing.

## Decision

- `reset_release_sync` asserts reset asynchronously and releases it after two
  rising edges of the receiving clock. Its initialized state also supplies
  power-up reset. CPU and pixel resets include their PLL lock where present.
- `debug_snapshot_cdc` captures the entire displayed processor bus in its
  source domain. A four-phase request/acknowledge handshake holds that bus
  until the destination has captured it and completed acknowledgement.
  Either endpoint reset resets the transfer, with local release in both domains.
- The generator produces the CDC instance and all rendering-group inputs.
  Table-follow addresses and access classification use the transferred bus.
  Memory-window reads continue to use the dual-clock shadows; simultaneous
  read/write collisions are debug-view limitations, not coherent memory snapshots.
- The loader detects button edges after two synchronizer stages and a separate
  history register. Its selector is synchronized and latched on the accepted
  request. The operator must hold the selector stable before pressing LOAD.
- Both SDC files describe the 50 MHz oscillator and derive PLL clocks and
  device-recommended uncertainty. False paths stop at asynchronous reset or
  first control-synchronizer boundaries. The held payload has a 10 ns maximum
  path delay; its handshake protects hold time. There are no global CPU/video cuts.
- LEDs and seven-segment displays have no clocked receiver. The 28 VGA output
  ports remain explicitly unconstrained pending an external interface budget.

## Consequences and validation

The console updates with handshake latency; rendering groups may show different
source snapshots, while each captured group and multi-bit field remains coherent.
Clocked processor execution, retirement and arithmetic are unchanged.

Reset fixtures wait for local release before setting architectural state. The
loader test uses a bounded wait for copy start and verifies all write addresses,
rather than depending on the previous button-pipeline latency.

Validation comprises 111 common, 51 single-cycle and 88 pipeline cocotb executions
without unexpected failures, retaining the documented machine-mode limitations.
Five standalone checks cover reset assertion/release, unrelated-clock transfer,
independent endpoint resets, frozen-result convergence, character snapshots,
decoding panels and memory windows. The layout constants of two existing VGA
tests were brought into agreement with the existing field maps.

Both candidate designs were fitted at seed 5 and checked at 1100 mV with slow/fast
models at 0 and 85 degrees Celsius. Setup, hold, pulse width and the bounded
payload paths have positive slack. Recovery/removal reports contain no active
paths under the reset-boundary exclusions; their zero path counts are not margins.

These are post-campaign corrections. They do not retroactively validate the old
bitstreams or update their measured frequency, resource or benchmark results.
A new physical validation and campaign are required before assigning the thesis
results to the corrected RTL.
