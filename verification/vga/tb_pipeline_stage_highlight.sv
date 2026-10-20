// Coherence check for the stage highlight of the pipeline screen writer.
//
// Every stage box of the pipeline console and every flow arrow between them
// is a static cell of the template, but its background has to follow the
// stage it belongs to: a stage that holds an instruction is painted with the
// dark navy of the palette, and so is the arrow that leaves it.
//
// Each stage has its own instruction register, so the check drives the five
// registers one after the other: every box has to be painted only while its
// own stage holds an instruction.  The writer derives the state of a stage
// from the snapshot bank, so the check compares the attribute of every write
// against the derived signal of the DUT at that very instant.
//
// The addresses come from the writer itself, so the check follows the
// template instead of hard-coding a layout.

module tb_pipeline_stage_highlight;

    logic clk = 1'b0;
    logic rst_n = 1'b0;

    logic [31:0] if_instruction;
    logic [31:0] id_instruction;
    logic [31:0] ex_instruction;
    logic [31:0] mem_instruction;
    logic [31:0] wb_instruction;

    logic        vmem_wr_en;
    logic [12:0] vmem_wr_addr;
    logic [15:0] vmem_wr_data;

    // The attribute of a cell is {background[7:4], foreground[3:0]}.  The
    // headers keep the colour of the template - red for most of them, blue
    // for the pipeline registers - and the arrows its grey; only the
    // background changes.
    localparam logic [7:0] ATTR_RED_BASE  = 8'h0B;
    localparam logic [7:0] ATTR_RED_HOT   = 8'h1B;
    localparam logic [7:0] ATTR_BLUE_BASE = 8'h0A;
    localparam logic [7:0] ATTR_BLUE_HOT  = 8'h1A;
    localparam logic [7:0] ATTR_ARROW_BASE = 8'h09;
    localparam logic [7:0] ATTR_ARROW_HOT  = 8'h19;

    // The signal that decides whether a cell is painted as active.
    localparam int SEL_IF  = 0;
    localparam int SEL_ID  = 1;
    localparam int SEL_EX  = 2;
    localparam int SEL_MEM = 3;
    localparam int SEL_WB  = 4;

    localparam int N_CELLS = 13;

    logic [12:0] cell_addr [0:N_CELLS-1];
    logic [7:0]  cell_char [0:N_CELLS-1];
    logic [7:0]  cell_base [0:N_CELLS-1];
    logic [7:0]  cell_hot  [0:N_CELLS-1];
    integer      cell_sel  [0:N_CELLS-1];
    integer      hits      [0:N_CELLS-1];
    integer      hot_hits  [0:N_CELLS-1];
    integer      base_hits [0:N_CELLS-1];

    logic [2:0]  state;
    integer      hold;
    integer      errors = 0;
    integer      bad_cell = -1;
    logic [7:0]  bad_char = 8'h00;
    logic [7:0]  bad_attr = 8'h00;
    integer      i;

    always #1 clk = ~clk;

    // One stage after the other holds an instruction, so every box has to be
    // painted in its own phase only.  A phase is held for three sweeps, so the
    // snapshot bank of every group captures it.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= 3'd0;
            hold <= 0;
            if_instruction <= 32'h00000000;
            id_instruction <= 32'h00000000;
            ex_instruction <= 32'h00000000;
            mem_instruction <= 32'h00000000;
            wb_instruction <= 32'h00000000;
        end else if (hold >= 3 * u_dut.N_CHARS) begin
            hold <= 0;
            case (state)
                3'd0: begin
                    state <= 3'd1;
                    // The canonical bubble: no stage holds an instruction.
                    if_instruction <= 32'h00000013;
                    id_instruction <= 32'h00000013;
                    ex_instruction <= 32'h00000013;
                    mem_instruction <= 32'h00000013;
                    wb_instruction <= 32'h00000013;
                end
                3'd1: begin
                    state <= 3'd2;
                    if_instruction <= 32'h00000033;
                    id_instruction <= 32'h00000000;
                    ex_instruction <= 32'h00000000;
                    mem_instruction <= 32'h00000000;
                    wb_instruction <= 32'h00000000;
                end
                3'd2: begin
                    state <= 3'd3;
                    if_instruction <= 32'h00000000;
                    id_instruction <= 32'h00000033;
                    ex_instruction <= 32'h00000000;
                    mem_instruction <= 32'h00000000;
                    wb_instruction <= 32'h00000000;
                end
                3'd3: begin
                    state <= 3'd4;
                    if_instruction <= 32'h00000000;
                    id_instruction <= 32'h00000000;
                    ex_instruction <= 32'h00000033;
                    mem_instruction <= 32'h00000000;
                    wb_instruction <= 32'h00000000;
                end
                3'd4: begin
                    state <= 3'd5;
                    if_instruction <= 32'h00000000;
                    id_instruction <= 32'h00000000;
                    ex_instruction <= 32'h00000000;
                    mem_instruction <= 32'h00000033;
                    wb_instruction <= 32'h00000000;
                end
                3'd5: begin
                    state <= 3'd6;
                    if_instruction <= 32'h00000000;
                    id_instruction <= 32'h00000000;
                    ex_instruction <= 32'h00000000;
                    mem_instruction <= 32'h00000000;
                    wb_instruction <= 32'h00000033;
                end
                default: begin
                    state <= 3'd0;
                    if_instruction <= 32'h00000000;
                    id_instruction <= 32'h00000000;
                    ex_instruction <= 32'h00000000;
                    mem_instruction <= 32'h00000000;
                    wb_instruction <= 32'h00000000;
                end
            endcase
        end else begin
            hold <= hold + 1;
        end
    end

    // Every write to a monitored cell has to carry the character of the
    // template and the attribute of the stage the cell belongs to.
    always_ff @(posedge clk) begin
        if (rst_n && vmem_wr_en) begin
            for (int k = 0; k < N_CELLS; k = k + 1) begin
                if (vmem_wr_addr == cell_addr[k]) begin
                    logic hot_now;
                    case (cell_sel[k])
                        SEL_IF:  hot_now = u_dut.stage_if_active;
                        SEL_ID:  hot_now = u_dut.stage_id_active;
                        SEL_EX:  hot_now = u_dut.stage_ex_active;
                        SEL_MEM: hot_now = u_dut.stage_mem_active;
                        default: hot_now = u_dut.stage_wb_active;
                    endcase
                    hits[k] = hits[k] + 1;
                    if (hot_now) begin
                        hot_hits[k] = hot_hits[k] + 1;
                    end else begin
                        base_hits[k] = base_hits[k] + 1;
                    end
                    if (vmem_wr_data[7:0] !== cell_char[k]) begin
                        errors = errors + 1;
                        if (bad_cell < 0) begin
                            bad_cell = i;
                            bad_char = vmem_wr_data[7:0];
                            bad_attr = vmem_wr_data[15:8];
                        end
                    end
                    if (vmem_wr_data[15:8] !==
                        (hot_now ? cell_hot[k] : cell_base[k])) begin
                        errors = errors + 1;
                        if (bad_cell < 0) begin
                            bad_cell = i;
                            bad_char = vmem_wr_data[7:0];
                            bad_attr = vmem_wr_data[15:8];
                        end
                    end
                end
            end
        end
    end

    screen_writer_pipeline u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .if_instruction(if_instruction),
        .id_instruction(id_instruction),
        .ex_instruction(ex_instruction),
        .mem_instruction(mem_instruction),
        .wb_instruction(wb_instruction),
        .reg_values(1024'd0),
        .alu_a(32'd0), .alu_b(32'd0), .alu_op(5'd0), .alu_res(32'd0),
        .alua_src(2'd0), .alub_src(1'b0), .br_op(5'd0), .branch(1'b0),
        .branch_flush(1'b0), .cycles_at_done(64'd0), .data_wr(32'd0),
        .dm_addr(32'd0), .dm_ctrl(3'd0), .dm_rdata(32'd0), .dm_wdata(32'd0),
        .dm_wr(1'b0), .ex_alu_result(32'd0), .ex_branch_taken(1'b0),
        .ex_imm(32'd0), .ex_pc(32'd0), .ex_rs1_data(32'd0), .ex_rs2_data(32'd0),
        .flush(1'b0), .funct3(3'd0), .funct7(7'd0), .id_pc(32'd0),
        .if_pc(32'd0), .imm_out(32'd0), .imm_src(3'd0), .instr_at_done(64'd0),
        .instr_retired(64'd0), .instruction(32'd0), .load_use_hazard(1'b0),
        .mem_alu_result(32'd0), .mem_rs1_data(32'd0), .mem_rs2_data(32'd0),
        .next_pc(32'd0), .opcode(7'd0), .pc(32'd0), .rd_addr(5'd0),
        .rs1_addr(5'd0), .rs1_data(32'd0), .rs2_addr(5'd0), .rs2_data(32'd0),
        .ru_data_wr_src(2'd0), .ru_wr(1'b0), .stall(1'b0), .trap_flush(1'b0),
        .wb_rd_addr(5'd0), .wb_rd_data(32'd0),
        .vmem_wr_en(vmem_wr_en),
        .vmem_wr_addr(vmem_wr_addr),
        .vmem_wr_data(vmem_wr_data)
    );

    initial begin
        for (i = 0; i < N_CELLS; i = i + 1) begin
            hits[i] = 0;
            hot_hits[i] = 0;
            base_hits[i] = 0;
        end

        // The header of every stage box.
        cell_addr[0] = u_dut.ADDR_STAGE_FETCH_0;
        cell_char[0] = "F";
        cell_base[0] = ATTR_RED_BASE;
        cell_hot[0]  = ATTR_RED_HOT;
        cell_sel[0]  = SEL_IF;

        cell_addr[1] = u_dut.ADDR_STAGE_IF_ID_0;
        cell_char[1] = "I";
        cell_base[1] = ATTR_BLUE_BASE;
        cell_hot[1]  = ATTR_BLUE_HOT;
        cell_sel[1]  = SEL_ID;

        cell_addr[2] = u_dut.ADDR_STAGE_DECODE_0;
        cell_char[2] = "D";
        cell_base[2] = ATTR_RED_BASE;
        cell_hot[2]  = ATTR_RED_HOT;
        cell_sel[2]  = SEL_ID;

        cell_addr[3] = u_dut.ADDR_STAGE_ID_EX_0;
        cell_char[3] = "I";
        cell_base[3] = ATTR_BLUE_BASE;
        cell_hot[3]  = ATTR_BLUE_HOT;
        cell_sel[3]  = SEL_EX;

        cell_addr[4] = u_dut.ADDR_STAGE_EXECUTE_0;
        cell_char[4] = "E";
        cell_base[4] = ATTR_RED_BASE;
        cell_hot[4]  = ATTR_RED_HOT;
        cell_sel[4]  = SEL_EX;

        cell_addr[5] = u_dut.ADDR_STAGE_EX_MEM_0;
        cell_char[5] = "E";
        cell_base[5] = ATTR_BLUE_BASE;
        cell_hot[5]  = ATTR_BLUE_HOT;
        cell_sel[5]  = SEL_MEM;

        cell_addr[6] = u_dut.ADDR_STAGE_MEMORY_0;
        cell_char[6] = "M";
        cell_base[6] = ATTR_RED_BASE;
        cell_hot[6]  = ATTR_RED_HOT;
        cell_sel[6]  = SEL_MEM;

        cell_addr[7] = u_dut.ADDR_STAGE_MEM_WB_0;
        cell_char[7] = "M";
        cell_base[7] = ATTR_BLUE_BASE;
        cell_hot[7]  = ATTR_BLUE_HOT;
        cell_sel[7]  = SEL_MEM;

        cell_addr[8] = u_dut.ADDR_STAGE_WRITEBACK_0;
        cell_char[8] = "W";
        cell_base[8] = ATTR_RED_BASE;
        cell_hot[8]  = ATTR_RED_HOT;
        cell_sel[8]  = SEL_WB;

        // The flow arrow that leaves every stage.
        cell_addr[9] = u_dut.ADDR_ARROW_9_24;
        cell_char[9] = "-";
        cell_base[9] = ATTR_ARROW_BASE;
        cell_hot[9]  = ATTR_ARROW_HOT;
        cell_sel[9]  = SEL_IF;

        cell_addr[10] = u_dut.ADDR_ARROW_24_43;
        cell_char[10] = "v";
        cell_base[10] = ATTR_ARROW_BASE;
        cell_hot[10]  = ATTR_ARROW_HOT;
        cell_sel[10]  = SEL_ID;

        cell_addr[11] = u_dut.ADDR_ARROW_41_55;
        cell_char[11] = "-";
        cell_base[11] = ATTR_ARROW_BASE;
        cell_hot[11]  = ATTR_ARROW_HOT;
        cell_sel[11]  = SEL_EX;

        cell_addr[12] = u_dut.ADDR_ARROW_44_72;
        cell_char[12] = "^";
        cell_base[12] = ATTR_ARROW_BASE;
        cell_hot[12]  = ATTR_ARROW_HOT;
        cell_sel[12]  = SEL_MEM;

        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        // Seven phases of three sweeps each.
        repeat (24 * u_dut.N_CHARS) @(posedge clk);

        $display("cells monitored  : %0d", N_CELLS);
        for (i = 0; i < N_CELLS; i = i + 1) begin
            $display("cell %0d: %0d writes, %0d active, %0d idle",
                     i, hits[i], hot_hits[i], base_hits[i]);
            // Every cell has to be painted in both of its attributes,
            // otherwise the test did not exercise the whole effect.
            if (hits[i] == 0 || hot_hits[i] == 0 || base_hits[i] == 0) begin
                $display("FAIL: cell %0d was not painted in both attributes", i);
                errors = errors + 1;
            end
        end

        if (errors == 0) begin
            $display("PASS: every stage box and flow arrow follows its own stage");
        end else begin
            $display("FAIL: %0d mismatches, first at cell %0d (character %h, attribute %h)",
                     errors, bad_cell, bad_char, bad_attr);
        end
        $finish;
    end

endmodule
