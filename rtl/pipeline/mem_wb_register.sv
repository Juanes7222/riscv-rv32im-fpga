// MEM/WB pipeline register: propagates writeback data, CSR/trap control to WB.
//
// stall: holds current contents (per ADR 037). Without this, the multi-cycle
// division stall would let MEM and WB advance while EX is held, desynchronising
// the pipeline.
//
// No flush input. The trap is IN WB at the cycle trap_flush is asserted, so
// the trap itself must be allowed to commit normally (it owns the CSR writes
// to mepc, mcause, mtval). Bubbling MEM/WB would lose the trap instruction.
// The flush is wired to EX/MEM (which holds the instruction that was in EX
// when the trap resolved - one cycle younger than the trap).
module mem_wb_register (
    input  logic        clk,
    input  logic        rst,
    input  logic        stall,
    // Datapath
    input  logic [31:0] mem_alu_result,
    input  logic [31:0] mem_dm_rd_data,
    input  logic [31:0] mem_rs1_data,
    input  logic [31:0] mem_instruction,
    input  logic [4:0]  mem_rd_addr,
    input  logic        mem_ru_wr,
    input  logic [1:0]  mem_ru_data_wr_src,
    input  logic [31:0] mem_pc_plus4,
    input  logic [31:0] mem_pc,
    // CSR / trap
    input  logic        mem_trap_entry,
    input  logic        mem_mret_exec,
    input  logic [11:0] mem_csr_addr,
    input  logic        mem_csr_wr,
    input  logic [1:0]  mem_csr_op,
    input  logic        mem_csr_imm,
    input  logic [4:0]  mem_rs1_addr,
    // Outputs
    output logic [31:0] wb_alu_result,
    output logic [31:0] wb_dm_rd_data,
    output logic [31:0] wb_rs1_data,
    output logic [31:0] wb_instruction,
    output logic [4:0]  wb_rd_addr,
    output logic        wb_ru_wr,
    output logic [1:0]  wb_ru_data_wr_src,
    output logic [31:0] wb_pc_plus4,
    output logic [31:0] wb_pc,
    // CSR / trap outputs
    output logic        wb_trap_entry,
    output logic        wb_mret_exec,
    output logic [11:0] wb_csr_addr,
    output logic        wb_csr_wr,
    output logic [1:0]  wb_csr_op,
    output logic        wb_csr_imm,
    output logic [4:0]  wb_rs1_addr
);
    always_ff @(posedge clk) begin
        if (rst) begin
            wb_alu_result      <= '0;
            wb_dm_rd_data      <= '0;
            wb_rs1_data        <= '0;
            wb_instruction     <= 32'h00000013;  // canonical bubble (ADR 037)
            wb_rd_addr         <= '0;
            wb_ru_wr           <= 1'b0;
            wb_ru_data_wr_src  <= '0;
            wb_pc_plus4        <= '0;
            wb_pc              <= '0;
            wb_trap_entry      <= 1'b0;
            wb_mret_exec       <= 1'b0;
            wb_csr_addr        <= '0;
            wb_csr_wr          <= 1'b0;
            wb_csr_op          <= '0;
            wb_csr_imm         <= 1'b0;
            wb_rs1_addr        <= '0;
        end else if (!stall) begin
            wb_alu_result      <= mem_alu_result;
            wb_dm_rd_data      <= mem_dm_rd_data;
            wb_rs1_data        <= mem_rs1_data;
            wb_instruction     <= mem_instruction;
            wb_rd_addr         <= mem_rd_addr;
            wb_ru_wr           <= mem_ru_wr;
            wb_ru_data_wr_src  <= mem_ru_data_wr_src;
            wb_pc_plus4        <= mem_pc_plus4;
            wb_pc              <= mem_pc;
            wb_trap_entry      <= mem_trap_entry;
            wb_mret_exec       <= mem_mret_exec;
            wb_csr_addr        <= mem_csr_addr;
            wb_csr_wr          <= mem_csr_wr;
            wb_csr_op          <= mem_csr_op;
            wb_csr_imm         <= mem_csr_imm;
            wb_rs1_addr        <= mem_rs1_addr;
        end
        // On stall: implicit hold.
    end
endmodule
