# RV32IM FPGA - Results Report

*Generated: 2026-06-24 19:31*

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
| CPI=1 Invariant (45 tests) | ✅ 45/0/45 | ⬜ - |
| Pipeline Smoke Tests (4 tests) | ⬜ - | ✅ 4/0/4 |
| Pipeline Debug/Forwarding | ⬜ - | ✅ 1/0/1 |
| Pipeline RV32I ISA (37 tests) | ⬜ - | ✅ 37/0/37 |
| Pipeline RV32M (8 tests) | ⬜ - | ✅ 8/0/8 |
| Pipeline RV32MI (15 tests) | ⬜ - | ✅ 15/0/15 |
| Pipeline Hazard/Forwarding (7 tests) | ⬜ - | ✅ 7/0/7 |
| Pipeline Control Hazards (5 tests) | ⬜ - | ✅ 4/0/4 |
| Pipeline CPI Counters (4 tests) | ⬜ - | ✅ 4/0/4 |

---

## Synthesis Results

| Metric | Single-Cycle | Pipeline |
|---|---|---|
| Fmax @85°C | 36.79 MHz | 57.45 MHz |
| Fmax @0°C | 37.57 MHz | 57.81 MHz |
| ALMs | 12201 | 2177 |
| Registers | 18045 | 2173 |
| DSP Blocks | 9 | 9 |
| Memory Bits | 0 | 16384 |
| Pins | 54 | 54 |
| Setup Slack (85°C) | -17.182 ns | -7.407 ns |
| Hold Slack (85°C) | -17.182 ns | -7.407 ns |

---

## Replica Fmax Statistics

| Replica | Single-Cycle (MHz) | Pipeline (MHz) |
|---|---|---|
| Replica 1 | 36.73 | 56.60 |
| Replica 2 | 37.11 | 53.00 |
| Replica 3 | 37.26 | 57.96 |
| Replica 4 | 36.68 | 58.06 |
| Replica 5 | 36.79 | 57.45 |
| **Mean ± σ** | **36.91 ± 0.23** | **56.61 ± 1.88** |
| Min | 36.68 | 53.00 |
| Max | 37.26 | 58.06 |

---

## Pipeline Hazard/Forwarding Tests

| Test | Status | Time (s) |
|---|---|---|
| test_forward_ex_mem_to_ex | ✅ PASS | 0.0024 |
| test_forward_mem_wb_to_ex | ✅ PASS | 0.0023 |
| test_forward_wb_to_id | ✅ PASS | 0.0018 |
| test_load_use_then_forward_mem_wb | ✅ PASS | 0.0015 |
| test_chain_three_raw_dependencies | ✅ PASS | 0.0018 |
| test_no_false_forward_to_x0 | ✅ PASS | 0.0019 |
| test_mem_raw_stall_then_forward | ✅ PASS | 0.0019 |

## Pipeline Control Hazard Tests

| Test | Status | Time (s) |
|---|---|---|
| test_beq_taken_flushes_pipeline | ✅ PASS | 0.0018 |
| test_beq_not_taken_no_flush | ✅ PASS | 0.0017 |
| test_jal_flush | ✅ PASS | 0.0024 |
| test_jalr_flush | ✅ PASS | 0.0021 |

## Pipeline CPI/Performance Counter Tests

| Test | Status | Time (s) |
|---|---|---|
| test_counters_reset_to_zero | ✅ PASS | 0.0003 |
| test_load_use_increases_cycles | ✅ PASS | 0.0033 |
| test_div_increases_cycles | ✅ PASS | 0.0067 |
| test_counter_monotonicity | ✅ PASS | 0.0015 |
