// Coherence check for the single-cycle screen writer.
//
// The writer formats one character per pixel clock.  Without a snapshot bank
// an eight digit field is assembled from eight different instants of the
// sampled signal, so the number on screen never existed on the bus.  This
// test drives the PC with a counter that changes every cycle and verifies
// that all eight characters of the field come from one captured instant.
//
// It also checks that the register table is written from the packed register
// file bus: every register holds the same pattern, so each row of the table
// must show it.
//
// The last check covers the attribute byte: a field that changes meaning
// changes its colour.  The dm_wr field is the probe: it keeps its base
// colour while the write enable is low and turns to its hot colour while
// the write enable is high.

module tb_screen_writer_snapshot;

    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic [31:0] pc = 32'h11111111;
    logic [1023:0] reg_values = {1024{1'b0}};

    logic [31:0] alu_a;
    logic [31:0] alu_b;
    logic [4:0] alu_op;
    logic [31:0] alu_res;
    logic [1:0] alua_src;
    logic [0:0] alub_src;
    logic [4:0] br_op;
    logic [0:0] branch;
    logic [63:0] cycle_count;
    logic [31:0] data_wr;
    logic [31:0] dm_addr;
    logic [2:0] dm_ctrl;
    logic [31:0] dm_rdata;
    logic [31:0] dm_wdata;
    logic [0:0] dm_wr;
    logic       dm_wr_drive = 1'b0;
    logic [2:0] funct3;
    logic [6:0] funct7;
    logic [0:0] halted;
    logic [31:0] imm_out;
    logic [2:0] imm_src;
    logic [31:0] instruction;
    logic [31:0] next_pc;
    logic [6:0] opcode;
    logic [4:0] rd_addr;
    logic [4:0] rs1_addr;
    logic [31:0] rs1_data;
    logic [4:0] rs2_addr;
    logic [31:0] rs2_data;
    logic [1:0] ru_data_wr_src;
    logic [0:0] ru_wr;

    logic        vmem_wr_en;
    logic [12:0] vmem_wr_addr;
    logic [15:0] vmem_wr_data;

    localparam int FIELD_WIDTH = 8;
    localparam logic [31:0] REG_PATTERN = 32'hA5A5A5A5;

    // Address of the dm_wr field, taken from synthesis/single_cycle/fields.json.
    localparam logic [12:0] ADDR_DM_WR = 13'd4574;
    // Attribute of the dm_wr field: body colour, and the hot colour of a
    // write in progress (foreground 11 on background 3).
    localparam logic [7:0] ATTR_BASE = 8'h09;
    localparam logic [7:0] ATTR_HOT  = 8'h3B;

    logic [7:0]  field_char [0:FIELD_WIDTH-1];
    logic [31:0] field_snap [0:FIELD_WIDTH-1];
    logic [7:0]  reg_char   [0:FIELD_WIDTH-1];
    integer      field_pos = 0;
    integer      reg_pos = 0;
    integer      groups = 0;
    integer      attr_low = 0;    // dm_wr written with the snapshot low
    integer      attr_high = 0;   // dm_wr written with the snapshot high
    integer      errors = 0;
    integer      i;

    always #1 clk = ~clk;

    initial alu_a = 0;
    initial alu_b = 0;
    initial alu_op = 0;
    initial alu_res = 0;
    initial alua_src = 0;
    initial alub_src = 0;
    initial br_op = 0;
    initial branch = 0;
    initial cycle_count = 0;
    initial data_wr = 0;
    initial dm_addr = 0;
    initial dm_ctrl = 0;
    initial dm_rdata = 0;
    initial dm_wdata = 0;
    initial dm_wr = 0;
    initial funct3 = 0;
    initial funct7 = 0;
    initial halted = 0;
    initial imm_out = 0;
    initial imm_src = 0;
    initial instruction = 0;
    initial next_pc = 0;
    initial opcode = 0;
    initial rd_addr = 0;
    initial rs1_addr = 0;
    initial rs1_data = 0;
    initial rs2_addr = 0;
    initial rs2_data = 0;
    initial ru_data_wr_src = 0;
    initial ru_wr = 0;

    always_ff @(posedge clk) begin
        if (rst_n) begin
            alu_a <= alu_a + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            alu_b <= alu_b + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            alu_op <= alu_op + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            alu_res <= alu_res + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            alua_src <= alua_src + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            alub_src <= alub_src + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            br_op <= br_op + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            branch <= branch + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            cycle_count <= cycle_count + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            data_wr <= data_wr + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            dm_addr <= dm_addr + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            dm_ctrl <= dm_ctrl + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            dm_rdata <= dm_rdata + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            dm_wdata <= dm_wdata + 1'b1;
        end
    end
    // The write enable is the probe of the attribute test: it is driven in
    // two deliberate phases instead of counting.
    always_ff @(posedge clk) begin
        if (rst_n) begin
            dm_wr <= dm_wr_drive;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            funct3 <= funct3 + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            funct7 <= funct7 + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            halted <= halted + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            imm_out <= imm_out + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            imm_src <= imm_src + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            instruction <= instruction + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            next_pc <= next_pc + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            opcode <= opcode + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            rd_addr <= rd_addr + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            rs1_addr <= rs1_addr + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            rs1_data <= rs1_data + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            rs2_addr <= rs2_addr + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            rs2_data <= rs2_data + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            ru_data_wr_src <= ru_data_wr_src + 1'b1;
        end
    end
    always_ff @(posedge clk) begin
        if (rst_n) begin
            ru_wr <= ru_wr + 1'b1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst_n) begin
            pc <= pc + 32'h11111111;
        end
    end

    // Collect the characters written into the PC field and into x0.
    always_ff @(posedge clk) begin
        if (rst_n && vmem_wr_en) begin
            if (vmem_wr_addr == u_dut.ADDR_PC) begin
                field_pos = 0;
                groups = groups + 1;
            end
            if (vmem_wr_addr >= u_dut.ADDR_PC &&
                vmem_wr_addr < u_dut.ADDR_PC + FIELD_WIDTH) begin
                field_char[field_pos] = vmem_wr_data[7:0];
                field_snap[field_pos] = u_dut.snap_pc;
                field_pos = field_pos + 1;
            end
            if (vmem_wr_addr == u_dut.ADDR_X0) begin
                reg_pos = 0;
            end
            if (vmem_wr_addr >= u_dut.ADDR_X0 &&
                vmem_wr_addr < u_dut.ADDR_X0 + FIELD_WIDTH) begin
                reg_char[reg_pos] = vmem_wr_data[7:0];
                reg_pos = reg_pos + 1;
            end
            // The attribute of the dm_wr field must follow the value the
            // field shows, which is the snapshot of the write enable.
            if (vmem_wr_addr == ADDR_DM_WR) begin
                if (u_dut.snap_dm_wr) begin
                    attr_high = attr_high + 1;
                end else begin
                    attr_low = attr_low + 1;
                end
                if (vmem_wr_data[15:8] !=
                    (u_dut.snap_dm_wr ? ATTR_HOT : ATTR_BASE)) begin
                    errors = errors + 1;
                end
            end
        end
    end

    screen_writer_single_cycle u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .pc(pc),
        .reg_values(reg_values),
        .alu_a(alu_a),
        .alu_b(alu_b),
        .alu_op(alu_op),
        .alu_res(alu_res),
        .alua_src(alua_src),
        .alub_src(alub_src),
        .br_op(br_op),
        .branch(branch),
        .cycle_count(cycle_count),
        .cycles_at_done(64'd0),
        .instr_at_done(64'd0),
        .data_wr(data_wr),
        .dm_addr(dm_addr),
        .dm_ctrl(dm_ctrl),
        .dm_rdata(dm_rdata),
        .dm_wdata(dm_wdata),
        .dm_wr(dm_wr),
        .funct3(funct3),
        .funct7(funct7),
        .halted(halted),
        .imm_out(imm_out),
        .imm_src(imm_src),
        .instruction(instruction),
        .next_pc(next_pc),
        .opcode(opcode),
        .rd_addr(rd_addr),
        .rs1_addr(rs1_addr),
        .rs1_data(rs1_data),
        .rs2_addr(rs2_addr),
        .rs2_data(rs2_data),
        .ru_data_wr_src(ru_data_wr_src),
        .ru_wr(ru_wr),
        .vmem_wr_en(vmem_wr_en),
        .vmem_wr_addr(vmem_wr_addr),
        .vmem_wr_data(vmem_wr_data)
    );

    initial begin
        // Every register holds the same pattern.
        for (i = 0; i < 32; i = i + 1) begin
            reg_values[32*i +: 32] = REG_PATTERN;
        end

        repeat (4) @(posedge clk);
        rst_n = 1'b1;

        // Phase 1: the write enable is low, the field keeps its base colour.
        dm_wr_drive = 1'b0;
        repeat (u_dut.N_CHARS * 4) @(posedge clk);

        // Phase 2: the write enable is high, the field turns to its hot
        // colour.  The snapshot bank picks the new value up at the end of
        // the next sweep.
        dm_wr_drive = 1'b1;
        repeat (u_dut.N_CHARS * 4) @(posedge clk);

        $display("PC field address : %0d", u_dut.ADDR_PC);
        $display("x0 field address  : %0d", u_dut.ADDR_X0);
        $display("dm_wr address     : %0d", ADDR_DM_WR);
        $display("sweeps captured   : %0d", groups);
        $display("attribute samples : %0d low, %0d high", attr_low, attr_high);
        $write("PC digits         : ");
        for (i = 0; i < FIELD_WIDTH; i = i + 1) begin
            $write("%s ", field_char[i]);
        end
        $display("");

        // Every character of the field must come from the same instant.
        for (i = 1; i < FIELD_WIDTH; i = i + 1) begin
            if (field_snap[i] !== field_snap[0]) begin
                errors = errors + 1;
            end
        end

        // ... and the characters must spell that instant.
        for (i = 0; i < FIELD_WIDTH; i = i + 1) begin
            logic [3:0] nibble;
            nibble = (field_snap[0] >> ((FIELD_WIDTH - 1 - i) * 4)) & 4'hF;
            if (field_char[i] !== ((nibble < 4'd10) ? (8'd48 + nibble) : (8'd55 + nibble))) begin
                errors = errors + 1;
            end
        end

        // The register table must show the pattern of x0.
        $write("x0 digits         : ");
        for (i = 0; i < FIELD_WIDTH; i = i + 1) begin
            $write("%s ", reg_char[i]);
        end
        $display("");
        for (i = 0; i < FIELD_WIDTH; i = i + 1) begin
            logic [3:0] nibble;
            nibble = (REG_PATTERN >> ((FIELD_WIDTH - 1 - i) * 4)) & 4'hF;
            if (reg_char[i] !== ((nibble < 4'd10) ? (8'd48 + nibble) : (8'd55 + nibble))) begin
                errors = errors + 1;
            end
        end

        // The attribute must have been seen in both states, otherwise the
        // test did not exercise the hot colour at all.
        if (attr_low == 0 || attr_high == 0) begin
            $display("FAIL: the attribute of the dm_wr field was not seen in both states");
            errors = errors + 1;
        end

        if (errors == 0) begin
            $display("PASS: fields are coherent, the register table is filled and the attribute follows the meaning");
        end else begin
            $display("FAIL: %0d mismatches", errors);
        end
        $finish;
    end

endmodule
