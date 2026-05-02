module top_single_cycle (
    input logic clk,     // 50 MHz — DE1-SoC PIN_AF14
    input logic rst_n    // Active-low synchronous reset — KEY[0]
);

    localparam [4:0] ALU_DIV  = 5'b01110;
    localparam [4:0] ALU_DIVU = 5'b01111;
    localparam [4:0] ALU_REM  = 5'b10000;
    localparam [4:0] ALU_REMU = 5'b10001;

    localparam [1:0] ALUA_RS1  = 2'b00;
    localparam [1:0] ALUA_PC   = 2'b01;
    localparam [1:0] ALUA_ZERO = 2'b10;

    localparam [1:0] WB_ALU = 2'b00;
    localparam [1:0] WB_MEM = 2'b01;
    localparam [1:0] WB_PC4 = 2'b10;


    // Fetch
    logic [31:0] pc;
    logic [31:0] pc_plus4;
    logic [31:0] instruction;

    // Instruction fields
    logic [6:0]  opcode;
    logic [4:0]  rd_addr;
    logic [2:0]  funct3;
    logic [4:0]  rs1_addr;
    logic [4:0]  rs2_addr;
    logic [6:0]  funct7;

    // Control signals
    logic        ru_wr;
    logic [2:0]  imm_src;
    logic [1:0]  alua_src;
    logic        alub_src;
    logic [4:0]  alu_op;
    logic [4:0]  br_op;
    logic        dm_wr;
    logic [2:0]  dm_ctrl;
    logic [1:0]  ru_data_wr_src;

    // Register file
    logic [31:0] rs1_data;
    logic [31:0] rs2_data;
    logic [31:0] rd_data;

    // Immediate
    logic [31:0] imm_out;

    // ALU
    logic [31:0] alu_a;
    logic [31:0] alu_b;
    logic [31:0] alu_res;
    logic        div_busy;
    logic        div_done;

    // Branch
    logic        branch;
    logic        mask_pc_lsb;

    // Memory
    logic [31:0] dm_rd_data;

    // Write-enable gate (ADR 023)
    logic        is_div;
    logic        wr_en_gated;


    assign opcode   = instruction[6:0];
    assign rd_addr  = instruction[11:7];
    assign funct3   = instruction[14:12];
    assign rs1_addr = instruction[19:15];
    assign rs2_addr = instruction[24:20];
    assign funct7   = instruction[31:25];

    // Write-enable gate for division
    assign is_div = (alu_op == ALU_DIV || alu_op == ALU_DIVU ||
                        alu_op == ALU_REM || alu_op == ALU_REMU);
    assign wr_en_gated = ru_wr & (~is_div | div_done);

    always_comb begin
        case (alua_src)
            ALUA_RS1:  alu_a = rs1_data;
            ALUA_PC:   alu_a = pc;
            ALUA_ZERO: alu_a = 32'b0;
            default:   alu_a = rs1_data;
        endcase
    end

    assign alu_b = alub_src ? imm_out : rs2_data;

    always_comb begin
        case (ru_data_wr_src)
            WB_ALU:  rd_data = alu_res;
            WB_MEM:  rd_data = dm_rd_data;
            WB_PC4:  rd_data = pc_plus4;
            default: rd_data = alu_res;
        endcase
    end

    pc u_pc (
        .clk         (clk),
        .rst_n       (rst_n),
        .branch      (branch),
        .mask_pc_lsb (mask_pc_lsb),
        .alu_res     (alu_res),
        .div_busy    (div_busy),
        .pc          (pc),
        .pc_plus4    (pc_plus4)
    );

    instruction_memory #(
        .IMEM_DEPTH (1024)
    ) u_imem (
        .addr        (pc),
        .instruction (instruction)
    );

    control_unit u_cu (
        .opcode          (opcode),
        .funct3          (funct3),
        .funct7          (funct7),
        .ru_wr           (ru_wr),
        .imm_src         (imm_src),
        .alua_src        (alua_src),
        .alub_src        (alub_src),
        .alu_op          (alu_op),
        .br_op           (br_op),
        .dm_wr           (dm_wr),
        .dm_ctrl         (dm_ctrl),
        .ru_data_wr_src  (ru_data_wr_src)
    );

    register_file u_rf (
        .clk      (clk),
        .rst      (~rst_n),         // register_file uses active-high synchronous rst
        .rs1_addr (rs1_addr),
        .rs2_addr (rs2_addr),
        .rd_addr  (rd_addr),
        .rd_data  (rd_data),
        .wr_en    (wr_en_gated),    // gated - not ru_wr directly (ADR 023)
        .rs1_data (rs1_data),
        .rs2_data (rs2_data)
    );

    imm_gen u_imm (
        .instruction (instruction),
        .imm_src     (imm_src),
        .imm_out     (imm_out)
    );

    branch_unit u_bu (
        .rs1_data    (rs1_data),
        .rs2_data    (rs2_data),
        .br_op       (br_op),
        .branch      (branch),
        .mask_pc_lsb (mask_pc_lsb)
    );

    alu_rv32im u_alu (
        .clk      (clk),
        .rst_n    (rst_n),
        .a        (alu_a),
        .b        (alu_b),
        .alu_op   (alu_op),
        .alu_res  (alu_res),
        .div_busy (div_busy),
        .div_done (div_done)
    );

    data_memory #(
        .DMEM_DEPTH (8192)
    ) u_dmem (
        .clk     (clk),
        .addr    (alu_res),
        .wr_data (rs2_data),
        .dm_wr   (dm_wr),
        .dm_ctrl (dm_ctrl),
        .rd_data (dm_rd_data)
    );

endmodule