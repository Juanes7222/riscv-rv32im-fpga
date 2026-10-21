// ROM shadow: the program image must be loaded and read in the VGA clock
// domain, one word per pixel-clock cycle.  The shadow is a plain ROM: an
// address beyond the image is truncated to the depth of the array and
// lands on a lower word, because the multiplexer that would return a NOP
// keeps Quartus from inferring the M10K.
module tb_vga_rom_shadow;
    logic rd_clk = 0;
    always #5 rd_clk = ~rd_clk;

    logic [31:0] rd_addr = 0;
    logic [31:0] rd_data;

    vga_rom_shadow #(.DEPTH(4)) dut (
        .rd_clk(rd_clk), .rd_addr(rd_addr), .rd_data(rd_data));

    task expect_word(input logic [31:0] addr, input logic [31:0] want);
        begin
            rd_addr <= addr;
            @(posedge rd_clk); #1;
            if (rd_data !== want)
                $fatal(1, "addr %08x: expected %08x got %08x", addr, want, rd_data);
        end
    endtask

    initial begin
        expect_word(32'd0,  32'hAABBCCDD);
        expect_word(32'd4,  32'h11223344);
        expect_word(32'd8,  32'h55667788);
        expect_word(32'd12, 32'h99AABBCC);
        // An address beyond the program is truncated to the depth of the
        // array, so it lands on a lower word: the shadow is a plain ROM
        // and has no out-of-range multiplexer.
        expect_word(32'd16, 32'hAABBCCDD);
        expect_word(32'hFFFFFFF0, 32'hAABBCCDD);
        $display("PASS");
        $finish;
    end
endmodule
