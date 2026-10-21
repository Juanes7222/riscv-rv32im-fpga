# RV32IM FPGA - Results Report

*Generated: 2026-10-21 16:16*

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
| Fmax @85°C | 53.02 MHz | 53.41 MHz |
| Fmax @0°C | 54.17 MHz | 53.59 MHz |
| ALMs | 11438 | 3632 |
| Registers | 18908 | 3913 |
| DSP Blocks | 7 | 10 |
| Memory Bits | 229888 | 246272 |
| Pins | 85 | 85 |
| Setup Slack (85°C) | -8.861 ns | -8.724 ns |
| Hold Slack (85°C) | -8.861 ns | -8.724 ns |

---

## Replica Fmax Statistics

| Replica | Single-Cycle (MHz) | Pipeline (MHz) |
|---|---|---|
| Replica 1 | 53.75 | 54.59 |
| Replica 2 | 52.89 | 54.19 |
| Replica 3 | 51.75 | 54.51 |
| Replica 4 | 53.19 | 55.57 |
| Replica 5 | 53.02 | 53.41 |
| **Mean ± σ** | **52.92 ± 0.73** | **54.45 ± 0.78** |
| Min | 51.75 | 53.41 |
| Max | 53.75 | 55.57 |

---
