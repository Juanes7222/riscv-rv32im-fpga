// Forwarding unit: resolves RAW data hazards by selecting forwarded operands for EX.
// EX/MEM forwarding takes priority over MEM/WB when both conditions hold simultaneously.
module forwarding_unit (
    input  logic [4:0]  ex_rs1_addr,
    input  logic [4:0]  ex_rs2_addr,
    // EX/MEM stage
    input  logic [4:0]  mem_rd_addr,
    input  logic        mem_ru_wr,
    // MEM/WB stage
    input  logic [4:0]  wb_rd_addr,
    input  logic        wb_ru_wr,
    // Forward select outputs: 00=register file, 01=MEM/WB, 10=EX/MEM
    output logic [1:0]  fwd_a_sel,
    output logic [1:0]  fwd_b_sel
);
    always_comb begin
        fwd_a_sel = 2'b00;
        fwd_b_sel = 2'b00;

        // Forward A
        if (mem_ru_wr && (mem_rd_addr != 5'b0) && (mem_rd_addr == ex_rs1_addr))
            fwd_a_sel = 2'b10; // EX/MEM forward (higher priority)
        else if (wb_ru_wr && (wb_rd_addr != 5'b0) && (wb_rd_addr == ex_rs1_addr))
            fwd_a_sel = 2'b01; // MEM/WB forward

        // Forward B
        if (mem_ru_wr && (mem_rd_addr != 5'b0) && (mem_rd_addr == ex_rs2_addr))
            fwd_b_sel = 2'b10;
        else if (wb_ru_wr && (wb_rd_addr != 5'b0) && (wb_rd_addr == ex_rs2_addr))
            fwd_b_sel = 2'b01;
    end
endmodule