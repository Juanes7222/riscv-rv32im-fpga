// Read-only copy of the program image for the VGA console.
//
// The program is a ROM, so the copy never changes: it is initialised from
// the same image the processor's instruction memory uses and read from the
// VGA clock domain.
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

    // An address beyond the memory fetches a NOP, exactly like the
    // processor's instruction memory, so the console never shows a word
    // where the processor would execute a NOP.
    logic addr_out_of_bounds;
    assign addr_out_of_bounds = (rd_addr[31:ADDR_BITS+2] != 0);

    always_ff @(posedge rd_clk) begin
        rd_data <= addr_out_of_bounds ? 32'h00000013 : mem[word_index];
    end
endmodule
