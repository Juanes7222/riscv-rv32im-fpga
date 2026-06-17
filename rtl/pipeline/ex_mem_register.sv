// EX/MEM pipeline register: propagates ALU result, store data, control, and CSR/trap to MEM.
//
// stall: holds current contents (per ADR 037). Critical for the multi-cycle
// division stall to actually freeze the pipeline: without this, MEM and WB
// would advance while EX is held on a DIV, desynchronising the datapath.
//
// flush: writes the canonical bubble. Driven by trap_flush (not branch_flush):
//   - A taken branch is IN EX when it resolves, so EX/MEM should capture
//     the branch instruction normally (it retires through MEM and WB).
//   - A trap is IN WB when it resolves, so the EX-stage and MEM-stage
//     instructions (younger than the trap) must be invalidated.
//
// Note that branch_flush already bubbles IF/ID and ID/EX (the two stages
// younger than the branch), which is correct: those are the only stages
// younger than the branch.
module ex_mem_register (
    input  logic        clk,
    input  logic        rst,
    input  logic        stall,
    input  logic        flush,
    // Datapath
    input  logic [31:0] ex_alu_result,
    input  logic [31:0] ex_rs2_data_fwd,
    input  logic [31:0] ex_rs1_data_fwd,  // needed for CSR zimm / rs1 source
    input  logic [31:0] ex_instruction,
    input  logic [4:0]  ex_rd_addr,
    input  logic        ex_ru_wr,
    input  logic        ex_dm_wr,
    input  logic [2:0]  ex_dm_ctrl,
    input  logic [1:0]  ex_ru_data_wr_src,
    input  logic [31:0] ex_pc_plus4,
    input  logic [31:0] ex_pc,
    // CSR / trap
    input  logic        ex_trap_entry,
    input  logic        ex_mret_exec,
    input  logic [11:0] ex_csr_addr,
    input  logic        ex_csr_wr,
    input  logic [1:0]  ex_csr_op,
    input  logic        ex_csr_imm,
    input  logic [4:0]  ex_rs1_addr,       // zimm[4:0] source for immediate CSR ops
    // Datapath outputs
    output logic [31:0] mem_alu_result,
    output logic [31:0] mem_rs2_data,
    output logic [31:0] mem_rs1_data,
    output logic [31:0] mem_instruction,
    output logic [4:0]  mem_rd_addr,
    output logic        mem_ru_wr,
    output logic        mem_dm_wr,
    output logic [2:0]  mem_dm_ctrl,
    output logic [1:0]  mem_ru_data_wr_src,
    output logic [31:0] mem_pc_plus4,
    output logic [31:0] mem_pc,
    // CSR / trap outputs
    output logic        mem_trap_entry,
    output logic        mem_mret_exec,
    output logic [11:0] mem_csr_addr,
    output logic        mem_csr_wr,
    output logic [1:0]  mem_csr_op,
    output logic        mem_csr_imm,
    output logic [4:0]  mem_rs1_addr
);
    localparam logic [31:0] BUBBLE = 32'h00000013;

    always_ff @(posedge clk) begin
        if (rst) begin
            mem_alu_result      <= '0;
            mem_rs2_data        <= '0;
            mem_rs1_data        <= '0;
            mem_instruction     <= BUBBLE;
            mem_rd_addr         <= '0;
            mem_ru_wr           <= 1'b0;
            mem_dm_wr           <= 1'b0;
            mem_dm_ctrl         <= '0;
            mem_ru_data_wr_src  <= '0;
            mem_pc_plus4        <= '0;
            mem_pc              <= '0;
            mem_trap_entry      <= 1'b0;
            mem_mret_exec       <= 1'b0;
            mem_csr_addr        <= '0;
            mem_csr_wr          <= 1'b0;
            mem_csr_op          <= '0;
            mem_csr_imm         <= 1'b0;
            mem_rs1_addr        <= '0;
        end else if (flush) begin
            mem_alu_result      <= '0;
            mem_rs2_data        <= '0;
            mem_rs1_data        <= '0;
            mem_instruction     <= BUBBLE;
            mem_rd_addr         <= '0;
            mem_ru_wr           <= 1'b0;
            mem_dm_wr           <= 1'b0;
            mem_dm_ctrl         <= '0;
            mem_ru_data_wr_src  <= '0;
            mem_pc_plus4        <= '0;
            mem_pc              <= '0;
            mem_trap_entry      <= 1'b0;
            mem_mret_exec       <= 1'b0;
            mem_csr_addr        <= '0;
            mem_csr_wr          <= 1'b0;
            mem_csr_op          <= '0;
            mem_csr_imm         <= 1'b0;
            mem_rs1_addr        <= '0;
        end else if (!stall) begin
            mem_alu_result      <= ex_alu_result;
            mem_rs2_data        <= ex_rs2_data_fwd;
            mem_rs1_data        <= ex_rs1_data_fwd;
            mem_instruction     <= ex_instruction;
            mem_rd_addr         <= ex_rd_addr;
            mem_ru_wr           <= ex_ru_wr;
            mem_dm_wr           <= ex_dm_wr;
            mem_dm_ctrl         <= ex_dm_ctrl;
            mem_ru_data_wr_src  <= ex_ru_data_wr_src;
            mem_pc_plus4        <= ex_pc_plus4;
            mem_pc              <= ex_pc;
            mem_trap_entry      <= ex_trap_entry;
            mem_mret_exec       <= ex_mret_exec;
            mem_csr_addr        <= ex_csr_addr;
            mem_csr_wr          <= ex_csr_wr;
            mem_csr_op          <= ex_csr_op;
            mem_csr_imm         <= ex_csr_imm;
            mem_rs1_addr        <= ex_rs1_addr;
        end
        // On stall: implicit hold.
    end
endmodule
