// VGA font ROM - 256 characters x 16 rows, 8 bits per row (8x16 font).
// Synchronous read so Quartus infers block ROM (M10K or MLAB).
// Initialised from vga_font_rom.hex (raw hex, one byte per line).

// Path relative to the Quartus project directory (synthesis/<arch>/).  A
// simulator can override it from the command line, because it resolves the
// path against its own working directory.
`ifndef FONT_ROM_FILE
`define FONT_ROM_FILE "../../rtl/shared/vga_font_rom.hex"
`endif

module vga_font_rom (
    input  logic        clk,
    input  logic [11:0] addr,   // char_code[7:0] & row[3:0]
    output logic [7:0]  data
);

    // 4096 entries: 256 chars x 16 rows each.
    (* ramstyle = "M10K, no_rw_check" *)
    logic [7:0] mem [0:4095];

    // Quartus accepts $readmemh in synthesis for ROM initialisation.
    initial begin
        $readmemh(`FONT_ROM_FILE, mem);
    end

    always_ff @(posedge clk) begin
        data <= mem[addr];
    end

endmodule
