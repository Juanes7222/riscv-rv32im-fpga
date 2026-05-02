module imm_gen (
    input  logic [31:0] instruction,
    input  logic [2:0]  imm_src,
    output logic [31:0] imm_out
);

    localparam [2:0] IMM_I = 3'b000;
    localparam [2:0] IMM_S = 3'b001;
    localparam [2:0] IMM_B = 3'b010;
    localparam [2:0] IMM_U = 3'b011;
    localparam [2:0] IMM_J = 3'b100;

    always_comb begin
        case (imm_src)
            IMM_I: imm_out = {{20{instruction[31]}}, instruction[31:20]};

            IMM_S: imm_out = {{20{instruction[31]}},
                               instruction[31:25], instruction[11:7]};

            IMM_B: imm_out = {{19{instruction[31]}},
                               instruction[31],    instruction[7],
                               instruction[30:25], instruction[11:8], 1'b0};

            IMM_U: imm_out = {instruction[31:12], 12'b0};

            IMM_J: imm_out = {{11{instruction[31]}},
                               instruction[31],    instruction[19:12],
                               instruction[20],    instruction[30:21], 1'b0};

            default: imm_out = 32'b0;
        endcase
    end

endmodule