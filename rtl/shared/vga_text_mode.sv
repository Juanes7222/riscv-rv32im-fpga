// VGA text-mode pixel generator.
// Reads character code from video_memory, looks up font bitmap, and
// produces 8-bpp RGB pixels with a 2-cycle pipeline to compensate for
// registered memory reads.
// The video-memory cell is {attribute[15:8], character[7:0]}: the attribute
// byte selects the foreground colour from its low nibble and the background
// colour from its high nibble.

module vga_text_mode (
    input  logic        clk,          // vga_pixel_clk
    input  logic        reset,        // synchronous, active high
    input  logic [10:0] hcount,
    input  logic [9:0]  vcount,
    input  logic        video_on,
    input  logic [15:0] char_data,    // from video_memory (1-cycle delayed)
    output logic [7:0]  vga_r,
    output logic [7:0]  vga_g,
    output logic [7:0]  vga_b
);

    // Pipeline stage 0: align hcount/vcount with char_data (1-cycle vmem delay)
    logic [10:0] hcount_d1;
    logic [9:0]  vcount_d1;
    logic        video_on_d1;

    always_ff @(posedge clk) begin
        hcount_d1  <= hcount;
        vcount_d1  <= vcount;
        video_on_d1<= video_on;
    end

    // Font ROM address: char_code x 16 + row_in_char
    logic [11:0] font_addr;
    assign font_addr = {char_data[7:0], vcount_d1[3:0]};

    logic [7:0] font_byte;
    vga_font_rom u_font (
        .clk  (clk),
        .addr (font_addr),
        .data (font_byte)
    );

    // Pipeline stage 1: align hcount with font_byte (another cycle)
    logic [10:0] hcount_d2;
    logic        video_on_d2;

    always_ff @(posedge clk) begin
        hcount_d2  <= hcount_d1;
        video_on_d2<= video_on_d1;
    end

    // Extract pixel bit: MSB is leftmost pixel in the 8-pixel-wide character row.
    logic pixel_bit;
    assign pixel_bit = font_byte[7 - hcount_d2[2:0]];

    // 16-entry RGB palette shared by foreground and background.
    function automatic logic [23:0] palette_rgb(input logic [3:0] idx);
        case (idx)
            4'd0:  palette_rgb = 24'h000000;
            4'd1:  palette_rgb = 24'h101040;
            4'd2:  palette_rgb = 24'h103010;
            4'd3:  palette_rgb = 24'h501010;
            4'd4:  palette_rgb = 24'h505000;
            4'd5:  palette_rgb = 24'h202020;
            4'd6:  palette_rgb = 24'h303030;
            4'd7:  palette_rgb = 24'h606060;
            4'd8:  palette_rgb = 24'hFFFFFF;
            4'd9:  palette_rgb = 24'hC0C0C0;
            4'd10: palette_rgb = 24'h8FB8FF;
            4'd11: palette_rgb = 24'hFF5050;
            4'd12: palette_rgb = 24'h50FF50;
            4'd13: palette_rgb = 24'h6060FF;
            4'd14: palette_rgb = 24'hFF60FF;
            4'd15: palette_rgb = 24'hFFFF60;
            default: palette_rgb = 24'hC0C0C0;
        endcase
    endfunction

    // Colours are registered in the same stage as the font ROM output, so the
    // attribute byte travels with the character it belongs to and the path
    // from a register to the output pins keeps a single mux level.
    logic [23:0] fg_rgb;
    logic [23:0] bg_rgb;

    always_ff @(posedge clk) begin
        if (reset) begin
            fg_rgb <= 24'h000000;
            bg_rgb <= 24'h000000;
        end else begin
            fg_rgb <= palette_rgb(char_data[11:8]);
            bg_rgb <= palette_rgb(char_data[15:12]);
        end
    end

    // The colour mux is combinational; the channel split is plain wiring.
    logic [23:0] pixel_rgb;

    always_comb begin
        if (video_on_d2 && pixel_bit) begin
            pixel_rgb = fg_rgb;
        end else begin
            pixel_rgb = bg_rgb;
        end
    end

    assign vga_r = pixel_rgb[23:16];
    assign vga_g = pixel_rgb[15:8];
    assign vga_b = pixel_rgb[7:0];

endmodule