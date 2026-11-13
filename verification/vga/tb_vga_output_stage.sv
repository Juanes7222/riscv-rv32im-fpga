`timescale 1ns/1ps

// Exercise a complete 720p frame through the real controller and renderer.
// A synchronous character source changes colour at cell boundaries, exposing
// mismatches between the memory, RGB, blanking and sync pipelines.
module tb_vga_output_stage;
    logic clk = 0;
    logic reset = 1;
    always #6.734 clk = ~clk;
    wire [10:0] hcount;
    wire [9:0] vcount;
    wire video_on, hsync, vsync;
    logic [15:0] char_data;
    wire [7:0] pixel_r, pixel_g, pixel_b;
    wire [7:0] red, green, blue;
    wire blank_n, out_hsync, out_vsync, dac_clock;
    integer h_history [0:2];
    integer v_history [0:2];
    integer valid = 0;
    integer active_pixels = 0;
    integer hsync_pixels = 0;
    integer vsync_pixels = 0;
    integer x, y, i;
    logic [23:0] expected_rgb;
    logic [26:0] sampled_pins;
    realtime last_pin_change = 0;

    vga_controller_1280x720 controller (
        .clk(clk), .reset(reset), .hcount(hcount), .vcount(vcount),
        .video_on(video_on), .hsync(hsync), .vsync(vsync)
    );
    always @(posedge clk) begin
        char_data <= (hcount[3] ^ vcount[4]) ? 16'hBB20 : 16'h8820;
        if (reset) begin
            valid <= 0;
        end else begin
            h_history[0] <= hcount;
            h_history[1] <= h_history[0];
            h_history[2] <= h_history[1];
            v_history[0] <= vcount;
            v_history[1] <= v_history[0];
            v_history[2] <= v_history[1];
            if (valid < 3) valid <= valid + 1;
        end
    end
    vga_text_mode renderer (
        .clk(clk), .reset(reset), .hcount(hcount), .vcount(vcount),
        .video_on(video_on), .char_data(char_data),
        .vga_r(pixel_r), .vga_g(pixel_g), .vga_b(pixel_b)
    );
    vga_output_stage dut (
        .pixel_clk(clk), .reset(reset),
        .pixel_r(pixel_r), .pixel_g(pixel_g), .pixel_b(pixel_b),
        .video_on(video_on), .hsync(hsync), .vsync(vsync),
        .vga_r(red), .vga_g(green), .vga_b(blue),
        .vga_blank_n(blank_n), .vga_hsync(out_hsync), .vga_vsync(out_vsync),
        .vga_clock(dac_clock)
    );

    always @(red or green or blue or blank_n or out_hsync or out_vsync)
        last_pin_change = $realtime;

    task automatic check_sample;
        begin
            x = h_history[2];
            y = v_history[2];
            expected_rgb = (((x / 8) % 2) ^ ((y / 16) % 2)) ?
                           24'hFF5050 : 24'hFFFFFF;
            if ({red, green, blue} !== expected_rgb)
                $fatal(1, "RGB/cell alignment at %0d,%0d: %h != %h",
                       x, y, {red, green, blue}, expected_rgb);
            if (blank_n !== (x < 1280 && y < 720))
                $fatal(1, "Blanking alignment at %0d,%0d", x, y);
            if (out_hsync !== (x >= 1390 && x < 1430))
                $fatal(1, "Horizontal sync alignment at %0d,%0d", x, y);
            if (out_vsync !== (y >= 725 && y < 730))
                $fatal(1, "Vertical sync alignment at %0d,%0d", x, y);
            if (dac_clock !== 1'b1 || clk !== 1'b0)
                $fatal(1, "DAC must sample opposite the RGB update edge");
            if ($realtime - last_pin_change < 0.2)
                $fatal(1, "RTL interface setup interval below 0.2 ns");
            sampled_pins = {red, green, blue, blank_n, out_hsync, out_vsync};
            #1.5;
            if (sampled_pins !== {red, green, blue, blank_n, out_hsync, out_vsync})
                $fatal(1, "RTL interface hold interval below 1.5 ns");
        end
    endtask

    initial begin
        repeat (4) @(negedge clk);
        if ({red, green, blue, blank_n, out_hsync, out_vsync} !== 27'b0)
            $fatal(1, "Video outputs must be blank during reset");
        #1 reset = 0;
        wait (valid == 3);
        @(negedge clk);
        #0.001;
        for (i = 0; i < 1650 * 750; i = i + 1) begin
            check_sample();
            if (x != i % 1650 || y != i / 1650)
                $fatal(1, "Frame counter discontinuity at sample %0d", i);
            active_pixels += blank_n;
            hsync_pixels += out_hsync;
            vsync_pixels += out_vsync;
            @(negedge clk);
            #0.001;
        end
        if (active_pixels != 1280 * 720 || hsync_pixels != 40 * 750 ||
            vsync_pixels != 5 * 1650)
            $fatal(1, "Incorrect full-frame active or sync durations");
        // A reset during active operation must flush stale pixels and control.
        reset = 1;
        @(negedge clk);
        #0.001;
        if ({red, green, blue, blank_n, out_hsync, out_vsync} !== 27'b0)
            $fatal(1, "Reset failed to blank running video");
        $display("PASS: 1237500 pixels, RGB/control alignment, 720p sync, DAC phase and reset");
        $finish;
    end
    initial begin
        #20000000;
        $fatal(1, "Video interface test timed out");
    end
endmodule
