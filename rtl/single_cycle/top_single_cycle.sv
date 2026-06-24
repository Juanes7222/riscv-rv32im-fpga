module top_single_cycle #(
    parameter int IMEM_DEPTH = 16384,
    parameter int DMEM_DEPTH = 8192
)(
    input logic clk,     // 50 MHz - DE1-SoC PIN_AF14
    input logic rst_n,    // Active-low synchronous reset - KEY[0]
    output logic [9:0] ledr,       // pc[9:0]
    output logic [6:0] seven_seg_display0, // Connect to your 7-segment display output
    output logic [6:0] seven_seg_display1,
    output logic [6:0] seven_seg_display2,
    output logic [6:0] seven_seg_display3,
    output logic [6:0] seven_seg_display4,
    output logic [6:0] seven_seg_display5
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
    localparam [1:0] WB_CSR = 2'b11;    // ADR 027


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
    logic [11:0] instr_31_20;   // ADR 027: CSR address / ECALL funct12

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

    // ADR 027: Trap / CSR control signals
    logic        trap_entry;
    logic        mret_exec;
    logic [11:0] csr_addr;
    logic        csr_wr_raw;
    logic        csr_wr;
    logic [1:0]  csr_op;
    logic        csr_imm;
    logic [31:0] csr_rdata;
    logic [31:0] csr_wdata;
    logic [31:0] trap_target;
    logic [31:0] mepc_value;

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
    // Expose data-memory bus signals for cocotb monitor (flat names expected)
    // Protect from synthesis trimming — cocotb accesses these via hierarchical refs
    logic [31:0] dm_addr /* synthesis keep */;
    logic [31:0] dm_wdata /* synthesis keep */;

    // Alias internal signals to expected top-level names
    assign dm_addr  = alu_res;
    assign dm_wdata = rs2_data;

    // Write-enable gate (ADR 023)
    logic        is_div;
    logic        wr_en_gated;


    assign opcode      = instruction[6:0];
    assign rd_addr     = instruction[11:7];
    assign funct3      = instruction[14:12];
    assign rs1_addr    = instruction[19:15];
    assign rs2_addr    = instruction[24:20];
    assign funct7      = instruction[31:25];
    assign instr_31_20 = instruction[31:20];

    // Write-enable gate for division
    assign is_div = (alu_op == ALU_DIV || alu_op == ALU_DIVU ||
                        alu_op == ALU_REM || alu_op == ALU_REMU);
    assign wr_en_gated = ru_wr & (~is_div | div_done);

     assign ledr = pc[9:0];

    always_comb begin
        case (alua_src)
            ALUA_RS1:  alu_a = rs1_data;
            ALUA_PC:   alu_a = pc;
            ALUA_ZERO: alu_a = 32'b0;
            default:   alu_a = rs1_data;
        endcase
    end

    assign alu_b = alub_src ? imm_out : rs2_data;

    // ADR 027: CSR write data mux — rs1_data vs zimm for immediate forms
    assign csr_wdata = csr_imm ? {27'b0, instruction[19:15]} : rs1_data;

    // ADR 027: Gate csr_wr for CSRRS/CSRRC with rs1 == x0 (read-only per spec)
    // CSRRS = funct3[2:0] == 3'b010, CSRRC = funct3[2:0] == 3'b011
    // For these, if rs1 == 0, the CSR is not written.
    assign csr_wr = csr_wr_raw &
                    ~( (funct3 == 3'b010 || funct3 == 3'b011) &&
                        (rs1_addr == 5'b0) );

    // ADR 027: rd_data mux — adds WB_CSR path, removes hardcoded OP_SYSTEM=0
    always_comb begin
        case (ru_data_wr_src)
            WB_ALU:  rd_data = alu_res;
            WB_MEM:  rd_data = dm_rd_data;
            WB_PC4:  rd_data = pc_plus4;
            WB_CSR:  rd_data = csr_rdata;
            default: rd_data = alu_res;
        endcase
    end

    logic [63:0] cycle_count;
    logic [63:0] instr_retired;
    logic        program_done;

// synthesis translate_off
`ifndef SYNTHESIS
    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, top_single_cycle);
    end
`endif
// synthesis translate_on

    perf_counters #(
        .PIPELINE_MODE (1'b0)
    ) u_perf (
        .clk          (clk),
        .rst_n        (rst_n),
        .div_busy     (div_busy),
        .valid_wb     (1'b0),
        .cycle_count  (cycle_count),
        .instr_retired(instr_retired)
    );

    pc u_pc (
        .clk         (clk),
        .rst_n       (rst_n),
        .branch      (branch),
        .mask_pc_lsb (mask_pc_lsb),
        .alu_res     (alu_res),
        .div_busy    (div_busy),
        .trap_entry  (trap_entry),
        .mret_exec   (mret_exec),
        .trap_target (trap_target),
        .mepc_value  (mepc_value),
        .pc          (pc),
        .pc_plus4    (pc_plus4)
    );

    instruction_memory #(
        .IMEM_DEPTH (IMEM_DEPTH)
    ) u_imem (
        .addr        (pc),
        .instruction (instruction)
    );

    control_unit u_cu (
        .opcode         (opcode),
        .funct3         (funct3),
        .funct7         (funct7),
        .instr_31_20    (instr_31_20),
        .ru_wr          (ru_wr),
        .imm_src        (imm_src),
        .alua_src       (alua_src),
        .alub_src       (alub_src),
        .alu_op         (alu_op),
        .br_op          (br_op),
        .dm_wr          (dm_wr),
        .dm_ctrl        (dm_ctrl),
        .ru_data_wr_src (ru_data_wr_src),
        .trap_entry     (trap_entry),
        .mret_exec      (mret_exec),
        .csr_addr       (csr_addr),
        .csr_wr         (csr_wr_raw),
        .csr_op         (csr_op),
        .csr_imm        (csr_imm)
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
        .DMEM_DEPTH (DMEM_DEPTH)
    ) u_dmem (
        .clk     (clk),
        .addr    (alu_res),
        .wr_data (rs2_data),
        .dm_wr   (dm_wr),
        .dm_ctrl (dm_ctrl),
        .rd_data (dm_rd_data)
    );

    // ADR 027: CSR register file with trap logic
    csr_file u_csr (
        .clk         (clk),
        .rst_n       (rst_n),
        .csr_addr    (csr_addr),
        .csr_wdata   (csr_wdata),
        .csr_wr      (csr_wr),
        .csr_op      (csr_op),
        .csr_rdata   (csr_rdata),
        .trap_entry  (trap_entry),
        .trap_pc4    (pc_plus4),
        .mret_exec   (mret_exec),
        .trap_target (trap_target),
        .mepc_value  (mepc_value)
    );

    seven_segment u_seven_seg0 (
        .val     (instruction[3:0]), // Display opcode[3:0] on 7-segment
        .display (seven_seg_display0)
    );

    seven_segment u_seven_seg1 (
        .val     (instruction[7:4]), 
        .display (seven_seg_display1)
    );

    seven_segment u_seven_seg2 (
        .val     (instruction[11:8]),
        .display (seven_seg_display2)
    );

    seven_segment u_seven_seg3 (
        .val     (instruction[15:12]),
        .display (seven_seg_display3)
    );

    seven_segment u_seven_seg4 (
        .val     (instruction[19:16]),
        .display (seven_seg_display4)
    );

    seven_segment u_seven_seg5 (
        .val     (instruction[23:20]),
        .display (seven_seg_display5)
    );


endmodule
