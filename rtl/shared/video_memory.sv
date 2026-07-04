// Video memory - single-clock dual-port character buffer for text screen.
// Port A (write) and Port B (read) share the same clock (vga_pixel_clk).
// This guarantees M10K inference on Cyclone V.
// Initialised via screen.mif (Quartus project assignment).

module video_memory #(
    parameter int CELLS = 7200   // 160 cols x 45 rows
)(
    input  logic        clk,       // vga_pixel_clk (74.25 MHz)
    input  logic        wr_en,
    input  logic [12:0] wr_addr,
    input  logic [15:0] wr_data,

    input  logic [12:0] rd_addr,
    output logic [15:0] rd_data
);

    // Infer M10K and initialise from screen.mif.
    // ram_init_file is the Quartus attribute that binds a .mif to inferred RAM.
    (* ramstyle = "M10K", ram_init_file = "screen.mif" *)
    logic [15:0] mem [0:CELLS-1];

    // Synchronous write
    always_ff @(posedge clk) begin
        if (wr_en)
            mem[wr_addr] <= wr_data;
    end

    // Synchronous read (registered output, required for M10K)
    always_ff @(posedge clk) begin
        rd_data <= mem[rd_addr];
    end

endmodule