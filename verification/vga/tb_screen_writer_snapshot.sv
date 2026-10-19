// Coherence check for the single-cycle screen writer.
//
// The writer formats one character per pixel clock.  Without a snapshot bank
// an eight digit field is assembled from eight different instants of the
// sampled signal, so the number on screen never existed on the bus.  This
// test drives the PC with a counter that changes every cycle and verifies
// that all eight characters of the field come from one captured instant.

module tb_screen_writer_snapshot;

    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic [31:0] pc = 32'h11111111;

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

    logic [7:0]  field_char [0:FIELD_WIDTH-1];
    logic [31:0] field_snap [0:FIELD_WIDTH-1];
    integer      field_pos = 0;
    integer      groups = 0;
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
    always_ff @(posedge clk) begin
        if (rst_n) begin
            dm_wr <= dm_wr + 1'b1;
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

    // Collect the characters written into the PC field.
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
        end
    end

    screen_writer_single_cycle u_dut (
        .clk(clk),
        .rst_n(rst_n),
        .pc(pc),
        .alu_a(alu_a),
        .alu_b(alu_b),
        .alu_op(alu_op),
        .alu_res(alu_res),
        .alua_src(alua_src),
        .alub_src(alub_src),
        .br_op(br_op),
        .branch(branch),
        .cycle_count(cycle_count),
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
        repeat (4) @(posedge clk);
        rst_n = 1'b1;
        // Let several full sweeps run.
        repeat (u_dut.N_CHARS * 6) @(posedge clk);

        $display("PC field address : %0d", u_dut.ADDR_PC);
        $display("sweeps captured   : %0d", groups);
        $write("digits            : ");
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

        if (errors == 0) begin
            $display("PASS: the field is rendered from one coherent instant");
        end else begin
            $display("FAIL: %0d mismatches (torn field)", errors);
        end
        $finish;
    end

endmodule
