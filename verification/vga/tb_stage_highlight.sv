// Coherence check for the stage highlight of the single-cycle screen writer.
//
// The stage boxes and the flow arrows between them are static cells of the
// template, but their background has to follow the stage they belong to: a
// stage that holds an instruction is painted with the dark navy of the
// palette, and so is the arrow that leaves it.
//
// The writer derives the state of every stage from the snapshot bank, so the
// check compares the attribute of every write against the derived signal of
// the DUT at that very instant.  The instruction walks through the states
// the console has to show - nothing, the canonical bubble, a load, a store
// and an add - and every state is held for three sweeps, so the snapshot
// bank captures all of them.
//
// The addresses come from the writer itself, so the check follows the
// template instead of hard-coding a layout.

module tb_stage_highlight;

    logic clk = 1'b0;
    logic rst_n = 1'b0;

    logic [31:0] instruction;
    logic [0:0]  dm_wr;

    logic        vmem_wr_en;
    logic [12:0] vmem_wr_addr;
    logic [15:0] vmem_wr_data;

    // The attribute of a cell is {background[7:4], foreground[3:0]}.  The
    // stage headers keep the red of the template (foreground 11) and the
    // flow arrows its grey (foreground 9); only the background changes.
    localparam logic [7:0] ATTR_HEADER_BASE = 8'h0B;
    localparam logic [7:0] ATTR_HEADER_HOT  = 8'h1B;
    localparam logic [7:0] ATTR_ARROW_BASE  = 8'h09;
    localparam logic [7:0] ATTR_ARROW_HOT   = 8'h19;

    // The signal that decides whether a cell is painted as active.
    localparam int SEL_STAGE = 0;   // the stage holds an instruction
    localparam int SEL_MEM   = 1;   // the instruction accesses the memory
    localparam int SEL_WRITE = 2;   // the memory is written

    localparam int N_CELLS = 9;

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

    // The instruction walks through the states of the console.  A state is
    // held for three sweeps, so the snapshot bank of every group captures it.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= 3'd0;
            hold <= 0;
            instruction <= 32'h00000000;
            dm_wr <= 1'b0;
        end else if (hold >= 3 * u_dut.N_CHARS) begin
            hold <= 0;
            case (state)
                3'd0: begin
                    state <= 3'd1;
                    instruction <= 32'h00000013;   // the canonical bubble
                    dm_wr <= 1'b0;
                end
                3'd1: begin
                    state <= 3'd2;
                    instruction <= 32'h00002003;   // a load
                    dm_wr <= 1'b0;
                end
                3'd2: begin
                    state <= 3'd3;
                    instruction <= 32'h00002023;   // a store
                    dm_wr <= 1'b1;
                end
                3'd3: begin
                    state <= 3'd4;
                    instruction <= 32'h00000033;   // an add
                    dm_wr <= 1'b0;
                end
                default: begin
                    state <= 3'd0;
                    instruction <= 32'h00000000;   // nothing to execute
                    dm_wr <= 1'b0;
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
                        SEL_STAGE: hot_now = u_dut.stage_active;
                        SEL_MEM:   hot_now = u_dut.mem_access;
                        default:   hot_now = u_dut.mem_write_access;
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

    screen_writer_single_cycle u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .alu_a(32'd0),
        .alu_b(32'd0),
        .alu_op(5'd0),
        .alu_res(32'd0),
        .alua_src(2'd0),
        .alub_src(1'b0),
        .br_op(5'd0),
        .branch(1'b0),
        .cycle_count(64'd0),
        .cycles_at_done(64'd0),
        .data_wr(32'd0),
        .dm_addr(32'd0),
        .dm_ctrl(3'd0),
        .dm_rdata(32'd0),
        .dm_wdata(32'd0),
        .dm_wr(dm_wr),
        .funct3(3'd0),
        .funct7(7'd0),
        .halted(1'b0),
        .imm_out(32'd0),
        .imm_src(3'd0),
        .instr_at_done(64'd0),
        .instruction(instruction),
        .next_pc(32'd0),
        .opcode(7'd0),
        .pc(32'd0),
        .rd_addr(5'd0),
        .rs1_addr(5'd0),
        .rs1_data(32'd0),
        .rs2_addr(5'd0),
        .rs2_data(32'd0),
        .ru_data_wr_src(2'd0),
        .ru_wr(1'b0),
        .reg_values(1024'd0),
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

        // The header of every stage box and the flow arrow of every stage.
        cell_addr[0] = u_dut.ADDR_STAGE_FETCH_0;
        cell_char[0] = "F";
        cell_base[0] = ATTR_HEADER_BASE;
        cell_hot[0]  = ATTR_HEADER_HOT;
        cell_sel[0]  = SEL_STAGE;

        cell_addr[1] = u_dut.ADDR_STAGE_DECODE_0;
        cell_char[1] = "D";
        cell_base[1] = ATTR_HEADER_BASE;
        cell_hot[1]  = ATTR_HEADER_HOT;
        cell_sel[1]  = SEL_STAGE;

        cell_addr[2] = u_dut.ADDR_STAGE_EXECUTE_0;
        cell_char[2] = "E";
        cell_base[2] = ATTR_HEADER_BASE;
        cell_hot[2]  = ATTR_HEADER_HOT;
        cell_sel[2]  = SEL_STAGE;

        cell_addr[3] = u_dut.ADDR_STAGE_MEMORY_0;
        cell_char[3] = "M";
        cell_base[3] = ATTR_HEADER_BASE;
        cell_hot[3]  = ATTR_HEADER_HOT;
        cell_sel[3]  = SEL_MEM;

        cell_addr[4] = u_dut.ADDR_STAGE_WRITEBACK_0;
        cell_char[4] = "W";
        cell_base[4] = ATTR_HEADER_BASE;
        cell_hot[4]  = ATTR_HEADER_HOT;
        cell_sel[4]  = SEL_WRITE;

        cell_addr[5] = u_dut.ADDR_ARROW_11_58;
        cell_char[5] = "V";
        cell_base[5] = ATTR_ARROW_BASE;
        cell_hot[5]  = ATTR_ARROW_HOT;
        cell_sel[5]  = SEL_STAGE;

        cell_addr[6] = u_dut.ADDR_ARROW_17_89;
        cell_char[6] = "^";
        cell_base[6] = ATTR_ARROW_BASE;
        cell_hot[6]  = ATTR_ARROW_HOT;
        cell_sel[6]  = SEL_MEM;

        cell_addr[7] = u_dut.ADDR_ARROW_29_60;
        cell_char[7] = "V";
        cell_base[7] = ATTR_ARROW_BASE;
        cell_hot[7]  = ATTR_ARROW_HOT;
        cell_sel[7]  = SEL_STAGE;

        cell_addr[8] = u_dut.ADDR_ARROW_30_89;
        cell_char[8] = "^";
        cell_base[8] = ATTR_ARROW_BASE;
        cell_hot[8]  = ATTR_ARROW_HOT;
        cell_sel[8]  = SEL_MEM;

        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        // Five states of three sweeps each.
        repeat (18 * u_dut.N_CHARS) @(posedge clk);

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
            $display("PASS: the stage boxes and the flow arrows follow the stage they belong to");
        end else begin
            $display("FAIL: %0d mismatches, first at cell %0d (character %h, attribute %h)",
                     errors, bad_cell, bad_char, bad_attr);
        end
        $finish;
    end

endmodule
