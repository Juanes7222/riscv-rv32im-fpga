# Architecture Decision Records

This index lists every design decision recorded for the `rv32im-pipeline-de1soc`
project. Each entry links to an individual ADR file. Records are numbered
sequentially in the order the decision was made. Once recorded, a decision is
never deleted — if a decision is reversed, a new ADR is added that supersedes
the original, and both remain in the index.

| # | Title | Status | Supersedes |
|---|-------|--------|------------|
| [001](001_harvard_memory_architecture.md) | Harvard memory architecture | Accepted | — |
| [002](002_implementation_order.md) | Single-cycle before pipeline | Accepted | — |
| [003](003_rv32i_before_extension_m.md) | RV32I first, extension M as second iteration | Accepted | — |
| [004](004_shared_modules_boundary.md) | Boundary between shared and microarchitecture-specific modules | Accepted | — |
| [005](005_alua_src_2bit.md) | ALU operand-A source extended to 2 bits | Accepted | — |
| [006](006_jalr_pc_masking.md) | JALR LSB masking responsibility assigned to branch_unit | Accepted | — |
| [007](007_branch_unit_inputs.md) | Branch unit receives rs1/rs2 directly from register file | Accepted | — |
| [008](008_m_extension_implementation.md) | Combinational multiplier, multi-cycle divisor for extension M | Accepted | — |
| [009](009_mulhsu_33bit_extension.md) | MULHSU implemented via 33-bit sign/zero extension | Accepted | — |
| [010](010_systemverilog_style.md) | Unified SystemVerilog style: logic + always_comb | Accepted | — |
| [011](011_instruction_memory_async_read.md) | Instruction memory asynchronous read | Accepted | — |
| [012](012_reset_vector.md) | Reset vector `0x00000000` | Accepted | — |
| [013](013_memory_sizes.md) | Instruction memory 64 KB, data memory 32 KB | Accepted | — |
