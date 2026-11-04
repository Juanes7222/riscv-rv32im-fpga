# RV32IM FPGA - Results Report

*Generated: 2026-11-03 21:05*

---

## Verification Results

| Test Suite | Single-Cycle (P/F/T) | Pipeline (P/F/T) |
|---|---|---|
| RV32I ISA (37 tests) | ✅ 37/0/37 | ⬜ - |
| RV32M M-Extension (8 tests) | ✅ 8/0/8 | ⬜ - |
| RV32MI Machine-Mode (15 tests) | ✅ 15/0/15 | ⬜ - |
| ALU Unit Tests | ✅ 27/0/27 | ⬜ - |
| Branch Unit Tests | ✅ 20/0/20 | ⬜ - |
| Model vs DUT Comparison | ✅ 4/0/4 | ⬜ - |

---

## Synthesis Results

| Metric | Single-Cycle | Pipeline |
|---|---|---|
| Fmax @85°C | 47.01 MHz | 58.46 MHz |
| Fmax @0°C | 47.30 MHz | 58.63 MHz |
| ALMs | 3828 | 5737 |
| Registers | 4157 | 5079 |
| DSP Blocks | 10 | 10 |
| Memory Bits | 475648 | 344576 |
| Pins | 85 | 85 |
| Setup Slack (85°C) | -7.949 ns | -7.106 ns |
| Hold Slack (85°C) | -7.949 ns | -7.106 ns |

---

## Replica Fmax Statistics

| Replica | Single-Cycle (MHz) | Pipeline (MHz) |
|---|---|---|
| Replica 1 | 48.84 | 61.27 |
| Replica 2 | 48.02 | 58.48 |
| Replica 3 | 47.92 | 60.83 |
| Replica 4 | 47.00 | 58.46 |
| Replica 5 | 47.01 | 58.46 |
| **Mean ± σ** | **47.76 ± 0.77** | **59.50 ± 1.42** |
| Min | 47.00 | 58.46 |
| Max | 48.84 | 61.27 |

---
