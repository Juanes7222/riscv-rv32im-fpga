// Read-only copy of the program image for the VGA console.
//
// The program is a ROM, so the copy never changes: it is initialised from
// the same image the processor's instruction memory uses and read from the
// VGA clock domain.
//
// The shadow returns the word of the array for every address, while the
// processor's instruction memories return a NOP beyond the image: the
// difference is accepted, because the multiplexer that would produce the
// NOP keeps Quartus from inferring the M10K, and the Fmax it costs is
// worth more than that corner case.
`include "../shared/mem_config.vh"

module vga_rom_shadow #(
    parameter int DEPTH = 2048
)(
    input  logic        rd_clk,
    input  logic [31:0] rd_addr,
    output logic [31:0] rd_data
);
    localparam int ADDR_BITS = $clog2(DEPTH);

    (* ramstyle = "M10K" *) logic [31:0] mem [0:DEPTH-1];

    initial begin
        `ifdef IMEM_FILE
            $readmemh(`IMEM_FILE, mem);
        `endif
    end

    // Word index extraction - keep outside always_ff for Icarus compat
    logic [ADDR_BITS-1:0] word_index;
    assign word_index = rd_addr[ADDR_BITS+1:2];

    always_ff @(posedge rd_clk) begin
        rd_data <= mem[word_index];
    end
endmodule
