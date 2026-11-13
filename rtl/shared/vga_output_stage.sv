// Register digital video at the pins. The DAC samples on the following
// falling pixel edge, providing half a period for setup and hold.
// The renderer has two cycles of latency; delay blanking and sync equally.
module vga_output_stage (
    input  logic pixel_clk,
    input  logic reset,
    input  logic [7:0] pixel_r,
    input  logic [7:0] pixel_g,
    input  logic [7:0] pixel_b,
    input  logic video_on,
    input  logic hsync,
    input  logic vsync,
    output logic [7:0] vga_r,
    output logic [7:0] vga_g,
    output logic [7:0] vga_b,
    output logic vga_blank_n,
    output logic vga_hsync,
    output logic vga_vsync,
    output logic vga_clock
);
    logic [2:0] blank_pipeline;
    logic [2:0] hsync_pipeline;
    logic [2:0] vsync_pipeline;

    always_ff @(posedge pixel_clk) begin
        if (reset) begin
            vga_r <= '0;
            vga_g <= '0;
            vga_b <= '0;
            blank_pipeline <= '0;
            hsync_pipeline <= '0;
            vsync_pipeline <= '0;
        end else begin
            vga_r <= pixel_r;
            vga_g <= pixel_g;
            vga_b <= pixel_b;
            blank_pipeline <= {blank_pipeline[1:0], video_on};
            hsync_pipeline <= {hsync_pipeline[1:0], hsync};
            vsync_pipeline <= {vsync_pipeline[1:0], vsync};
        end
    end

    assign vga_blank_n = blank_pipeline[2];
    assign vga_hsync = hsync_pipeline[2];
    assign vga_vsync = vsync_pipeline[2];
    assign vga_clock = ~pixel_clk;
endmodule
