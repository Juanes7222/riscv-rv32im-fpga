// Copy of the program image for the VGA console.
//
// The console reads it in its own clock domain.  The program loader writes
// whole words through the write port, which lives in the processor clock
// domain and is driven by the very same signals as the instruction memory,
// so the listing shows the program that is actually loaded.  Without the
// write port the console would keep showing the image synthesised into the
// bitstream.
//
// The shadow returns the word of the array for every address, while the
// processor's instruction memory returns a NOP beyond the image: the
// difference is accepted, because the multiplexer that would produce the
// NOP keeps Quartus from inferring the M10K, and the Fmax it costs is
// worth more than that corner case.
`include "../shared/mem_config.vh"

module vga_rom_shadow #(
    parameter int DEPTH = 2048
)(
    input  logic        wr_clk,
    input  logic        wr_en,
    input  logic [31:0] wr_addr,
    input  logic [31:0] wr_data,
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
    logic [ADDR_BITS-1:0] wr_word;
    logic [ADDR_BITS-1:0] rd_word;
    assign wr_word = wr_addr[ADDR_BITS+1:2];
    assign rd_word = rd_addr[ADDR_BITS+1:2];

    always_ff @(posedge wr_clk) begin
        if (wr_en)
            mem[wr_word] <= wr_data;
    end

    always_ff @(posedge rd_clk) begin
        rd_data <= mem[rd_word];
    end
endmodule
