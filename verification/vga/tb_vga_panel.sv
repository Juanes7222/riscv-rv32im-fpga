// Check of the decoding panel.
//
// The panel shows the instruction in flight, decoded: the instruction word,
// the mnemonic, the register numbers and the immediate.  The test drives
// the instruction of both writers and checks the characters and the
// colours the panel paints.
//
// The panel is a group of its own: it paints one character per cycle, so
// the test waits for whole sweeps of the panel before it looks at the
// screen.  The panel captures the instruction at its sweep boundary, so
// the test waits for a few sweeps before it checks the panel.
//
// Both designs are checked: the pipeline writer decodes the instruction
// of its EX stage, the single-cycle writer the instruction it executes.
// The panels sit in a different place on the two screens, so the expected
// places are hardcoded from the template and not taken from the writer
// under test.

module tb_vga_panel;

    // The width of the text screen: the panel covers whole rows.
    localparam int SCREEN_W = 160;

    // The lines of the panel and the characters of one line.
    localparam int PANEL_LINES = 4;
    localparam int PANEL_CHARS = 24;
    // The bits of the whole panel.
    localparam int PANEL_BITS = 8 * PANEL_LINES * PANEL_CHARS;

    // The place of the panel on the two screens, read from the template:
    // the pipeline console shows it at row 37, the single-cycle console
    // at row 36.
    localparam int PIPE_ROW0 = 37 * SCREEN_W;
    localparam int SC_ROW0   = 36 * SCREEN_W + 83;

    // The cycles a panel may take to sweep.  A sweep is 96 characters and
    // the writer paints one character every few cycles, so this is
    // generous; it only stops a panel that never sweeps from hanging the
    // test.
    localparam int SWEEP_GUARD = 30000;

    localparam int DUT_PIPE = 0;
    localparam int DUT_SC   = 1;

    // The panels the test expects, one per instruction it drives.  The
    // register numbers are the fields of the instruction word, so the
    // fields an instruction does not use show the bits of the immediate.
    // The formats without rs2 (I, B, U and J) show a placeholder instead:
    // the bits of the instruction would be immediate bits, not a register
    // number.  The R format and the S format carry a real rs2.  The same
    // holds for rd (the B and the S formats have none) and for rs1 (the U
    // and the J formats have none).

    // addi x5, x1, 4: the encoding of the task brief.  It decodes to x5
    // and x1, not to the x1 and x2 the brief names.
    localparam [PANEL_BITS-1:0] EXP_ADDI_X1 = {
        "INSTR 00408293          ",
        "MNEM  ADDI              ",
        "rd=05 rs1=01 rs2=--     ",
        "imm=00000004            "};

    // add x6, x1, x2
    localparam [PANEL_BITS-1:0] EXP_ADD = {
        "INSTR 00208333          ",
        "MNEM  ADD               ",
        "rd=06 rs1=01 rs2=02     ",
        "imm=00000000            "};

    // addi x1, x2, 4
    localparam [PANEL_BITS-1:0] EXP_ADDI_X2 = {
        "INSTR 00410093          ",
        "MNEM  ADDI              ",
        "rd=01 rs1=02 rs2=--     ",
        "imm=00000004            "};

    // lw x1, 0(x1)
    localparam [PANEL_BITS-1:0] EXP_LW = {
        "INSTR 0000A083          ",
        "MNEM  LW                ",
        "rd=01 rs1=01 rs2=--     ",
        "imm=00000000            "};

    // beq x1, x2, 8: the B format has no rd.
    localparam [PANEL_BITS-1:0] EXP_BEQ = {
        "INSTR 00208463          ",
        "MNEM  BEQ               ",
        "rd=-- rs1=01 rs2=--     ",
        "imm=00000008            "};

    // mul x7, x3, x4: the M extension of this core is OP with
    // funct7 = 0000001.
    localparam [PANEL_BITS-1:0] EXP_MUL = {
        "INSTR 024183B3          ",
        "MNEM  MUL               ",
        "rd=07 rs1=03 rs2=04     ",
        "imm=00000000            "};

    // div x8, x5, x6
    localparam [PANEL_BITS-1:0] EXP_DIV = {
        "INSTR 0262C433          ",
        "MNEM  DIV               ",
        "rd=08 rs1=05 rs2=06     ",
        "imm=00000000            "};

    // sra x9, x7, x8: the shift to the right is SRA when funct7[5] is
    // set, SRL otherwise.
    localparam [PANEL_BITS-1:0] EXP_SRA = {
        "INSTR 4083D4B3          ",
        "MNEM  SRA               ",
        "rd=09 rs1=07 rs2=08     ",
        "imm=00000000            "};

    // srai x10, x3, 4: the immediate field of a shift immediate holds
    // the funct7 of the instruction, so the panel shows the shamt alone.
    localparam [PANEL_BITS-1:0] EXP_SRAI = {
        "INSTR 4041D513          ",
        "MNEM  SRAI              ",
        "rd=10 rs1=03 rs2=--     ",
        "imm=00000004            "};

    // sub x6, x1, x2: the subtraction is the operation with funct7[5] set.
    localparam [PANEL_BITS-1:0] EXP_SUB = {
        "INSTR 40208333          ",
        "MNEM  SUB               ",
        "rd=06 rs1=01 rs2=02     ",
        "imm=00000000            "};

    // lui x5, 4: the U format has no rs1.
    localparam [PANEL_BITS-1:0] EXP_LUI = {
        "INSTR 000042B7          ",
        "MNEM  LUI               ",
        "rd=05 rs1=-- rs2=--     ",
        "imm=00000004            "};

    // jal x1, 16: the J format has no rs1.
    localparam [PANEL_BITS-1:0] EXP_JAL = {
        "INSTR 010000EF          ",
        "MNEM  JAL               ",
        "rd=01 rs1=-- rs2=--     ",
        "imm=00000010            "};

    // sb x2, 8(x1): the S format carries an rs2, the source register of
    // the stored word, but no rd.
    localparam [PANEL_BITS-1:0] EXP_SB = {
        "INSTR 00208423          ",
        "MNEM  SB                ",
        "rd=-- rs1=01 rs2=02     ",
        "imm=00000008            "};

    logic clk = 1'b0;
    logic rst_n = 1'b0;

    // The instruction in flight of the two designs.
    logic [31:0] pipe_ex_instruction = 32'd0;
    logic [31:0] sc_instruction = 32'd0;

    // The memory window of the pipeline writer.
    logic [31:0] pipe_imem_rd_addr;
    logic [31:0] pipe_imem_rd_data = 32'd0;
    logic [31:0] pipe_dmem_rd_addr;
    logic [31:0] pipe_dmem_rd_data = 32'd0;
    logic        pipe_wr_en;
    logic [12:0] pipe_wr_addr;
    logic [15:0] pipe_wr_data;

    // The memory window of the single-cycle writer.
    logic [31:0] sc_imem_rd_addr;
    logic [31:0] sc_imem_rd_data = 32'd0;
    logic [31:0] sc_dmem_rd_addr;
    logic [31:0] sc_dmem_rd_data = 32'd0;
    logic        sc_wr_en;
    logic [12:0] sc_wr_addr;
    logic [15:0] sc_wr_data;

    // The screens the writers paint.
    logic [7:0] pipe_char [0:7199];
    logic [7:0] pipe_attr [0:7199];
    logic [7:0] sc_char [0:7199];
    logic [7:0] sc_attr [0:7199];

    // The number of finished sweeps of the panel, per writer.
    integer sweeps [0:1];

    // The last character of the last line of the panel, per writer.
    logic [12:0] pipe_last_cell;
    logic [12:0] sc_last_cell;

    integer errors = 0;
    integer i;

    always #1 clk = ~clk;

    initial begin
        pipe_last_cell = PIPE_ROW0 + (PANEL_LINES - 1) * SCREEN_W
                        + (PANEL_CHARS - 1);
        sc_last_cell   = SC_ROW0   + (PANEL_LINES - 1) * SCREEN_W
                        + (PANEL_CHARS - 1);
    end

    // Collect the characters the writers paint and count the sweeps of the
    // panel: a sweep ends with the last character of the last line.
    always_ff @(posedge clk) begin
        if (rst_n && pipe_wr_en) begin
            pipe_char[pipe_wr_addr] = pipe_wr_data[7:0];
            pipe_attr[pipe_wr_addr] = pipe_wr_data[15:8];
            if (pipe_wr_addr == pipe_last_cell)
                sweeps[DUT_PIPE] = sweeps[DUT_PIPE] + 1;
        end
        if (rst_n && sc_wr_en) begin
            sc_char[sc_wr_addr] = sc_wr_data[7:0];
            sc_attr[sc_wr_addr] = sc_wr_data[15:8];
            if (sc_wr_addr == sc_last_cell)
                sweeps[DUT_SC] = sweeps[DUT_SC] + 1;
        end
    end

    function automatic int panel_row0(input int dut);
        panel_row0 = (dut == DUT_PIPE) ? PIPE_ROW0 : SC_ROW0;
    endfunction

    // The character the panel shows at (line, column).
    function automatic [7:0] expected_char(input [PANEL_BITS-1:0] expected,
                                            input int line, input int col);
        integer index;
        begin
            index = line * PANEL_CHARS + col;
            expected_char = (expected >> (PANEL_BITS - 8*(index + 1)))
                            & 8'hFF;
        end
    endfunction

    // The colour the panel gives to a cell: the labels wear the body
    // colour, every value the colour of its kind.
    function automatic [7:0] expected_attr(input int line, input int col);
        begin
            case (line)
                0: expected_attr = (col >= 6 && col < 14) ? 8'h08 : 8'h09;
                1: expected_attr = (col >= 6 && col < 12) ? 8'h0F : 8'h09;
                2: expected_attr = ((col >= 3 && col < 5) ||
                                    (col >= 10 && col < 12) ||
                                    (col >= 17 && col < 19)) ? 8'h0D : 8'h09;
                3: expected_attr = (col >= 4 && col < 12) ? 8'h0C : 8'h09;
                default: expected_attr = 8'h09;
            endcase
        end
    endfunction

    // Wait for whole sweeps of the panel of both writers.  The panel
    // captures the instruction at its sweep boundary, so the sweep after
    // the change shows the new instruction.  The wait is bounded: a panel
    // that never sweeps is a failure, not a hang.
    task automatic wait_sweeps(input int sweeps_wanted);
        integer pipe_target;
        integer sc_target;
        integer guard;
        begin
            pipe_target = sweeps[DUT_PIPE] + sweeps_wanted;
            sc_target = sweeps[DUT_SC] + sweeps_wanted;
            guard = 0;
            while ((sweeps[DUT_PIPE] < pipe_target ||
                    sweeps[DUT_SC] < sc_target) &&
                   guard < SWEEP_GUARD) begin
                guard = guard + 1;
                @(negedge clk);
            end
            if (guard >= SWEEP_GUARD) begin
                $display("FAIL: the decoding panel did not sweep %0d times",
                         sweeps_wanted);
                errors = errors + 1;
            end
        end
    endtask

    // Check the whole panel: the characters of the four lines and their
    // colours.
    task automatic check_panel(input int dut,
                               input [PANEL_BITS-1:0] expected);
        integer l;
        integer c;
        integer addr;
        logic [7:0] got_char;
        logic [7:0] got_attr;
        begin
            for (l = 0; l < PANEL_LINES; l = l + 1) begin
                for (c = 0; c < PANEL_CHARS; c = c + 1) begin
                    addr = panel_row0(dut) + l * SCREEN_W + c;
                    if (dut == DUT_PIPE) begin
                        got_char = pipe_char[addr];
                        got_attr = pipe_attr[addr];
                    end else begin
                        got_char = sc_char[addr];
                        got_attr = sc_attr[addr];
                    end
                    if (got_char !== expected_char(expected, l, c)) begin
                        if (errors == 0)
                            $display("FAIL: design %0d line %0d col %0d shows %h, expected %h",
                                     dut, l, c, got_char,
                                     expected_char(expected, l, c));
                        errors = errors + 1;
                    end
                    if (got_attr !== expected_attr(l, c)) begin
                        if (errors == 0)
                            $display("FAIL: design %0d line %0d col %0d has the attribute %h, expected %h",
                                     dut, l, c, got_attr, expected_attr(l, c));
                        errors = errors + 1;
                    end
                end
            end
        end
    endtask

    // Drive an instruction and check the panel of both designs.
    task automatic run_phase(input logic [31:0] instruction,
                             input [PANEL_BITS-1:0] expected);
        begin
            pipe_ex_instruction = instruction;
            sc_instruction = instruction;
            wait_sweeps(4);
            check_panel(DUT_PIPE, expected);
            check_panel(DUT_SC, expected);
        end
    endtask

    screen_writer_pipeline #(
        .DMEM_DEPTH (512),
        .IMEM_DEPTH (2048)
    ) u_pipe (
        .clk(clk),
        .rst_n(rst_n),
        .alu_a(32'd0), .alu_b(32'd0), .alu_op(5'd0), .alu_res(32'd0),
        .alua_src(2'd0), .alub_src(1'b0), .br_op(5'd0), .branch(1'b0),
        .branch_flush(1'b0), .cycles_at_done(64'd0), .data_wr(32'd0),
        .dm_addr(32'd0), .dm_ctrl(3'd0), .dm_rdata(32'd0), .dm_wdata(32'd0),
        .dm_wr(1'b0), .ex_alu_result(32'd0), .ex_branch_taken(1'b0),
        .ex_imm(32'd0), .ex_instruction(pipe_ex_instruction), .ex_pc(32'd0),
        .ex_rs1_data(32'd0), .ex_rs2_data(32'd0), .flush(1'b0), .funct3(3'd0),
        .funct7(7'd0), .id_instruction(32'd0), .id_pc(32'd0),
        .if_instruction(32'd0), .if_pc(32'd0), .imm_out(32'd0), .imm_src(3'd0),
        .instr_at_done(64'd0), .instr_retired(64'd0), .instruction(32'd0),
        .load_use_hazard(1'b0), .mem_alu_result(32'd0),
        .mem_instruction(32'd0), .mem_rs1_data(32'd0),
        .mem_rs2_data(32'd0), .next_pc(32'd0), .opcode(7'd0), .pc(32'd0),
        .rd_addr(5'd0), .rs1_addr(5'd0), .rs1_data(32'd0), .rs2_addr(5'd0),
        .rs2_data(32'd0), .ru_data_wr_src(2'd0), .ru_wr(1'b0), .stall(1'b0),
        .trap_flush(1'b0), .wb_instruction(32'd0), .wb_rd_addr(5'd0),
        .wb_rd_data(32'd0), .reg_values(1024'd0),
        .imem_rd_addr(pipe_imem_rd_addr), .imem_rd_data(pipe_imem_rd_data),
        .dmem_rd_addr(pipe_dmem_rd_addr), .dmem_rd_data(pipe_dmem_rd_data),
        .vmem_wr_en(pipe_wr_en),
        .vmem_wr_addr(pipe_wr_addr),
        .vmem_wr_data(pipe_wr_data)
    );

    screen_writer_single_cycle #(
        .DMEM_DEPTH (512),
        .IMEM_DEPTH (2048)
    ) u_sc (
        .clk(clk),
        .rst_n(rst_n),
        .alu_a(32'd0), .alu_b(32'd0), .alu_op(5'd0), .alu_res(32'd0),
        .alua_src(2'd0), .alub_src(1'b0), .br_op(5'd0), .branch(1'b0),
        .cycle_count(64'd0), .cycles_at_done(64'd0), .data_wr(32'd0),
        .dm_addr(32'd0), .dm_ctrl(3'd0), .dm_rdata(32'd0), .dm_wdata(32'd0),
        .dm_wr(1'b0), .funct3(3'd0), .funct7(7'd0), .halted(1'b0),
        .imm_out(32'd0), .imm_src(3'd0), .instr_at_done(64'd0),
        .instruction(sc_instruction), .next_pc(32'd0), .opcode(7'd0),
        .pc(32'd0),
        .rd_addr(5'd0), .rs1_addr(5'd0), .rs1_data(32'd0), .rs2_addr(5'd0),
        .rs2_data(32'd0), .ru_data_wr_src(2'd0), .ru_wr(1'b0),
        .reg_values(1024'd0),
        .imem_rd_addr(sc_imem_rd_addr), .imem_rd_data(sc_imem_rd_data),
        .dmem_rd_addr(sc_dmem_rd_addr), .dmem_rd_data(sc_dmem_rd_data),
        .vmem_wr_en(sc_wr_en),
        .vmem_wr_addr(sc_wr_addr),
        .vmem_wr_data(sc_wr_data)
    );

    initial begin
        for (i = 0; i < 7200; i = i + 1) begin
            pipe_char[i] = 8'h00;
            pipe_attr[i] = 8'h00;
            sc_char[i] = 8'h00;
            sc_attr[i] = 8'h00;
        end
        sweeps[DUT_PIPE] = 0;
        sweeps[DUT_SC] = 0;

        repeat (4) @(posedge clk);
        rst_n = 1'b1;

        // The instruction in flight is decoded: the word, the mnemonic,
        // the register numbers and the immediate.
        run_phase(32'h00408293, EXP_ADDI_X1);
        run_phase(32'h00208333, EXP_ADD);
        run_phase(32'h00410093, EXP_ADDI_X2);
        run_phase(32'h0000A083, EXP_LW);
        run_phase(32'h00208463, EXP_BEQ);
        run_phase(32'h024183B3, EXP_MUL);
        run_phase(32'h0262C433, EXP_DIV);
        run_phase(32'h4083D4B3, EXP_SRA);
        run_phase(32'h4041D513, EXP_SRAI);
        run_phase(32'h40208333, EXP_SUB);
        run_phase(32'h000042B7, EXP_LUI);
        run_phase(32'h010000EF, EXP_JAL);
        run_phase(32'h00208423, EXP_SB);

        $display("sweeps of the panel: %0d pipeline, %0d single-cycle",
                 sweeps[DUT_PIPE], sweeps[DUT_SC]);
        if (errors == 0) begin
            $display("PASS: the decoding panel shows the instruction in flight");
        end else begin
            $display("FAIL: %0d mismatches", errors);
        end
        $finish;
    end

endmodule
