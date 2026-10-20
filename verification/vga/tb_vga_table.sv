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

module tb_vga_table;

    // The depth of the data memory the table reads.
    localparam int DEPTH = 512;
    // The rows of the table and the characters of one row.
    localparam int ROWS = 32;
    localparam int ROW_BYTES = 14;

    // Only the opcode of these instructions matters to the writer.
    localparam logic [31:0] INSTR_LOAD  = 32'h0000A083;  // lw   x1, 0(x1)
    localparam logic [31:0] INSTR_STORE = 32'h0010A023;  // sw   x1, 0(x1)
    localparam logic [31:0] INSTR_ALU   = 32'h00400093;  // addi x1, x0, 4

    logic clk = 1'b0;
    logic rst_n = 1'b0;

    logic [31:0] dm_addr = 32'd0;
    logic [31:0] mem_instruction = INSTR_LOAD;

    logic [31:0] imem_rd_addr;
    logic [31:0] imem_rd_data = 32'd0;
    logic [31:0] dmem_rd_addr;
    logic [31:0] dmem_rd_data = 32'd0;

    logic        vmem_wr_en;
    logic [12:0] vmem_wr_addr;
    logic [15:0] vmem_wr_data;

    // The screen the writer paints.
    logic [7:0] cell_char [0:7199];
    logic [7:0] cell_attr [0:7199];

    // The number of finished sweeps of the table.
    integer boundary_count = 0;
    integer errors = 0;
    integer i;

    // The last character of the last row of the table.
    logic [12:0] last_cell;

    always #1 clk = ~clk;

    // The fake shadow: it answers with the word address it is asked for,
    // so the expected character of every row is known.  It registers the
    // answer, like the real shadow does.
    always_ff @(posedge clk) begin
        dmem_rd_data <= dmem_rd_addr >> 2;
    end

    // Collect the characters the writer paints and count the sweeps of the
    // table: the sweep ends with the last character of the last row.
    always_ff @(posedge clk) begin
        if (rst_n && vmem_wr_en) begin
            cell_char[vmem_wr_addr] = vmem_wr_data[7:0];
            cell_attr[vmem_wr_addr] = vmem_wr_data[15:8];
            if (vmem_wr_addr == last_cell)
                boundary_count = boundary_count + 1;
        end
    end

    // The last character of the last row of the table.
    initial begin
        last_cell = u_dut.TBL_DATA_MEMORY_ROW0
                    + (ROWS - 1) * u_dut.TBL_DATA_MEMORY_STRIDE
                    + (ROW_BYTES - 1);
    end

    function automatic [7:0] hex_char(input logic [3:0] nibble);
        hex_char = (nibble < 4'd10) ? (8'd48 + nibble) : (8'd55 + nibble);
    endfunction

    // Wait for whole sweeps of the table.  The window moves at the sweep
    // boundary, so the sweep after the change shows the new window.
    task automatic wait_sweeps(input int sweeps);
        integer target;
        begin
            target = boundary_count + sweeps;
            while (boundary_count < target)
                @(negedge clk);
        end
    endtask

    // Check the whole table: the address column shows the byte address of
    // the window base plus the row offset, the data column shows the word
    // and the row of the access is marked with '>'.
    task automatic check_window(input int base, input int marked,
                                input bit is_write);
        integer r;
        integer c;
        integer word;
        integer addr;
        logic [7:0] expected_char;
        logic [7:0] expected_attr;
        begin
            for (r = 0; r < ROWS; r = r + 1) begin
                word = base + r;
                for (c = 0; c < ROW_BYTES; c = c + 1) begin
                    addr = u_dut.TBL_DATA_MEMORY_ROW0
                           + r * u_dut.TBL_DATA_MEMORY_STRIDE + c;
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
                    if (cell_char[addr] !== expected_char) begin
                        if (errors == 0) begin
                            $display("FAIL: row %0d col %0d shows %h, expected %h",
                                     r, c, cell_char[addr], expected_char);
                        end
                        errors = errors + 1;
                    end
                    if (cell_attr[addr] !== expected_attr) begin
                        if (errors == 0) begin
                            $display("FAIL: row %0d col %0d has the attribute %h, expected %h",
                                     r, c, cell_attr[addr], expected_attr);
                        end
                        errors = errors + 1;
                    end
                end
            end
        end
    endtask

    screen_writer_pipeline #(
        .DMEM_DEPTH (DEPTH)
    ) u_dut (
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
        .mem_instruction(mem_instruction), .mem_rs1_data(32'd0),
        .mem_rs2_data(32'd0), .next_pc(32'd0), .opcode(7'd0), .pc(32'd0),
        .rd_addr(5'd0), .rs1_addr(5'd0), .rs1_data(32'd0), .rs2_addr(5'd0),
        .rs2_data(32'd0), .ru_data_wr_src(2'd0), .ru_wr(1'b0), .stall(1'b0),
        .trap_flush(1'b0), .wb_instruction(32'd0), .wb_rd_addr(5'd0),
        .wb_rd_data(32'd0), .reg_values(1024'd0),
        .imem_rd_addr(imem_rd_addr), .imem_rd_data(imem_rd_data),
        .dmem_rd_addr(dmem_rd_addr), .dmem_rd_data(dmem_rd_data),
        .vmem_wr_en(vmem_wr_en),
        .vmem_wr_addr(vmem_wr_addr),
        .vmem_wr_data(vmem_wr_data)
    );

    initial begin
        for (i = 0; i < 7200; i = i + 1) begin
            cell_char[i] = 8'h00;
            cell_attr[i] = 8'h00;
        end

        repeat (4) @(posedge clk);
        rst_n = 1'b1;

        // A load at word 5: the window clamps at the bottom of the
        // memory, so the table starts at word 0.
        dm_addr = 32'd20;
        mem_instruction = INSTR_LOAD;
        wait_sweeps(3);
        check_window(0, 5, 1'b0);

        // A store at word 100: the window follows it and the marked row
        // is painted as a write.
        dm_addr = 32'd400;
        mem_instruction = INSTR_STORE;
        wait_sweeps(3);
        check_window(84, 100, 1'b1);

        // An arithmetic instruction: the window stays where the last
        // access left it, the address of an arithmetic instruction is
        // meaningless.
        dm_addr = 32'hDEADBEEF;
        mem_instruction = INSTR_ALU;
        wait_sweeps(3);
        check_window(84, 100, 1'b1);

        // A load at the last word: the window clamps at the top of the
        // memory.
        dm_addr = 32'd2044;
        mem_instruction = INSTR_LOAD;
        wait_sweeps(3);
        check_window(DEPTH - ROWS, DEPTH - 1, 1'b0);

        // A load in the middle of the memory.
        dm_addr = 32'd80;
        mem_instruction = INSTR_LOAD;
        wait_sweeps(3);
        check_window(4, 20, 1'b0);

        $display("sweeps of the table: %0d", boundary_count);
        if (errors == 0) begin
            $display("PASS: the data memory table is a live window");
        end else begin
            $display("FAIL: %0d mismatches", errors);
        end
        $finish;
    end

endmodule
