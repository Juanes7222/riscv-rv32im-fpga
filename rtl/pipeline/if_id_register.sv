// IF/ID pipeline register: holds instruction and PC captured at the end of IF.
module if_id_register (
    input  logic        clk,
    input  logic        rst,
    input  logic        stall,
    input  logic        flush,
    input  logic [31:0] if_pc,
    input  logic [31:0] if_instruction,
    output logic [31:0] id_pc,
    output logic [31:0] id_instruction
);
    localparam logic [31:0] BUBBLE = 32'h00000013;

    always_ff @(posedge clk) begin
        if (rst) begin
            id_pc          <= '0;
            id_instruction <= BUBBLE;
        end else if (flush) begin
            id_pc          <= '0;
            id_instruction <= BUBBLE;
        end else if (!stall) begin
            id_pc          <= if_pc;
            id_instruction <= if_instruction;
        end
    end
endmodule