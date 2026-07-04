// ID/EX pipeline register: propagates decoded control signals, operands, and CSR/trap fields to EX.
module id_ex_register (
    input  logic        clk,
    input  logic        rst,
    input  logic        flush,
    input  logic        stall,
    // PC and instruction data
    input  logic [31:0] id_pc,
    input  logic [31:0] id_instruction,
    // Operands from register file
    input  logic [31:0] id_rs1_data,
    input  logic [31:0] id_rs2_data,
    // Immediate
    input  logic [31:0] id_imm,
    // Register addresses
    input  logic [4:0]  id_rs1_addr,
    input  logic [4:0]  id_rs2_addr,
    input  logic [4:0]  id_rd_addr,
    // Control signals for datapath
    input  logic        id_ru_wr,
    input  logic [2:0]  id_imm_src,
    input  logic [1:0]  id_alua_src,
    input  logic        id_alub_src,
    input  logic [4:0]  id_alu_op,
    input  logic [4:0]  id_br_op,
    input  logic        id_dm_wr,
    input  logic [2:0]  id_dm_ctrl,
    input  logic [1:0]  id_ru_data_wr_src,
    // CSR / trap signals
    input  logic        id_trap_entry,
    input  logic        id_mret_exec,
    input  logic [11:0] id_csr_addr,
    input  logic        id_csr_wr,
    input  logic [1:0]  id_csr_op,
    input  logic        id_csr_imm,
    // Outputs for datapath
    output logic [31:0] ex_pc,
    output logic [31:0] ex_instruction,
    output logic [31:0] ex_rs1_data,
    output logic [31:0] ex_rs2_data,
    output logic [31:0] ex_imm,
    output logic [4:0]  ex_rs1_addr,
    output logic [4:0]  ex_rs2_addr,
    output logic [4:0]  ex_rd_addr,
    output logic        ex_ru_wr,
    output logic [2:0]  ex_imm_src,
    output logic [1:0]  ex_alua_src,
    output logic        ex_alub_src,
    output logic [4:0]  ex_alu_op,
    output logic [4:0]  ex_br_op,
    output logic        ex_dm_wr,
    output logic [2:0]  ex_dm_ctrl,
    output logic [1:0]  ex_ru_data_wr_src,
    // Outputs for CSR / trap
    output logic        ex_trap_entry,
    output logic        ex_mret_exec,
    output logic [11:0] ex_csr_addr,
    output logic        ex_csr_wr,
    output logic [1:0]  ex_csr_op,
    output logic        ex_csr_imm
);
    // Canonical bubble: ADDI x0, x0, 0 (ADR 037).
    localparam logic [31:0] BUBBLE = 32'h00000013;

    // Per ADR 037: stall preserves the current contents (hold); flush
    // invalidates them by writing the canonical bubble. These are
    // semantically distinct. The hazard detection unit asserts:
    //   - `stall` for both load-use and div_busy (IF/ID uses this).
    //   - `flush` (separately) only for branch/trap/load-use. The
    //     ID/EX register is what bubbles on load-use, not holds, so the
    //     load can advance to MEM and the consumer can move to EX in
    //     the next cycle. For div_busy, ID/EX holds (the div must
    //     stay in EX for 34 cycles).
    always_ff @(posedge clk) begin
        if (rst) begin
            ex_pc              <= '0;
            ex_instruction     <= BUBBLE;
            ex_rs1_data        <= '0;
            ex_rs2_data        <= '0;
            ex_imm             <= '0;
            ex_rs1_addr        <= '0;
            ex_rs2_addr        <= '0;
            ex_rd_addr         <= '0;
            ex_ru_wr           <= 1'b0;
            ex_imm_src         <= '0;
            ex_alua_src        <= '0;
            ex_alub_src        <= 1'b0;
            ex_alu_op          <= '0;
            ex_br_op           <= '0;
            ex_dm_wr           <= 1'b0;
            ex_dm_ctrl         <= '0;
            ex_ru_data_wr_src  <= '0;
            ex_trap_entry      <= 1'b0;
            ex_mret_exec       <= 1'b0;
            ex_csr_addr        <= '0;
            ex_csr_wr          <= 1'b0;
            ex_csr_op          <= '0;
            ex_csr_imm         <= 1'b0;
        end else if (flush) begin
            ex_pc              <= '0;
            ex_instruction     <= BUBBLE;
            ex_rs1_data        <= '0;
            ex_rs2_data        <= '0;
            ex_imm             <= '0;
            ex_rs1_addr        <= '0;
            ex_rs2_addr        <= '0;
            ex_rd_addr         <= '0;
            ex_ru_wr           <= 1'b0;
            ex_imm_src         <= '0;
            ex_alua_src        <= '0;
            ex_alub_src        <= 1'b0;
            ex_alu_op          <= '0;
            ex_br_op           <= '0;
            ex_dm_wr           <= 1'b0;
            ex_dm_ctrl         <= '0;
            ex_ru_data_wr_src  <= '0;
            ex_trap_entry      <= 1'b0;
            ex_mret_exec       <= 1'b0;
            ex_csr_addr        <= '0;
            ex_csr_wr          <= 1'b0;
            ex_csr_op          <= '0;
            ex_csr_imm         <= 1'b0;
        end else if (!stall) begin
            ex_pc              <= id_pc;
            ex_instruction     <= id_instruction;
            ex_rs1_data        <= id_rs1_data;
            ex_rs2_data        <= id_rs2_data;
            ex_imm             <= id_imm;
            ex_rs1_addr        <= id_rs1_addr;
            ex_rs2_addr        <= id_rs2_addr;
            ex_rd_addr         <= id_rd_addr;
            ex_ru_wr           <= id_ru_wr;
            ex_imm_src         <= id_imm_src;
            ex_alua_src        <= id_alua_src;
            ex_alub_src        <= id_alub_src;
            ex_alu_op          <= id_alu_op;
            ex_br_op           <= id_br_op;
            ex_dm_wr           <= id_dm_wr;
            ex_dm_ctrl         <= id_dm_ctrl;
            ex_ru_data_wr_src  <= id_ru_data_wr_src;
            ex_trap_entry      <= id_trap_entry;
            ex_mret_exec       <= id_mret_exec;
            ex_csr_addr        <= id_csr_addr;
            ex_csr_wr          <= id_csr_wr;
            ex_csr_op          <= id_csr_op;
            ex_csr_imm         <= id_csr_imm;
        end
        // On stall (div_busy): implicit hold (no update).
    end
endmodule