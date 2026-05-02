module control_unit (
    input  logic [6:0] opcode,
    input  logic [2:0] funct3,
    input  logic [6:0] funct7,

    output logic        ru_wr,
    output logic [2:0]  imm_src,
    output logic [1:0]  alua_src,
    output logic        alub_src,
    output logic [4:0]  alu_op,
    output logic [4:0]  br_op,
    output logic        dm_wr,
    output logic [2:0]  dm_ctrl,
    output logic [1:0]  ru_data_wr_src
);

    // Opcodes
    localparam [6:0] OP_LUI    = 7'b0110111;
    localparam [6:0] OP_AUIPC  = 7'b0010111;
    localparam [6:0] OP_JAL    = 7'b1101111;
    localparam [6:0] OP_JALR   = 7'b1100111;
    localparam [6:0] OP_BRANCH = 7'b1100011;
    localparam [6:0] OP_LOAD   = 7'b0000011;
    localparam [6:0] OP_STORE  = 7'b0100011;
    localparam [6:0] OP_IMM    = 7'b0010011;
    localparam [6:0] OP_REG    = 7'b0110011;

    // Immediate format selector
    localparam [2:0] IMM_I = 3'b000;
    localparam [2:0] IMM_S = 3'b001;
    localparam [2:0] IMM_B = 3'b010;
    localparam [2:0] IMM_U = 3'b011;
    localparam [2:0] IMM_J = 3'b100;

    // ALU operation codes
    localparam [4:0] ALU_ADD    = 5'b00000;
    localparam [4:0] ALU_SUB    = 5'b00001;
    localparam [4:0] ALU_SLL    = 5'b00010;
    localparam [4:0] ALU_SLT    = 5'b00011;
    localparam [4:0] ALU_SLTU   = 5'b00100;
    localparam [4:0] ALU_XOR    = 5'b00101;
    localparam [4:0] ALU_SRL    = 5'b00110;
    localparam [4:0] ALU_SRA    = 5'b00111;
    localparam [4:0] ALU_OR     = 5'b01000;
    localparam [4:0] ALU_AND    = 5'b01001;
    localparam [4:0] ALU_MUL    = 5'b01010;
    localparam [4:0] ALU_MULH   = 5'b01011;
    localparam [4:0] ALU_MULHSU = 5'b01100;
    localparam [4:0] ALU_MULHU  = 5'b01101;
    localparam [4:0] ALU_DIV    = 5'b01110;
    localparam [4:0] ALU_DIVU   = 5'b01111;
    localparam [4:0] ALU_REM    = 5'b10000;
    localparam [4:0] ALU_REMU   = 5'b10001;

    // ALU-A source selector (ADR 005)
    localparam [1:0] ALUA_RS1  = 2'b00;
    localparam [1:0] ALUA_PC   = 2'b01;
    localparam [1:0] ALUA_ZERO = 2'b10;

    // Branch type prefix for br_op[4:3]
    localparam [1:0] BR_NONE = 2'b00;
    localparam [1:0] BR_COND = 2'b01;
    localparam [1:0] BR_JAL  = 2'b10;
    localparam [1:0] BR_JALR = 2'b11;

    // Write-back source selector
    localparam [1:0] WB_ALU = 2'b00;
    localparam [1:0] WB_MEM = 2'b01;
    localparam [1:0] WB_PC4 = 2'b10;

    // Main decode
    always_comb begin
        // Default assignments: safe no-op, no latch inference.
        ru_wr          = 1'b0;
        imm_src        = IMM_I;
        alua_src       = ALUA_RS1;
        alub_src       = 1'b0;
        alu_op         = ALU_ADD;
        br_op          = {BR_NONE, 3'b000};
        dm_wr          = 1'b0;
        dm_ctrl        = funct3;
        ru_data_wr_src = WB_ALU;

        case (opcode)

            OP_LUI: begin
                ru_wr          = 1'b1;
                imm_src        = IMM_U;
                alua_src       = ALUA_ZERO;   // instruction[19:15] is imm (ADR 005)
                alub_src       = 1'b1;
                alu_op         = ALU_ADD;
                ru_data_wr_src = WB_ALU;
            end

            OP_AUIPC: begin
                ru_wr          = 1'b1;
                imm_src        = IMM_U;
                alua_src       = ALUA_PC;
                alub_src       = 1'b1;
                alu_op         = ALU_ADD;
                ru_data_wr_src = WB_ALU;
            end

            OP_JAL: begin
                ru_wr          = 1'b1;
                imm_src        = IMM_J;
                alua_src       = ALUA_PC;
                alub_src       = 1'b1;
                alu_op         = ALU_ADD;
                br_op          = {BR_JAL, 3'b000};
                ru_data_wr_src = WB_PC4;
            end

            OP_JALR: begin
                ru_wr          = 1'b1;
                imm_src        = IMM_I;
                alua_src       = ALUA_RS1;
                alub_src       = 1'b1;
                alu_op         = ALU_ADD;
                br_op          = {BR_JALR, 3'b000};
                ru_data_wr_src = WB_PC4;
            end

            OP_BRANCH: begin
                imm_src  = IMM_B;
                alua_src = ALUA_PC;
                alub_src = 1'b1;
                alu_op   = ALU_ADD;
                br_op    = {BR_COND, funct3};
            end

            OP_LOAD: begin
                ru_wr          = 1'b1;
                imm_src        = IMM_I;
                alua_src       = ALUA_RS1;
                alub_src       = 1'b1;
                alu_op         = ALU_ADD;
                dm_ctrl        = funct3;      // LB/LH/LW/LBU/LHU
                ru_data_wr_src = WB_MEM;
            end

            OP_STORE: begin
                imm_src  = IMM_S;
                alua_src = ALUA_RS1;
                alub_src = 1'b1;
                alu_op   = ALU_ADD;
                dm_wr    = 1'b1;
                dm_ctrl  = funct3;            // SB/SH/SW
            end

            OP_IMM: begin
                ru_wr          = 1'b1;
                imm_src        = IMM_I;
                alua_src       = ALUA_RS1;
                alub_src       = 1'b1;
                ru_data_wr_src = WB_ALU;

                case (funct3)
                    3'b000: alu_op = ALU_ADD;
                    3'b010: alu_op = ALU_SLT;
                    3'b011: alu_op = ALU_SLTU;
                    3'b100: alu_op = ALU_XOR;
                    3'b110: alu_op = ALU_OR;
                    3'b111: alu_op = ALU_AND;
                    3'b001: alu_op = ALU_SLL;
                    3'b101: alu_op = funct7[5] ? ALU_SRA : ALU_SRL;
                    default: alu_op = ALU_ADD;
                endcase
            end

            OP_REG: begin
                ru_wr          = 1'b1;
                alua_src       = ALUA_RS1;
                alub_src       = 1'b0;
                ru_data_wr_src = WB_ALU;

                // funct7[0]=1 --> M extension (funct7=0000001)
                // funct7[5]=1 --> SUB or SRA (funct7=0100000)
                // Priority: M extension checked first on conflicting funct3 slots.
                case (funct3)
                    3'b000: alu_op = funct7[0] ? ALU_MUL    :
                                     funct7[5] ? ALU_SUB    : ALU_ADD;
                    3'b001: alu_op = funct7[0] ? ALU_MULH   : ALU_SLL;
                    3'b010: alu_op = funct7[0] ? ALU_MULHSU : ALU_SLT;
                    3'b011: alu_op = funct7[0] ? ALU_MULHU  : ALU_SLTU;
                    3'b100: alu_op = funct7[0] ? ALU_DIV    : ALU_XOR;
                    3'b101: alu_op = funct7[0] ? ALU_DIVU   :
                                     funct7[5] ? ALU_SRA    : ALU_SRL;
                    3'b110: alu_op = funct7[0] ? ALU_REM    : ALU_OR;
                    3'b111: alu_op = funct7[0] ? ALU_REMU   : ALU_AND;
                    default: alu_op = ALU_ADD;
                endcase
            end

            default: begin
                // ecall, ebreak, CSR, undefined opcodes: safe no-op.
                // ru_wr=0 and dm_wr=0 already set by default block above.
                // Explicit re-assertion for clarity and lint compliance.
                ru_wr = 1'b0;
                dm_wr = 1'b0;
                br_op = {BR_NONE, 3'b000};
            end

        endcase
    end

endmodule