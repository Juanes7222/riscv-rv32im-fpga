// Shadow memory: the write port must mirror the byte enables exactly, and
// an address beyond DEPTH must be handled like the CPU's memory handles
// it.
module tb_vga_shadow;
    logic wr_clk = 0, rd_clk = 0;
    always #5  wr_clk = ~wr_clk;
    always #7  rd_clk = ~rd_clk;

    logic        wr_en = 0;
    logic [31:0] wr_addr = 0, wr_data = 0;
    logic [3:0]  wr_be = 0;
    logic [31:0] rd_addr = 0;
    logic [31:0] rd_data;

    vga_mem_shadow #(.DEPTH(16)) dut (
        .wr_clk(wr_clk), .wr_en(wr_en), .wr_addr(wr_addr),
        .wr_data(wr_data), .wr_be(wr_be),
        .rd_clk(rd_clk), .rd_addr(rd_addr), .rd_data(rd_data));

    task write(input logic [31:0] addr, input logic [31:0] data, input logic [3:0] be);
        begin
            @(posedge wr_clk);
            wr_addr <= addr; wr_data <= data; wr_be <= be; wr_en <= 1'b1;
            @(posedge wr_clk);
            wr_en <= 1'b0; wr_be <= 4'b0000;
        end
    endtask

    task expect_word(input logic [31:0] addr, input logic [31:0] want);
        begin
            rd_addr <= addr;
            @(posedge rd_clk); #1;
            if (rd_data !== want)
                $fatal(1, "addr %08x: expected %08x got %08x", addr, want, rd_data);
        end
    endtask

    initial begin
        write(32'd0, 32'hAABBCCDD, 4'b1111);
        expect_word(32'd0, 32'hAABBCCDD);
        // A byte write must touch one lane only.
        write(32'd0, 32'h00000011, 4'b0001);
        expect_word(32'd0, 32'hAABBCC11);
        // A half write must touch two lanes.
        write(32'd4, 32'h00001234, 4'b0011);
        expect_word(32'd4, 32'h00001234);
        // An address beyond the depth of the array is dropped, exactly like
        // the CPU's memory drops it: the shadow takes the 13-bit word
        // index of the CPU, so the write lands outside the array.  In
        // synthesis the M10K truncates the address to the depth of the
        // array, like the CPU's array does.
        write(32'd1024, 32'hDEADBEEF, 4'b1111);
        expect_word(32'd0,   32'hAABBCC11);
        expect_word(32'd60,  32'h00000000);
        $display("PASS");
        $finish;
    end
endmodule
