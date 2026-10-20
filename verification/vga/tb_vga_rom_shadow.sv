// ROM shadow: the program image must be loaded and read in the VGA clock
// domain, one word per pixel-clock cycle.
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
        // The index is truncated to the array depth, so 16 lands on word 0.
        expect_word(32'd16, 32'hAABBCCDD);
        $display("PASS");
        $finish;
    end
endmodule
