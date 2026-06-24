# RV32IM FPGA — Results Report

*Generated: 2026-06-24 09:23*

---

## Verification Results

| Test Suite | Single-Cycle (P/F/T) | Pipeline (P/F/T) |
|---|---|---|
| RV32I ISA (37 tests) | ✅ 37/0/37 | ⬜ — |
| RV32M M-Extension (8 tests) | ✅ 8/0/8 | ⬜ — |
| RV32MI Machine-Mode (15 tests) | ✅ 15/0/15 | ⬜ — |
| ALU Unit Tests | ✅ 27/0/27 | ⬜ — |
| Branch Unit Tests | ✅ 20/0/20 | ⬜ — |
| Model vs DUT Comparison | ✅ 4/0/4 | ⬜ — |
| CPI=1 Invariant (45 tests) | ✅ 45/0/45 | ⬜ — |
| Pipeline Smoke Tests (4 tests) | ⬜ — | ✅ 4/0/4 |
| Pipeline Debug/Forwarding | ⬜ — | ✅ 1/0/1 |
| Pipeline RV32I ISA (37 tests) | ⬜ — | ✅ 37/0/37 |
| Pipeline RV32M (8 tests) | ⬜ — | ✅ 8/0/8 |
| Pipeline RV32MI (15 tests) | ⬜ — | ✅ 15/0/15 |
| Pipeline Hazard/Forwarding (7 tests) | ⬜ — | ✅ 7/0/7 |
| Pipeline Control Hazards (5 tests) | ⬜ — | ✅ 4/0/4 |
| Pipeline CPI Counters (4 tests) | ⬜ — | ✅ 4/0/4 |

---

## Synthesis Results

| Metric | Single-Cycle | Pipeline |
|---|---|---|
| Fmax @85°C | 37.54 MHz | 57.59 MHz |
| Fmax @0°C | 38.30 MHz | 58.57 MHz |
| ALMs | 11534 | 2145 |
| Registers | 17808 | 2093 |
| DSP Blocks | 9 | 9 |
| Memory Bits | 0 | 786432 |
| Pins | 54 | 54 |
| Setup Slack (85°C) | -16.636 ns | -7.365 ns |
| Hold Slack (85°C) | -16.636 ns | -7.365 ns |

---

## Pipeline Hazard/Forwarding Tests

| Test | Status | Time (s) |
|---|---|---|
| test_forward_ex_mem_to_ex | ✅ PASS | 0.0018 |
| test_forward_mem_wb_to_ex | ✅ PASS | 0.0021 |
| test_forward_wb_to_id | ✅ PASS | 0.0019 |
| test_load_use_then_forward_mem_wb | ✅ PASS | 0.0016 |
| test_chain_three_raw_dependencies | ✅ PASS | 0.0017 |
| test_no_false_forward_to_x0 | ✅ PASS | 0.0015 |
| test_mem_raw_stall_then_forward | ✅ PASS | 0.0018 |

## Pipeline Control Hazard Tests

| Test | Status | Time (s) |
|---|---|---|
| test_beq_taken_flushes_pipeline | ✅ PASS | 0.0020 |
| test_beq_not_taken_no_flush | ✅ PASS | 0.0018 |
| test_jal_flush | ✅ PASS | 0.0022 |
| test_jalr_flush | ✅ PASS | 0.0022 |

## Pipeline CPI/Performance Counter Tests

| Test | Status | Time (s) |
|---|---|---|
| test_counters_reset_to_zero | ✅ PASS | 0.0004 |
| test_load_use_increases_cycles | ✅ PASS | 0.0034 |
| test_div_increases_cycles | ✅ PASS | 0.0061 |
| test_counter_monotonicity | ✅ PASS | 0.0016 |
