// Check of the live data memory table.
//
// The data memory table is a window over the data memory: it follows the
// last load or store, so the address column shows the real addresses of
// the 32 words on screen and the row of the access carries a '>'.
//
// The test drives the memory window of the writer directly: the data
// input answers with the word address it is asked for, so the expected
// character of every row is known.  The writer is a round-robin that
// paints one character per cycle, so the test waits for whole sweeps of
// the table before it looks at the screen.
//
// Both designs are checked: the pipeline writer takes the access from the
// instruction in the MEM stage, the single-cycle writer from the
// instruction it executes.  The table sits in a different place on the two
// screens, so the expected addresses are hardcoded from the template and
// not taken from the writer under test.

module tb_vga_table;

    // The depth of the data memory the table reads.
    localparam int DEPTH = 512;
    // The rows of the table and the characters of one row.
    localparam int ROWS = 32;
    localparam int ROW_BYTES = 14;
    // The width of the text screen: the rows of a table are screen rows.
    localparam int SCREEN_W = 160;

    // The place of the table on the two screens, read from the template:
    // the pipeline console shows it at row 9, the single-cycle console at
    // row 12, and the address column comes right behind the border.
    localparam int PIPE_ROW0 = 9 * SCREEN_W + 118;
    localparam int SC_ROW0   = 12 * SCREEN_W + 32;

    localparam int DUT_PIPE = 0;
    localparam int DUT_SC   = 1;

    // Only the opcode of these instructions matters to the writer.
    localparam logic [31:0] INSTR_LOAD  = 32'h0000A083;  // lw   x1, 0(x1)
    localparam logic [31:0] INSTR_STORE = 32'h0010A023;  // sw   x1, 0(x1)
    localparam logic [31:0] INSTR_ALU   = 32'h00400093;  // addi x1, x0, 4

    logic clk = 1'b0;
    logic rst_n = 1'b0;

    // The access the table follows: the address and the instruction.
    logic [31:0] dm_addr = 32'd0;
    logic [31:0] instr = INSTR_ALU;

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

    // The number of finished sweeps of the table, per writer.
    integer boundary_count [0:1];
    // The number of mismatches reported per writer.
    integer reported [0:1];

    // The last character of the last row of the table, from the geometry
    // of the template.
    logic [12:0] pipe_last_cell;
    logic [12:0] sc_last_cell;

    integer errors = 0;
    integer i;

    always #1 clk = ~clk;

    initial begin
        pipe_last_cell = PIPE_ROW0 + (ROWS - 1) * SCREEN_W + (ROW_BYTES - 1);
        sc_last_cell   = SC_ROW0   + (ROWS - 1) * SCREEN_W + (ROW_BYTES - 1);
    end

    // The fake shadows: they answer with the word address they are asked
    // for, so the expected character of every row is known.  They register
    // the answer, like the real shadows do.
    always_ff @(posedge clk) begin
        pipe_dmem_rd_data <= pipe_dmem_rd_addr >> 2;
        sc_dmem_rd_data <= sc_dmem_rd_addr >> 2;
    end

    // Collect the characters the writers paint and count the sweeps of the
    // tables: a sweep ends with the last character of the last row.
    always_ff @(posedge clk) begin
        if (rst_n && pipe_wr_en) begin
            pipe_char[pipe_wr_addr] = pipe_wr_data[7:0];
            pipe_attr[pipe_wr_addr] = pipe_wr_data[15:8];
            if (pipe_wr_addr == pipe_last_cell)
                boundary_count[DUT_PIPE] = boundary_count[DUT_PIPE] + 1;
        end
        if (rst_n && sc_wr_en) begin
            sc_char[sc_wr_addr] = sc_wr_data[7:0];
            sc_attr[sc_wr_addr] = sc_wr_data[15:8];
            if (sc_wr_addr == sc_last_cell)
                boundary_count[DUT_SC] = boundary_count[DUT_SC] + 1;
        end
    end

    function automatic int table_row0(input int dut);
        table_row0 = (dut == DUT_PIPE) ? PIPE_ROW0 : SC_ROW0;
    endfunction

    function automatic [7:0] hex_char(input logic [3:0] nibble);
        hex_char = (nibble < 4'd10) ? (8'd48 + nibble) : (8'd55 + nibble);
    endfunction

    // Wait for whole sweeps of the tables of both writers.  The window
    // moves at the sweep boundary, so the sweep after the change shows the
    // new window.
    task automatic wait_sweeps(input int sweeps);
        integer pipe_target;
        integer sc_target;
        begin
            pipe_target = boundary_count[DUT_PIPE] + sweeps;
            sc_target = boundary_count[DUT_SC] + sweeps;
            while (boundary_count[DUT_PIPE] < pipe_target ||
                   boundary_count[DUT_SC] < sc_target)
                @(negedge clk);
        end
    endtask

    // Check the whole table: the address column shows the byte address of
    // the window base plus the row offset, the data column shows the word
    // and the row of the access is marked with '>'.  A marked word of -1
    // means that no row is marked.
    task automatic check_window(input int dut, input int base, input int marked,
                                input bit is_write);
        integer r;
        integer c;
        integer word;
        integer addr;
        logic [7:0] expected_char;
        logic [7:0] expected_attr;
        logic [7:0] got_char;
        logic [7:0] got_attr;
        begin
            for (r = 0; r < ROWS; r = r + 1) begin
                word = base + r;
                for (c = 0; c < ROW_BYTES; c = c + 1) begin
                    addr = table_row0(dut) + r * SCREEN_W + c;
                    if (c < 4)
                        expected_char = hex_char(((word * 4) >> ((3 - c) * 4))
                                                 & 4'hF);
                    else if (c == 4)
                        expected_char = 8'h3A;   // ':'
                    else if (c == 5)
                        expected_char = 8'h20;   // ' '
                    else
                        expected_char = hex_char((word >> ((13 - c) * 4))
                                                 & 4'hF);
                    if (c == 0 && word == marked)
                        expected_char = 8'h3E;   // '>'
                    expected_attr = (word == marked)
                                    ? (is_write ? 8'h38 : 8'h28) : 8'h09;
                    if (dut == DUT_PIPE) begin
                        got_char = pipe_char[addr];
                        got_attr = pipe_attr[addr];
                    end else begin
                        got_char = sc_char[addr];
                        got_attr = sc_attr[addr];
                    end
                    if (got_char !== expected_char) begin
                        if (reported[dut] == 0) begin
                            reported[dut] = 1;
                            $display("FAIL: %0d row %0d col %0d shows %h, expected %h",
                                     dut, r, c, got_char, expected_char);
                        end
                        errors = errors + 1;
                    end
                    if (got_attr !== expected_attr) begin
                        if (reported[dut] == 0) begin
                            reported[dut] = 1;
                            $display("FAIL: %0d row %0d col %0d has the attribute %h, expected %h",
                                     dut, r, c, got_attr, expected_attr);
                        end
                        errors = errors + 1;
                    end
                end
            end
        end
    endtask

    // The table of the generated writer has to sit where the template puts
    // it, otherwise it paints over the wrong cells.
    task automatic check_geometry();
        begin
            if (u_pipe.TBL_DATA_MEMORY_ROW0 != PIPE_ROW0) begin
                $display("FAIL: the pipeline table starts at %0d, expected %0d",
                         u_pipe.TBL_DATA_MEMORY_ROW0, PIPE_ROW0);
                errors = errors + 1;
            end
            if (u_sc.TBL_DATA_MEMORY_ROW0 != SC_ROW0) begin
                $display("FAIL: the single-cycle table starts at %0d, expected %0d",
                         u_sc.TBL_DATA_MEMORY_ROW0, SC_ROW0);
                errors = errors + 1;
            end
        end
    endtask

    // Wait for the tables to show the window and check it in both designs.
    task automatic run_phase(input int base, input int marked,
                             input bit is_write);
        begin
            wait_sweeps(3);
            check_window(DUT_PIPE, base, marked, is_write);
            check_window(DUT_SC, base, marked, is_write);
        end
    endtask

    screen_writer_pipeline #(
        .DMEM_DEPTH (DEPTH)
    ) u_pipe (
        .clk(clk),
        .rst_n(rst_n),
        .alu_a(32'd0), .alu_b(32'd0), .alu_op(5'd0), .alu_res(32'd0),
        .alua_src(2'd0), .alub_src(1'b0), .br_op(5'd0), .branch(1'b0),
        .branch_flush(1'b0), .cycles_at_done(64'd0), .data_wr(32'd0),
        .dm_addr(dm_addr), .dm_ctrl(3'd0), .dm_rdata(32'd0), .dm_wdata(32'd0),
        .dm_wr(1'b0), .ex_alu_result(32'd0), .ex_branch_taken(1'b0),
        .ex_imm(32'd0), .ex_instruction(32'd0), .ex_pc(32'd0),
        .ex_rs1_data(32'd0), .ex_rs2_data(32'd0), .flush(1'b0), .funct3(3'd0),
        .funct7(7'd0), .id_instruction(32'd0), .id_pc(32'd0),
        .if_instruction(32'd0), .if_pc(32'd0), .imm_out(32'd0), .imm_src(3'd0),
        .instr_at_done(64'd0), .instr_retired(64'd0), .instruction(32'd0),
        .load_use_hazard(1'b0), .mem_alu_result(32'd0),
        .mem_instruction(instr), .mem_rs1_data(32'd0),
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
        .DMEM_DEPTH (DEPTH)
    ) u_sc (
        .clk(clk),
        .rst_n(rst_n),
        .alu_a(32'd0), .alu_b(32'd0), .alu_op(5'd0), .alu_res(32'd0),
        .alua_src(2'd0), .alub_src(1'b0), .br_op(5'd0), .branch(1'b0),
        .cycle_count(64'd0), .cycles_at_done(64'd0), .data_wr(32'd0),
        .dm_addr(dm_addr), .dm_ctrl(3'd0), .dm_rdata(32'd0), .dm_wdata(32'd0),
        .dm_wr(1'b0), .funct3(3'd0), .funct7(7'd0), .halted(1'b0),
        .imm_out(32'd0), .imm_src(3'd0), .instr_at_done(64'd0),
        .instruction(instr), .next_pc(32'd0), .opcode(7'd0), .pc(32'd0),
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
        boundary_count[DUT_PIPE] = 0;
        boundary_count[DUT_SC] = 0;
        reported[DUT_PIPE] = 0;
        reported[DUT_SC] = 0;

        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        check_geometry();

        // Before the first access there is no marked row: the table shows
        // the first words of the memory and no '>'.
        dm_addr = 32'd0;
        instr = INSTR_ALU;
        run_phase(0, -1, 1'b0);

        // A load at word 5: the window clamps at the bottom of the
        // memory, so the table starts at word 0.
        dm_addr = 32'd20;
        instr = INSTR_LOAD;
        run_phase(0, 5, 1'b0);

        // A store at word 100: the window follows it and the marked row
        // is painted as a write.
        dm_addr = 32'd400;
        instr = INSTR_STORE;
        run_phase(84, 100, 1'b1);

        // An arithmetic instruction: the window stays where the last
        // access left it, the address of an arithmetic instruction is
        // meaningless.
        dm_addr = 32'hDEADBEEF;
        instr = INSTR_ALU;
        run_phase(84, 100, 1'b1);

        // A load at the last word: the window clamps at the top of the
        // memory.
        dm_addr = 32'd2044;
        instr = INSTR_LOAD;
        run_phase(DEPTH - ROWS, DEPTH - 1, 1'b0);

        // A store beyond the memory: the memory masks the index to its
        // depth, so the access lands in word 88 and the table marks that
        // word, not the end of the memory.
        dm_addr = 32'd2400;
        instr = INSTR_STORE;
        run_phase(72, 88, 1'b1);

        // A load in the middle of the memory.
        dm_addr = 32'd80;
        instr = INSTR_LOAD;
        run_phase(4, 20, 1'b0);

        $display("sweeps of the table: %0d pipeline, %0d single-cycle",
                 boundary_count[DUT_PIPE], boundary_count[DUT_SC]);
        if (errors == 0) begin
            $display("PASS: the data memory table is a live window");
        end else begin
            $display("FAIL: %0d mismatches", errors);
        end
        $finish;
    end

endmodule
