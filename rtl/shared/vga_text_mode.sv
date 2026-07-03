// VGA text-mode pixel generator.
// Reads character code from video_memory, looks up font bitmap, and
// produces 8-bpp RGB pixels with a 2-cycle pipeline to compensate for
// registered memory reads.

module vga_text_mode (
    input  logic        clk,          // vga_pixel_clk
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

    // Font ROM address: char_code × 16 + row_in_char
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

    // Foreground / background colours (white on black)
    localparam logic [7:0] FG = 8'hFF;
    localparam logic [7:0] BG = 8'h00;

    always_comb begin
        if (video_on_d2 && pixel_bit) begin
            vga_r = FG;
            vga_g = FG;
            vga_b = FG;
        end else begin
            vga_r = BG;
            vga_g = BG;
            vga_b = BG;
        end
    end

endmodule