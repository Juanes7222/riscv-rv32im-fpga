# RV32IM FPGA - Results Report

*Generated: 2026-11-07 21:36*

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
| Step Mode | ✅ 3/0/3 | ⬜ - |
| Pipeline Smoke Tests (4 tests) | ⬜ - | ✅ 4/0/4 |
| Pipeline Debug/Forwarding | ⬜ - | ✅ 1/0/1 |
| Pipeline RV32I ISA (37 tests) | ⬜ - | ✅ 37/0/37 |
| Pipeline RV32M (8 tests) | ⬜ - | ✅ 8/0/8 |
| Pipeline RV32MI (15 tests) | ⬜ - | ✅ 15/0/15 |
| Pipeline Hazard/Forwarding (8 tests) | ⬜ - | ✅ 8/0/8 |
| Pipeline Control Hazards (4 tests) | ⬜ - | ✅ 4/0/4 |
| Pipeline CPI Counters (4 tests) | ⬜ - | ✅ 4/0/4 |
| Pipeline Step Mode | ⬜ - | ✅ 2/0/2 |
| Program Loader | ✅ 3/0/3 | ✅ 3/0/3 |
| Loader Execution (1 test) | ⬜ - | ✅ 1/0/1 |

---

## Synthesis Results

| Metric | Single-Cycle | Pipeline |
|---|---|---|
| Fmax @85°C | 48.48 MHz | 60.60 MHz |
| Fmax @0°C | 48.72 MHz | 61.02 MHz |
| ALMs | 3789 | 4534 |
| Registers | 4140 | 5143 |
| DSP Blocks | 10 | 10 |
| Memory Bits | 475648 | 475648 |
| Pins | 90 | 90 |
| Setup Slack (85°C) | -7.939 ns | -6.502 ns |
| Hold Slack (85°C) | 0.234 ns | 0.245 ns |

---

## Replica Fmax Statistics

| Replica | Single-Cycle (MHz) | Pipeline (MHz) |
|---|---|---|
| Replica 1 | 49.55 | 63.34 |
| Replica 2 | 49.45 | 62.55 |
| Replica 3 | 49.86 | 61.18 |
| Replica 4 | 46.72 | 62.72 |
| Replica 5 | 49.92 | 60.96 |
| **Mean ± σ** | **49.10 ± 1.35** | **62.15 ± 1.03** |
| Min | 46.72 | 60.96 |
| Max | 49.92 | 63.34 |

---

## Notes on Interpretation

- **The negative setup slack is expected.** The SDC declares a 10 ns target (`synthesis/*/constraints.sdc`), twice as aggressive as the board clock on purpose, so that Quartus reports the true achievable Fmax after place-and-route instead of stopping at an artificially relaxed target (ADR 049). At the operating periods (25 ns for the single-cycle at 40 MHz and 20 ns for the pipeline at 50 MHz) both designs meet timing with positive margin: the measured mean Fmax is higher than the operating frequency in both cases.
- **The two architectures run at different clock frequencies** (40 MHz single-cycle, 50 MHz pipeline), by design (ADR 049: the single-cycle critical path does not reach 50 MHz). Absolute throughput is therefore computed with the Fmax of each architecture, while architectural efficiency is compared with CPI and CoreMark/MHz, which are independent of the clock.
- **CPI = 1 holds only for the non-DIV subset of the single-cycle design.** DIV/DIVU/REM/REMU run a 32-cycle radix-2 FSM (ADR 008, ADR 031), so their CPI is greater than 1 in both architectures; the comparison remains fair because the penalty applies to both.
- **Benchmarks are measured once per (architecture, program).** The CPI is deterministic in simulation, so the statistical variability reported here is the one of the five synthesis replicas, propagated to throughput through their Fmax (anteproyecto §7.1.3).

---

## Pipeline Hazard/Forwarding Tests

| Test | Status | Time (s) |
|---|---|---|
| test_forward_ex_mem_to_ex | ✅ PASS | 0.0023 |
| test_forward_mem_wb_to_ex | ✅ PASS | 0.0023 |
| test_forward_wb_to_id | ✅ PASS | 0.0020 |
| test_load_use_then_forward_mem_wb | ✅ PASS | 0.0016 |
| test_load_use_on_branch_executes_branch_once | ✅ PASS | 0.0032 |
| test_chain_three_raw_dependencies | ✅ PASS | 0.0015 |
| test_no_false_forward_to_x0 | ✅ PASS | 0.0013 |
| test_mem_raw_stall_then_forward | ✅ PASS | 0.0025 |

## Pipeline Control Hazard Tests

| Test | Status | Time (s) |
|---|---|---|
| test_beq_taken_flushes_pipeline | ✅ PASS | 0.0022 |
| test_beq_not_taken_no_flush | ✅ PASS | 0.0026 |
| test_jal_flush | ✅ PASS | 0.0028 |
| test_jalr_flush | ✅ PASS | 0.0018 |

## Pipeline CPI/Performance Counter Tests

| Test | Status | Time (s) |
|---|---|---|
| test_counters_reset_to_zero | ✅ PASS | 0.0010 |
| test_load_use_increases_cycles | ✅ PASS | 0.0047 |
| test_div_increases_cycles | ✅ PASS | 0.0086 |
| test_counter_monotonicity | ✅ PASS | 0.0015 |
