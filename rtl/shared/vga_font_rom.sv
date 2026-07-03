// VGA font ROM — 256 characters × 16 rows, 8 bits per row (8×16 font).
// Synchronous read so Quartus infers block ROM (M10K or MLAB).
// Initialised from vga_font_rom.hex (raw hex, one byte per line).

module vga_font_rom (
    input  logic        clk,
    input  logic [11:0] addr,   // char_code[7:0] & row[3:0]
    output logic [7:0]  data
);

    // 4096 entries: 256 chars × 16 rows each.
    (* ramstyle = "M10K, no_rw_check" *)
    logic [7:0] mem [0:4095];

    // Quartus accepts $readmemh in synthesis for ROM initialisation.
    initial begin
        // Path relative to Quartus project directory (synthesis/<arch>/)
        $readmemh("../../rtl/shared/vga_font_rom.hex", mem);
    end

    always_ff @(posedge clk) begin
        data <= mem[addr];
    end

endmodule