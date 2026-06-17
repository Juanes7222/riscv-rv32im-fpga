// PC unit for the pipelined processor: implements predict-not-taken with EX-stage resolution.
module pc_unit (
    input  logic        clk,
    input  logic        rst,
    input  logic        stall,
    input  logic        branch_taken,
    input  logic        mask_pc_lsb,
    input  logic [31:0] branch_target,
    output logic [31:0] pc
);
    logic [31:0] next_pc;
    logic [31:0] effective_target;

    // JALR requires bit 0 of target forced to zero (ADR 006)
    assign effective_target = mask_pc_lsb ? {branch_target[31:1], 1'b0} : branch_target;

    always_comb begin
        if (branch_taken)
            next_pc = effective_target;
        else
            next_pc = pc + 32'd4;
    end

    always_ff @(posedge clk) begin
        if (rst)
            pc <= '0;
        else if (!stall)
            pc <= next_pc;
    end
endmodule