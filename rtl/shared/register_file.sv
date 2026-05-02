module register_file (
    input  logic        clk,
    input  logic        rst,

    input  logic [4:0]  rs1_addr,
    input  logic [4:0]  rs2_addr,
    output logic [31:0] rs1_data,
    output logic [31:0] rs2_data,

    input  logic [4:0]  rd_addr,
    input  logic [31:0] rd_data,
    input  logic        wr_en
);

    logic [31:0] regs [0:31];

    // Read ports: purely combinational, x0 hardwired to zero at the output.
    assign rs1_data = (rs1_addr == 5'b0) ? 32'b0 : regs[rs1_addr];
    assign rs2_data = (rs2_addr == 5'b0) ? 32'b0 : regs[rs2_addr];

    // Write port: synchronous, synchronous reset, x0 protected at write gate.
    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 1; i < 32; i++) begin
                regs[i] <= 32'b0;
            end
        end else if (wr_en && rd_addr != 5'b0) begin
            regs[rd_addr] <= rd_data;
        end
    end

endmodule