// Control unit: combinational decode of opcode, funct3, funct7 into datapath controls.
// ADR 027: added trap/CSR signals for ECALL, MRET, and CSR instruction handling.
module control_unit (
    input  logic [6:0]  opcode,
    input  logic [2:0]  funct3,
    input  logic [6:0]  funct7,
    input  logic [11:0] instr_31_20,   // CSR address / ECALL funct12 field

    output logic         ru_wr,
    output logic [2:0]   imm_src,
    output logic [1:0]   alua_src,
    output logic         alub_src,
    output logic [4:0]   alu_op,
    output logic [4:0]   br_op,
    output logic         dm_wr,
    output logic [2:0]   dm_ctrl,
    output logic [1:0]   ru_data_wr_src,

    // Trap / CSR control (ADR 027)
    output logic         trap_entry,   // ECALL / EBREAK
    output logic         mret_exec,    // MRET
    output logic [11:0]  csr_addr,     // CSR register address
    output logic         csr_wr,       // CSR write strobe
    output logic [1:0]   csr_op,       // 00=CSRRW, 01=CSRRS, 10=CSRRC
    output logic         csr_imm       // 1 = immediate form (zimm source)
);

    localparam [6:0] OP_LUI    = 7'b0110111;
    localparam [6:0] OP_AUIPC  = 7'b0010111;
    localparam [6:0] OP_JAL    = 7'b1101111;
    localparam [6:0] OP_JALR   = 7'b1100111;
    localparam [6:0] OP_BRANCH = 7'b1100011;
    localparam [6:0] OP_LOAD   = 7'b0000011;
    localparam [6:0] OP_STORE  = 7'b0100011;
    localparam [6:0] OP_IMM    = 7'b0010011;
    localparam [6:0] OP_REG    = 7'b0110011;
    localparam [6:0] OP_SYSTEM = 7'b1110011;

    localparam [2:0] IMM_I = 3'b000;
    localparam [2:0] IMM_S = 3'b001;
    localparam [2:0] IMM_B = 3'b010;
    localparam [2:0] IMM_U = 3'b011;
    localparam [2:0] IMM_J = 3'b100;

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

    localparam [1:0] ALUA_RS1  = 2'b00;
    localparam [1:0] ALUA_PC   = 2'b01;
    localparam [1:0] ALUA_ZERO = 2'b10;

    localparam [4:0] BR_OP_NONE = 5'b00_000;
    localparam [4:0] BR_OP_JAL  = 5'b10_000;
    localparam [4:0] BR_OP_JALR = 5'b11_000;

    localparam [1:0] WB_ALU = 2'b00;
    localparam [1:0] WB_MEM = 2'b01;
    localparam [1:0] WB_PC4 = 2'b10;
    localparam [1:0] WB_CSR = 2'b11;    // ADR 027: CSR read data

    // Intermediate signals - workaround for Icarus bit-select in always_comb
    logic        funct7_5;
    logic        funct7_0;
    logic [4:0]  br_op_cond;

    assign funct7_5   = funct7[5];
    assign funct7_0   = funct7[0];
    assign br_op_cond = {2'b01, funct3};

    always_comb begin
        // Defaults
        ru_wr          = 1'b0;
        imm_src        = IMM_I;
        alua_src       = ALUA_RS1;
        alub_src       = 1'b0;
        alu_op         = ALU_ADD;
        br_op          = BR_OP_NONE;
        dm_wr          = 1'b0;
        dm_ctrl        = funct3;
        ru_data_wr_src = WB_ALU;
        // CSR / trap defaults
        trap_entry     = 1'b0;
        mret_exec      = 1'b0;
        csr_addr       = 12'b0;
        csr_wr         = 1'b0;
        csr_op         = 2'b00;
        csr_imm        = 1'b0;

        case (opcode)

            OP_LUI: begin
                ru_wr          = 1'b1;
                imm_src        = IMM_U;
                alua_src       = ALUA_ZERO;
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
                br_op          = BR_OP_JAL;
                ru_data_wr_src = WB_PC4;
            end

            OP_JALR: begin
                ru_wr          = 1'b1;
                imm_src        = IMM_I;
                alua_src       = ALUA_RS1;
                alub_src       = 1'b1;
                alu_op         = ALU_ADD;
                br_op          = BR_OP_JALR;
                ru_data_wr_src = WB_PC4;
            end

            OP_BRANCH: begin
                imm_src  = IMM_B;
                alua_src = ALUA_PC;
                alub_src = 1'b1;
                alu_op   = ALU_ADD;
                br_op    = br_op_cond;
            end

            OP_LOAD: begin
                ru_wr          = 1'b1;
                imm_src        = IMM_I;
                alua_src       = ALUA_RS1;
                alub_src       = 1'b1;
                alu_op         = ALU_ADD;
                dm_ctrl        = funct3;
                ru_data_wr_src = WB_MEM;
            end

            OP_STORE: begin
                imm_src  = IMM_S;
                alua_src = ALUA_RS1;
                alub_src = 1'b1;
                alu_op   = ALU_ADD;
                dm_wr    = 1'b1;
                dm_ctrl  = funct3;
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
                    // funct7_5 distinguishes SRLI (0) from SRAI (1)
                    3'b101: alu_op = funct7_5 ? ALU_SRA : ALU_SRL;
                    default: alu_op = ALU_ADD;
                endcase
            end

            OP_REG: begin
                ru_wr          = 1'b1;
                alua_src       = ALUA_RS1;
                alub_src       = 1'b0;
                ru_data_wr_src = WB_ALU;

                case (funct3)
                    3'b000: alu_op = funct7_0 ? ALU_MUL    :
                                     funct7_5 ? ALU_SUB    : ALU_ADD;
                    3'b001: alu_op = funct7_0 ? ALU_MULH   : ALU_SLL;
                    3'b010: alu_op = funct7_0 ? ALU_MULHSU : ALU_SLT;
                    3'b011: alu_op = funct7_0 ? ALU_MULHU  : ALU_SLTU;
                    3'b100: alu_op = funct7_0 ? ALU_DIV    : ALU_XOR;
                    3'b101: alu_op = funct7_0 ? ALU_DIVU   :
                                     funct7_5 ? ALU_SRA    : ALU_SRL;
                    3'b110: alu_op = funct7_0 ? ALU_REM    : ALU_OR;
                    3'b111: alu_op = funct7_0 ? ALU_REMU   : ALU_AND;
                    default: alu_op = ALU_ADD;
                endcase
            end

            OP_SYSTEM: begin
                // ADR 027: Full trap/CSR handling
                if (funct3 == 3'b000) begin
                    // Environment call / trap return
                    case (instr_31_20)
                        12'h000: trap_entry = 1'b1;   // ECALL
                        12'h001: trap_entry = 1'b1;   // EBREAK
                        12'h302: mret_exec  = 1'b1;   // MRET
                        default: ;                      // WFI / undefined --> NOP
                    endcase
                    // No register writeback for ECALL/MRET
                    ru_wr  = 1'b0;
                    br_op  = BR_OP_NONE;
                end else begin
                    // CSR read/write instructions
                    ru_wr          = 1'b1;
                    ru_data_wr_src = WB_CSR;
                    csr_addr       = instr_31_20;
                    csr_wr         = 1'b1;   // may be gated in top-level for x0 reads
                    csr_imm        = funct3[2];  // 1 for CSRRWI/CSRRSI/CSRRCI
                    // funct3[1:0]-1 maps: 001-->00(CSRRW), 010-->01(CSRRS), 011-->10(CSRRC)
                    csr_op         = funct3[1:0] - 2'b01;
                end
                // Default datapath: add 0+0 (ALU result unused for CSR op)
                alua_src = ALUA_ZERO;
                alub_src = 1'b1;
                alu_op   = ALU_ADD;
                br_op    = BR_OP_NONE;
            end

            default: begin
                ru_wr = 1'b0;
                dm_wr = 1'b0;
                br_op = BR_OP_NONE;
            end

        endcase
    end

endmodule
