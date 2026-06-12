module pc (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        branch,
    input  logic        mask_pc_lsb,
    input  logic [31:0] alu_res,
    input  logic        div_busy,

    // ADR 027: Trap / MRET support
    input  logic        trap_entry,
    input  logic        mret_exec,
    input  logic [31:0] trap_target,
    input  logic [31:0] mepc_value,

    output logic [31:0] pc,
    output logic [31:0] pc_plus4
);

    logic [31:0] branch_target;
    logic [31:0] next_pc;

    assign pc_plus4 = pc + 32'd4;

    // branch_target: force bit 0 to zero for JALR (ADR 006)
    assign branch_target = mask_pc_lsb ? {alu_res[31:1], 1'b0} : alu_res;

    // next_pc priority: trap > mret > branch/jump > sequential
    assign next_pc = trap_entry ? trap_target :
                     mret_exec  ? mepc_value  :
                     branch     ? branch_target : pc_plus4;

    // PC register: synchronous reset to 0x00000000, stall during division
    always_ff @(posedge clk) begin
        if (!rst_n)
            pc <= 32'h0000_0000;
        else if (div_busy)
            pc <= pc;           // stall: DIV_RUNNING or DIV_DONE active
        else
            pc <= next_pc;
    end

endmodule
