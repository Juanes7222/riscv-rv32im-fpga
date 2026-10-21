// Palette lookup: every attribute index must map to the RGB of the shared
// palette table, and the attribute byte must select the foreground colour
// from the low nibble and the background from the high nibble.
module tb_vga_palette;

    // Icarus cannot elaborate an unpacked-array constant initialiser, so the
    // table is filled element by element in the test process.
    logic [23:0] EXPECTED [0:15];

    logic        clk       = 1'b0;
    logic        reset     = 1'b1;
    logic [10:0] hcount    = 11'd0;
    logic [9:0]  vcount    = 10'd0;
    logic        video_on  = 1'b0;
    logic [15:0] char_data = 16'h0000;
    logic [7:0]  vga_r, vga_g, vga_b;

    vga_text_mode dut (
        .clk(clk), .reset(reset), .hcount(hcount), .vcount(vcount),
        .video_on(video_on), .char_data(char_data),
        .vga_r(vga_r), .vga_g(vga_g), .vga_b(vga_b)
    );

    task automatic tick;
        begin
            clk = 1'b1; #1;
            clk = 1'b0; #1;
        end
    endtask

    initial begin
        EXPECTED[0]  = 24'h000000;
        EXPECTED[1]  = 24'h101040;
        EXPECTED[2]  = 24'h103010;
        EXPECTED[3]  = 24'h501010;
        EXPECTED[4]  = 24'h505000;
        EXPECTED[5]  = 24'h202020;
        EXPECTED[6]  = 24'h303030;
        EXPECTED[7]  = 24'h606060;
        EXPECTED[8]  = 24'hFFFFFF;
        EXPECTED[9]  = 24'hC0C0C0;
        EXPECTED[10] = 24'h8FB8FF;
        EXPECTED[11] = 24'hFF5050;
        EXPECTED[12] = 24'h50FF50;
        EXPECTED[13] = 24'h6060FF;
        EXPECTED[14] = 24'hFF60FF;
        EXPECTED[15] = 24'hFFFF60;

        for (int i = 0; i < 16; i++) begin
            logic [23:0] got;
            got = dut.palette_rgb(i[3:0]);
            if (got !== EXPECTED[i])
                $fatal(1, "palette index %0d: expected %06x got %06x",
                       i, EXPECTED[i], got);
        end

        // The attribute byte is {background[15:12], foreground[11:8], char[7:0]}.
        char_data = {4'h8, 4'h2, 8'h41};

        // Reset clears both colour registers.
        reset = 1'b1;
        tick();
        tick();
        if (dut.fg_rgb !== 24'h000000 || dut.bg_rgb !== 24'h000000)
            $fatal(1, "reset did not clear the colour registers");

        // Foreground comes from the low nibble, background from the high one.
        reset = 1'b0;
        tick();
        if (dut.fg_rgb !== EXPECTED[4'h2])
            $fatal(1, "foreground: expected %06x got %06x", EXPECTED[4'h2], dut.fg_rgb);
        if (dut.bg_rgb !== EXPECTED[4'h8])
            $fatal(1, "background: expected %06x got %06x", EXPECTED[4'h8], dut.bg_rgb);

        // A blank glyph row paints the background colour.
        video_on = 1'b1;
        hcount   = 11'd0;
        vcount   = 10'd0;
        char_data = {4'h8, 4'h2, 8'h00};
        tick();
        tick();
        if ({vga_r, vga_g, vga_b} !== EXPECTED[4'h8])
            $fatal(1, "background pixel: expected %06x got %06x",
                   EXPECTED[4'h8], {vga_r, vga_g, vga_b});

        // Glyph 'A', row 2 is 0x10, so column 3 is a set bit: it paints the
        // foreground colour.
        hcount    = 11'd3;
        vcount    = 10'd2;
        char_data = {4'h8, 4'h2, 8'h41};
        tick();
        tick();
        if ({vga_r, vga_g, vga_b} !== EXPECTED[4'h2])
            $fatal(1, "foreground pixel: expected %06x got %06x",
                   EXPECTED[4'h2], {vga_r, vga_g, vga_b});

        $display("PASS");
        $finish;
    end
endmodule
