module tohost_detector #(
    parameter logic [31:0] TOHOST_ADDR = 32'h8000_1000
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        dm_wr,          // data memory write enable from datapath
    input  logic [31:0] addr,           // write address (alu_res from datapath)
    output logic        program_done,   // latches high on first tohost write
    output logic        freeze          // combinational: == program_done
);

    always_ff @(posedge clk) begin
        if (!rst_n)
            program_done <= 1'b0;
        else if (dm_wr && (addr == TOHOST_ADDR))
            program_done <= 1'b1;
    end

    assign freeze = program_done;

endmodule