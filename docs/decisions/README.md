# Architecture Decision Records

This index lists every design decision recorded for the `rv32im-pipeline-de1soc`
project. Each entry links to an individual ADR file. Records are numbered
sequentially in the order the decision was made. Once recorded, a decision is
never deleted - if a decision is reversed, a new ADR is added that supersedes
the original, and both remain in the index.

| # | Title | Status | Supersedes |
|---|-------|--------|------------|
| [001](001_harvard_memory_architecture.md) | Harvard memory architecture | Accepted | - |
| [002](002_implementation_order.md) | Single-cycle before pipeline | Accepted | - |
| [003](003_rv32i_before_extension_m.md) | RV32I first, extension M as second iteration | Accepted | - |
| [004](004_shared_modules_boundary.md) | Boundary between shared and microarchitecture-specific modules | Accepted | - |
| [005](005_alua_src_2bit.md) | ALU operand-A source extended to 2 bits | Accepted | - |
| [006](006_jalr_pc_masking.md) | JALR LSB masking responsibility assigned to branch_unit | Accepted | - |
| [007](007_branch_unit_inputs.md) | Branch unit receives rs1/rs2 directly from register file | Accepted | - |
| [008](008_m_extension_implementation.md) | Combinational multiplier, multi-cycle divisor for extension M | Accepted | - |
| [009](009_mulhsu_33bit_extension.md) | MULHSU implemented via 33-bit sign/zero extension | Accepted | - |
| [010](010_systemverilog_style.md) | Unified SystemVerilog style: logic + always_comb | Accepted | - |
| [011](011_instruction_memory_async_read.md) | Instruction memory asynchronous read | Superseded in part by ADR 046 | - |
| [012](012_reset_vector.md) | Reset vector `0x00000000` | Accepted | - |
| [013](013_memory_sizes.md) | Instruction and data memory sizes | Accepted | - |
| [014](014_memory_initialize_format.md) | Memory Initialization Format | Accepted | - |
| [015](015_register_file_ff_array.md) | Register File: FF Array Implementation | Accepted | - |
| [016](016_register_file_reset_zero.md) | Register File: All Registers Reset to Zero | Accepted | - |
| [017](017_imm_gen_interface.md) | Immediate Generator: Interface and Implementation | Accepted | - |
| [018](018_branch_unit.md) | Branch Unit: Interface and Implementation | Accepted | - |
| [019](019_alu_rv32im.md) | ALU RV32IM: Interface, MULHSU, and Division Strategy | Accepted | - |
| [020](020_data_memory_async_read.md) | Data Memory: Asynchronous Read | Superseded in part by ADR 048 | - |
| [021](021_data_memory_organization.md) | Data Memory: Word-Addressed Organization with Byte Enables | Accepted | - |
| [022](022_control_unit.md) | Control Unit: Interface and Implementation | Accepted | - |
| [023](023_wr_en_gated.md) | Register File Write Inhibit During Division | Accepted | - |
| [024](024_perf_counters.md) | Performance Counters | Accepted | - |
| [025](025_mem_init_define.md) | Memory Initialization via `define Macros | Accepted | - |
| [026](026_signaltap_metric_extraction.md) | SignalTap Metric Extraction | Accepted | - |
| [027](027_riscv-tests_compilation.md) | riscv-tests Compilation for Reset Vector 0x00000000 | Accepted | - |
| [028](028_pass-fail_onvention.md) | Pass/Fail Convention: tohost Symbol Monitoring in cocotb | Accepted | - |
| [029](029_cocotb_directory_structure.md) | cocotb Directory Structure | Accepted | - |
| [030](030_csr_and_trap_handling.md) | CSR File and Minimal Trap Handling (ECALL / MRET) | Accepted | - |
| [031](031_m_extension_test_failures_and_fsm_correction.md) | M-Extension Test Failures and Division FSM Correction | Accepted | supersedes parts of [008](008_m_extension_implementation.md), [019](019_alu_rv32im.md), [023](023_wr_en_gated.md) |
| [032](032_single_cycle_cpi_one_test_layer.md) | Single-Cycle CPI=1 Test Layer (test_cpi_one) | Accepted | implements the test layer called out in [029](029_cocotb_directory_structure.md) |
| [033](033_rv32mi_test_layer_and_csr_extension.md) | RV32MI Test Layer + CSR Register File Extension | Accepted | extends the CSR file from [030](030_csr_and_trap_handling.md) with 8 additional registers; adds rv32mi cocotb layer |
| [034](034_instruction_level_cocotb_test_layer.md) | Instruction-Level Cocotb Test Layer (test_alu_rv32i) | Accepted | implements the instruction-level test layer called out in [029](029_cocotb_directory_structure.md) |
| [035](035_branch_instruction_level_tests.md) | Branch Instruction-Level Tests (test_branch) | Accepted | adds BEQ/BNE/BLT/BGE/BLTU/BGEU tests using the pattern from [034] |
| [036](036_reference_model.md) | Python Reference Model for RV32IM | Accepted | implements the reference model called out in [029](029_cocotb_directory_structure.md); enables model-vs-DUT differential testing |
| [039](039_pipeline_critical_bug_fixes.md) | Pipeline Critical Bug Fixes | Accepted | fixes four critical bugs in the 5-stage pipeline (stall/flush separation, register propagation, trap flush); creates smoke tests |
| [040](040_pipeline_forwarding_hazards.md) | Pipeline Forwarding Hazard Detection (MEM-RAW and WB-RAW) | Accepted | extends hazard detection for non-load RAW hazards; fixes forwarding race for 2-cycle-old producers; 5/65 riscv tests pass |
| [036](037_canonical_pipeline_bubble_instruction.md) | Canonical Bubble Instruction for Pipeline Flush and Stall Insertion | Accepted | |
| [036](038_branch_resolution_ex_predict_not-taken.md) | Branch Resolution in EX with Predict-Not-Taken Policy | Accepted | |
| [044](044_step_mode_processor_freeze.md) | Step Mode: Freezing the Processor for the VGA Console | Accepted | adds the `key_step`/`step_mode` inputs, the `step_mode_ctrl` module, `alu_rv32im.hold` and `pc.step_hold` |
| [045](045_pipeline_console_alu_source_ports.md) | Pipeline console: the ALU source mux inputs were left unconnected | Accepted | connects `alua_src`/`alub_src` in `top_pipeline.sv`; removes the constant register whose removal crashed the Quartus synthesis report |
| [046](046_single_cycle_imem_next_pc.md) | Single-cycle instruction memory: registered read addressed with next_pc | Accepted | supersedes ADR 011 §4; moves the single-cycle IMEM into M10K blocks and keeps CPI = 1 |
| [047](047_data_memory_window_and_split_images.md) | Data memory: a 4 KB window and separate code/data images | Accepted | raises `DMEM_DEPTH` to 1 024 in both architectures, parameterises the word index, splits the `.mem` images, moves CoreMark's working block to `.bss`; keeps CPI = 1 |
| [048](048_single_cycle_half_cycle_data_memory.md) | Single-cycle data memory: half-cycle M10K read | Accepted | replaces the 4 KB logic-cell array (32 768 registers, not routable) with four byte-lane M10K blocks read on the falling edge; keeps CPI = 1 |
| [049](049_single_cycle_40mhz_cpu_clock.md) | Single-cycle processor clock: 40 MHz from a dedicated PLL | Accepted | the multiply writeback measures 48.37 MHz, so the single-cycle CPU runs from a 40 MHz PLL output instead of `CLOCK_50`; the pipeline keeps 50 MHz (58.74 MHz) |
| [050](050_dedicated_adder_for_address_and_redirect.md) | Dedicated adder for the load/store address and the branch target | Accepted | the shared ALU output mux put the DSP multiplier in the timing path of a don't-care value: the single-cycle goes from 29 to 48.37 MHz and the pipeline from 48 to 58.74 MHz |
| [051](051_tohost_parameter_decimal.md) | The tohost address parameter reaches Quartus in decimal | Accepted | Quartus does not parse the `0x` form of an Untyped parameter: `TOHOST_ADDR=0x6000` reached the netlist as 0, so `program_done` never fired on the board; the flow and the cocotb build now pass the decimal value |
| [052](052_single_cycle_fetch_waits_for_freeze.md) | Single-cycle fetch waits for the power-on pause to lift | Accepted | `fetch_valid` was set unconditionally after reset, so the instruction memory captured address 4 before the pause ended and the first instruction of every program was skipped; `branch_stress` looped 2^32 times and reported `0x400000004` instead of 4004 |
