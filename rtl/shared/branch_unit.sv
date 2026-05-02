module branch_unit (
    input  logic [31:0] rs1_data,
    input  logic [31:0] rs2_data,
    input  logic [4:0]  br_op,
    output logic        branch,
    output logic        mask_pc_lsb
);

    localparam [1:0] BR_NONE   = 2'b00;
    localparam [1:0] BR_COND   = 2'b01;
    localparam [1:0] BR_JAL    = 2'b10;
    localparam [1:0] BR_JALR   = 2'b11;

    localparam [2:0] FUNCT3_BEQ  = 3'b000;
    localparam [2:0] FUNCT3_BNE  = 3'b001;
    localparam [2:0] FUNCT3_BLT  = 3'b100;
    localparam [2:0] FUNCT3_BGE  = 3'b101;
    localparam [2:0] FUNCT3_BLTU = 3'b110;
    localparam [2:0] FUNCT3_BGEU = 3'b111;

    logic [1:0] branch_type;
    logic [2:0] branch_funct3;

    assign branch_type   = br_op[4:3];
    assign branch_funct3 = br_op[2:0];
    assign mask_pc_lsb   = (branch_type == BR_JALR);

    always_comb begin
        branch = 1'b0;

        case (branch_type)
            BR_NONE: branch = 1'b0;

            BR_COND: begin
                case (branch_funct3)
                    FUNCT3_BEQ: branch = (rs1_data == rs2_data);
                    FUNCT3_BNE: branch = (rs1_data != rs2_data);
                    FUNCT3_BLT: branch = ($signed(rs1_data) <  $signed(rs2_data));
                    FUNCT3_BGE: branch = ($signed(rs1_data) >= $signed(rs2_data));
                    FUNCT3_BLTU: branch = (rs1_data <  rs2_data);
                    FUNCT3_BGEU: branch = (rs1_data >= rs2_data);
                    default: branch = 1'b0;
                endcase
            end

            BR_JAL:  branch = 1'b1;
            BR_JALR: branch = 1'b1;

            default: branch = 1'b0;
        endcase
    end

endmodule