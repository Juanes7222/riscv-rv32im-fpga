# RV32IM FPGA - Results Report

*Generated: 2026-10-21 10:50*

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
| Fmax @85°C | 36.79 MHz | 52.53 MHz |
| Fmax @0°C | 37.70 MHz | 52.78 MHz |
| ALMs | 14487 | 4599 |
| Registers | 20637 | 5155 |
| DSP Blocks | 10 | 10 |
| Memory Bits | 229888 | 246272 |
| Pins | 85 | 85 |
| Setup Slack (85°C) | -17.184 ns | -9.036 ns |
| Hold Slack (85°C) | -17.184 ns | -9.036 ns |

---

## Replica Fmax Statistics

| Replica | Single-Cycle (MHz) | Pipeline (MHz) |
|---|---|---|
| Replica 1 | 36.73 | 56.60 |
| Replica 2 | 37.11 | 53.00 |
| Replica 3 | 37.26 | 57.96 |
| Replica 4 | 36.68 | 58.06 |
| Replica 5 | 36.79 | 57.45 |
| **Mean ± σ** | **36.91 ± 0.26** | **56.61 ± 2.10** |
| Min | 36.68 | 53.00 |
| Max | 37.26 | 58.06 |

---
