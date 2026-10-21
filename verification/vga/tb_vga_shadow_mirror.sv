// The shadow must mirror the CPU's data memory exactly: the same store
// signals drive both, so whatever the CPU's memory holds, the shadow holds
// too - byte lanes included.  An access whose word index is beyond the
// depth of the array is dropped by the CPU's memory, and the shadow has to
// drop it too instead of wrapping it into a word of the array.
module tb_vga_shadow_mirror;
    logic clk = 0;
    always #5 clk = ~clk;

    logic        dm_wr = 0;
    logic [31:0] addr = 0, wr_data = 0;
    logic [2:0]  dm_ctrl = 0;
    logic [31:0] cpu_rd_data;
    logic [3:0]  dbg_wr_be;
    logic [31:0] dbg_wr_data;
    logic [31:0] shadow_rd_data;

    // Access widths as the control unit encodes them.
    localparam logic [2:0] CTRL_BYTE = 3'b000;
    localparam logic [2:0] CTRL_HALF = 3'b001;
    localparam logic [2:0] CTRL_WORD = 3'b010;

    data_memory #(.DMEM_DEPTH(16)) u_cpu_mem (
        .clk        (clk),
        .addr       (addr),
        .wr_data    (wr_data),
        .dm_wr      (dm_wr),
        .dm_ctrl    (dm_ctrl),
        .rd_data    (cpu_rd_data),
        .dbg_wr_be  (dbg_wr_be),
        .dbg_wr_data(dbg_wr_data)
    );

    vga_mem_shadow #(.DEPTH(16)) u_shadow (
        .wr_clk (clk),
        .wr_en  (dm_wr),
        .wr_addr(addr),
        .wr_data(dbg_wr_data),
        .wr_be  (dbg_wr_be),
        .rd_clk (clk),
        .rd_addr(addr),
        .rd_data(shadow_rd_data)
    );

    // One store, then compare the shadow against the CPU's memory.
    task store_and_check(input logic [31:0] a, input logic [31:0] d,
                         input logic [2:0] ctrl);
        begin
            @(posedge clk);
            addr <= a; wr_data <= d; dm_ctrl <= ctrl; dm_wr <= 1'b1;
            @(posedge clk);        // both memories write here
            dm_wr <= 1'b0;
            @(posedge clk); #1;    // the shadow's read port catches up
            if (shadow_rd_data !== u_cpu_mem.mem[a[5:2]])
                $fatal(1, "addr %08x: cpu %08x shadow %08x",
                       a, u_cpu_mem.mem[a[5:2]], shadow_rd_data);
        end
    endtask

    // A store whose word index is beyond the depth of the array.  The
    // CPU's memory drops the write and its read returns X, so the shadow
    // has to drop it too: a shadow that wrapped the write into a word of
    // the array would show a word the processor never wrote.
    task store_out_of_range_and_check(input logic [31:0] a,
                                       input logic [31:0] d);
        begin
            @(posedge clk);
            addr <= a; wr_data <= d; dm_ctrl <= CTRL_WORD; dm_wr <= 1'b1;
            @(posedge clk);        // both memories write here
            dm_wr <= 1'b0;
            @(posedge clk); #1;    // the shadow's read port catches up
            if (shadow_rd_data !== cpu_rd_data)
                $fatal(1, "addr %08x: cpu %08x shadow %08x",
                       a, cpu_rd_data, shadow_rd_data);
            // The write was dropped: the first word of the array still
            // holds what the CPU's memory holds.
            addr <= 32'd0;
            @(posedge clk); #1;
            if (shadow_rd_data !== u_cpu_mem.mem[32'd0])
                $fatal(1, "addr 00000000: cpu %08x shadow %08x",
                       u_cpu_mem.mem[32'd0], shadow_rd_data);
        end
    endtask

    initial begin
        // A word store fills every lane.
        store_and_check(32'd0, 32'hAABBCCDD, CTRL_WORD);
        // A byte store touches one lane only, and the byte is the one the
        // CPU's memory keeps - not the byte that sits at the same position
        // in the source register.
        store_and_check(32'd1, 32'h00000011, CTRL_BYTE);
        // A half store touches two lanes.
        store_and_check(32'd2, 32'h00001234, CTRL_HALF);
        // A half store at an odd halfword address touches the upper lanes.
        store_and_check(32'd4, 32'hFFFFFFFF, CTRL_WORD);
        store_and_check(32'd4, 32'h00005678, CTRL_HALF);
        // A byte store on a fresh word still leaves the other lanes alone.
        store_and_check(32'd8, 32'h00000000, CTRL_WORD);
        store_and_check(32'd8, 32'h000000FF, CTRL_BYTE);
        // A store beyond the depth of the array: word 16 of a memory of
        // 16 words.  Neither memory may keep it.
        store_out_of_range_and_check(32'd64, 32'hDEADBEEF);
        $display("PASS");
        $finish;
    end
endmodule
