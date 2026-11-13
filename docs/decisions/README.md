# Architecture Decision Records

This index lists every design decision recorded for the `rv32im-pipeline-de1soc`
project. Each entry links to an individual ADR file. Records are numbered
sequentially in the order the decision was made. Once recorded, a decision is
never deleted - if a decision is reversed, a new ADR is added that supersedes
the original, and both remain in the index.

The whole set was audited on 2026-11-12 against the RTL: see
[`docs/auditoria_adrs_2026-11-12.md`](../auditoria_adrs_2026-11-12.md). The
status column below reflects the result of that audit.

| # | Title | Status | Supersedes / notes |
|---|-------|--------|--------------------|
| [001](001_harvard_memory_architecture.md) | Harvard memory architecture | Accepted | - |
| [002](002_implementation_order.md) | Single-cycle before pipeline | Accepted | the shared-module freezing it announced is qualified by [004](004_shared_modules_boundary.md) |
| [003](003_rv32i_before_extension_m.md) | RV32I first, extension M as second iteration | Accepted | - |
| [004](004_shared_modules_boundary.md) | Boundary between shared and microarchitecture-specific modules | Accepted (rewritten 2026-11-12) | rewritten after the memory split and the loader/console interfaces ([054](054_runtime_program_loader.md), [055](055_vga_console_architecture.md)) |
| [005](005_alua_src_2bit.md) | ALU operand-A source extended to 2 bits | Accepted | - |
| [006](006_jalr_pc_masking.md) | JALR LSB masking responsibility assigned to branch_unit | Accepted | - |
| [007](007_branch_unit_inputs.md) | Branch unit receives rs1/rs2 directly from the register file | Accepted | - |
| [008](008_m_extension_implementation.md) | Combinational multiplier, multi-cycle divisor for extension M | Accepted | division FSM tables superseded by [031](031_m_extension_test_failures_and_fsm_correction.md) |
| [009](009_mulhsu_33bit_extension.md) | MULHSU implemented via 33-bit sign/zero extension | Accepted | - |
| [010](010_systemverilog_style.md) | Unified SystemVerilog style: logic + always_comb | Accepted | the generated `screen_writer_*` and `seven_segment` are known exceptions |
| [011](011_instruction_memory_async_read.md) | Instruction memory asynchronous read | Superseded in part by [046](046_single_cycle_imem_next_pc.md) | §1 and §4 no longer apply; §2 and the M10K physics still do |
| [012](012_reset_vector.md) | Reset vector `0x00000000` | Accepted | - |
| [013](013_memory_sizes.md) | Instruction and data memory sizes | Accepted | the flow uses 4096/1024; simulation uses 16384/8192 |
| [014](014_memory_initialize_format.md) | Memory initialization format | Accepted | the `.mem` padding is `00000013` |
| [015](015_register_file_ff_array.md) | Register file: FF array implementation | Accepted | gained `dbg_regs` ([055](055_vga_console_architecture.md)) |
| [016](016_register_file_reset_zero.md) | Register file: x1-x31 reset to zero, x0 without storage | Accepted (rewritten 2026-11-12) | documents the implemented behaviour; the earlier "all registers" claim was wrong |
| [017](017_imm_gen_interface.md) | Immediate generator: interface and implementation | Accepted | field extraction moved out of `always_comb` for Icarus |
| [018](018_branch_unit.md) | Branch unit: interface and implementation | Accepted | - |
| [019](019_alu_rv32im.md) | ALU RV32IM: interface, MULHSU and division strategy | Accepted | CPI and `div_busy` tables superseded by [031](031_m_extension_test_failures_and_fsm_correction.md) |
| [020](020_data_memory_async_read.md) | Data memory: read behaviour | Superseded in part by [048](048_single_cycle_half_cycle_data_memory.md) | the single-cycle reads on the falling edge; read-during-write differs per design |
| [021](021_data_memory_organization.md) | Data memory: byte enables and read extension | Superseded in part by [048](048_single_cycle_half_cycle_data_memory.md) | four byte-lane arrays, not one word array |
| [022](022_control_unit.md) | Control unit: interface and implementation | Accepted | - |
| [023](023_wr_en_gated.md) | Register file write inhibit during division | Accepted | cycle tables superseded by [031](031_m_extension_test_failures_and_fsm_correction.md) |
| [024](024_perf_counters.md) | Performance counters and measurement infrastructure | Accepted (rewritten 2026-11-12) | rewritten against `perf_counter.sv`; readout is [042](042_hardware_measurement_without_signaltap.md) |
| [025](025_mem_init_define.md) | Memory initialization via `` `define `` macros | Accepted (updated 2026-11-12) | the header is committed and guarded by `` `ifndef ``, no template |
| [026](026_signaltap_metric_extraction.md) | SignalTap metric extraction | Superseded by [042](042_hardware_measurement_without_signaltap.md) | historical record |
| [027](027_riscv-tests_compilation.md) | riscv-tests compilation for reset vector `0x00000000` | Accepted (rewritten 2026-11-12) | build harness in `verification/riscv-tests-build/` |
| [028](028_pass-fail_onvention.md) | Pass/fail convention: `tohost` monitoring in cocotb | Accepted (updated 2026-11-12) | superseded in part by [032](032_single_cycle_cpi_one_test_layer.md) (hierarchy read, no top ports) |
| [029](029_cocotb_directory_structure.md) | cocotb directory structure and Makefile convention | Accepted (updated 2026-11-12) | flat layout plus `common.mk` |
| [030](030_csr_and_trap_handling.md) | CSR file and minimal trap handling (ECALL / MRET) | Accepted | - |
| [031](031_m_extension_test_failures_and_fsm_correction.md) | M-extension test failures and division FSM correction | Accepted | supersedes the division timing tables of [008](008_m_extension_implementation.md), [019](019_alu_rv32im.md) and [023](023_wr_en_gated.md) |
| [032](032_single_cycle_cpi_one_test_layer.md) | Single-cycle CPI=1 test layer (`test_cpi_one`) | Accepted | implements the layer announced in [029](029_cocotb_directory_structure.md) |
| [033](033_rv32mi_test_layer_and_csr_extension.md) | RV32MI test layer and CSR register extension | Accepted | extends the CSR file of [030](030_csr_and_trap_handling.md); adds the rv32mi layer |
| [034](034_instruction_level_cocotb_test_layer.md) | Instruction-level cocotb layer (`test_alu_rv32i`) | Accepted | implements the layer announced in [029](029_cocotb_directory_structure.md) |
| [035](035_branch_instruction_level_tests.md) | Branch instruction-level tests (`test_branch`) | Accepted | uses the pattern of [034](034_instruction_level_cocotb_test_layer.md) |
| [036](036_reference_model.md) | Python reference model for RV32IM | Accepted | differential testing against the DUT |
| [037](037_canonical_pipeline_bubble_instruction.md) | Canonical bubble instruction (`0x00000013`) | Accepted | header number fixed 2026-11-12 (said 033) |
| [038](038_branch_resolution_ex_predict_not-taken.md) | Branch resolution in EX, predict-not-taken | Accepted (updated 2026-11-12) | header number fixed (said 032); taken-branch penalty is one cycle, see [057](057_pipeline_frontend_without_if_id_register.md) |
| [039](039_pipeline_critical_bug_fixes.md) | Pipeline critical bug fixes (stall/flush, propagation, trap flush) | Accepted (updated 2026-11-12) | its `if_id_register` references are qualified by [057](057_pipeline_frontend_without_if_id_register.md) |
| [040](040_pipeline_forwarding_hazards.md) | Pipeline forwarding hazard detection (MEM-RAW, WB-RAW) | Superseded by [056](056_wb_to_id_forwarding.md) | originally marked "superseded by commit `06260fc`" |
| [041](041_pipeline_data_hazard_limitation.md) | Pipeline data-hazard limitation (producer 3+ cycles ahead) | Superseded by [056](056_wb_to_id_forwarding.md) | historical Fmax figure of that campaign |
| [042](042_hardware_measurement_without_signaltap.md) | Hardware measurement without SignalTap | Accepted | replaces [026](026_signaltap_metric_extraction.md) |
| [043](043_pipeline_load_use_branch_duplicate.md) | A load-use hazard on a branch executed the branch twice | Accepted | hazard wiring later formalised in [056](056_wb_to_id_forwarding.md) |
| [044](044_step_mode_processor_freeze.md) | Step mode: freezing the processor for the VGA console | Accepted (updated 2026-11-12) | adds `step_mode_ctrl`, `key_step`/`step_mode`, `alu_rv32im.hold`, `pc.step_hold`; freeze sources documented |
| [045](045_pipeline_console_alu_source_ports.md) | Pipeline console: the ALU source mux inputs were left unconnected | Accepted | connects `alua_src`/`alub_src` in `top_pipeline.sv` |
| [046](046_single_cycle_imem_next_pc.md) | Single-cycle instruction memory: registered read with `next_pc` | Accepted (updated 2026-11-12) | supersedes [011](011_instruction_memory_async_read.md) §3-4; keeps CPI = 1 |
| [047](047_data_memory_window_and_split_images.md) | Data memory: 4 KB window and separate code/data images | Accepted | `DMEM_DEPTH = 1024`, parameterised index, split `.mem` images |
| [048](048_single_cycle_half_cycle_data_memory.md) | Single-cycle data memory: half-cycle M10K read | Accepted | supersedes in part [020](020_data_memory_async_read.md) and [021](021_data_memory_organization.md) |
| [049](049_single_cycle_40mhz_cpu_clock.md) | Single-cycle processor clock: 40 MHz from a dedicated PLL | Accepted (updated 2026-11-12) | figures marked as that campaign's |
| [050](050_dedicated_adder_for_address_and_redirect.md) | Dedicated adder for the load/store address and the branch target | Accepted (updated 2026-11-12) | figures marked as that campaign's |
| [051](051_tohost_parameter_decimal.md) | The `tohost` address parameter reaches Quartus in decimal | Accepted | `TOHOST_ADDR` default `0x708` |
| [052](052_single_cycle_fetch_waits_for_freeze.md) | Single-cycle fetch waits for the power-on pause to lift | Accepted | `fetch_valid` gating |
| [053](053_redirect_priority_and_valid_retirement.md) | Redirect priority and explicit retirement validity | Accepted (updated 2026-11-12) | includes `tail_loop_halt` and the measurement window |
| [054](054_runtime_program_loader.md) | Runtime program loader (`SW[3:0]`, `KEY[2]`) | Accepted | records the loader and the memory write ports; updates [004](004_shared_modules_boundary.md) |
| [055](055_vga_console_architecture.md) | VGA console: architecture and interface changes | Accepted | records the console chain, shadows, `dbg_regs`; updates [004](004_shared_modules_boundary.md) |
| [056](056_wb_to_id_forwarding.md) | WB-to-ID forwarding and MEM-RAW restricted to loads | Accepted | supersedes [040](040_pipeline_forwarding_hazards.md) and [041](041_pipeline_data_hazard_limitation.md) |
| [057](057_pipeline_frontend_without_if_id_register.md) | Pipeline frontend without an IF/ID register: one-cycle branch penalty | Accepted | changes the frontend contract of [038](038_branch_resolution_ex_predict_not-taken.md), [039](039_pipeline_critical_bug_fixes.md) and [043](043_pipeline_load_use_branch_duplicate.md) |
