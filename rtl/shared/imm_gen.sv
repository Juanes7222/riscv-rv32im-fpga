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

    // Extract fields outside always_comb to avoid Icarus constant-select bug
    logic        sign_bit;
    logic [11:0] i_imm_raw;
    logic [6:0]  s_imm_hi;
    logic [4:0]  s_imm_lo;
    logic        b_bit_11;
    logic [5:0]  b_imm_hi;
    logic [3:0]  b_imm_lo;
    logic [19:0] u_imm;
    logic [7:0]  j_imm_19_12;
    logic        j_imm_11;
    logic [9:0]  j_imm_10_1;

    assign sign_bit    = instruction[31];
    assign i_imm_raw   = instruction[31:20];
    assign s_imm_hi    = instruction[31:25];
    assign s_imm_lo    = instruction[11:7];
    assign b_bit_11    = instruction[7];
    assign b_imm_hi    = instruction[30:25];
    assign b_imm_lo    = instruction[11:8];
    assign u_imm       = instruction[31:12];
    assign j_imm_19_12 = instruction[19:12];
    assign j_imm_11    = instruction[20];
    assign j_imm_10_1  = instruction[30:21];

    always_comb begin
        case (imm_src)
            IMM_I: imm_out = {{20{sign_bit}}, i_imm_raw};

            IMM_S: imm_out = {{20{sign_bit}}, s_imm_hi, s_imm_lo};

            IMM_B: imm_out = {{19{sign_bit}},
                               sign_bit, b_bit_11,
                               b_imm_hi, b_imm_lo, 1'b0};

            IMM_U: imm_out = {u_imm, 12'b0};

            IMM_J: imm_out = {{11{sign_bit}},
                               sign_bit, j_imm_19_12,
                               j_imm_11, j_imm_10_1, 1'b0};

            default: imm_out = 32'b0;
        endcase
    end

endmodule