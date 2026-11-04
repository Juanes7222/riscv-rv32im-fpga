# RV32IM FPGA - Results Report

*Generated: 2026-11-03 18:40*

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
| Pipeline Hazard/Forwarding (7 tests) | ⬜ - | ✅ 8/0/8 |
| Pipeline Control Hazards (5 tests) | ⬜ - | ✅ 4/0/4 |
| Pipeline CPI Counters (4 tests) | ⬜ - | ✅ 4/0/4 |

---

## Synthesis Results

| Metric | Single-Cycle | Pipeline |
|---|---|---|
| Fmax @85°C | 48.38 MHz | 59.50 MHz |
| Fmax @0°C | 48.12 MHz | 59.89 MHz |
| ALMs | 3816 | 5733 |
| Registers | 4109 | 5204 |
| DSP Blocks | 10 | 10 |
| Memory Bits | 475648 | 344576 |
| Pins | 85 | 85 |
| Setup Slack (85°C) | -6.790 ns | -6.808 ns |
| Hold Slack (85°C) | -6.790 ns | -6.808 ns |

---

## Replica Fmax Statistics

| Replica | Single-Cycle (MHz) | Pipeline (MHz) |
|---|---|---|
| Replica 1 | 48.79 | 57.13 |
| Replica 2 | 47.58 | 60.28 |
| Replica 3 | 48.59 | 58.49 |
| Replica 4 | 48.53 | 58.29 |
| Replica 5 | 48.38 | 59.50 |
| **Mean ± σ** | **48.37 ± 0.47** | **58.74 ± 1.20** |
| Min | 47.58 | 57.13 |
| Max | 48.79 | 60.28 |

---

## Pipeline Hazard/Forwarding Tests

| Test | Status | Time (s) |
|---|---|---|
| test_forward_ex_mem_to_ex | ✅ PASS | 0.0012 |
| test_forward_mem_wb_to_ex | ✅ PASS | 0.0011 |
| test_forward_wb_to_id | ✅ PASS | 0.0010 |
| test_load_use_then_forward_mem_wb | ✅ PASS | 0.0011 |
| test_load_use_on_branch_executes_branch_once | ✅ PASS | 0.0018 |
| test_chain_three_raw_dependencies | ✅ PASS | 0.0017 |
| test_no_false_forward_to_x0 | ✅ PASS | 0.0014 |
| test_mem_raw_stall_then_forward | ✅ PASS | 0.0015 |

## Pipeline Control Hazard Tests

| Test | Status | Time (s) |
|---|---|---|
| test_beq_taken_flushes_pipeline | ✅ PASS | 0.0013 |
| test_beq_not_taken_no_flush | ✅ PASS | 0.0015 |
| test_jal_flush | ✅ PASS | 0.0013 |
| test_jalr_flush | ✅ PASS | 0.0014 |

## Pipeline CPI/Performance Counter Tests

| Test | Status | Time (s) |
|---|---|---|
| test_counters_reset_to_zero | ✅ PASS | 0.0004 |
| test_load_use_increases_cycles | ✅ PASS | 0.0024 |
| test_div_increases_cycles | ✅ PASS | 0.0049 |
| test_counter_monotonicity | ✅ PASS | 0.0010 |
