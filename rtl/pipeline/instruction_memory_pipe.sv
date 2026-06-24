// Synchronous-read instruction memory for pipelined processor.
// Provides COMBINATIONAL output so IF/ID captures the current value.
// The always_ff block is retained purely for M10K ROM inference;
// Quartus implements the ROM output as UNREGISTERED.
`include "../shared/mem_config.vh"

module instruction_memory_pipe #(
    parameter int unsigned IMEM_DEPTH = 16384
)(
    input  logic        clk,
    input  logic [31:0] addr,
    output logic [31:0] instruction
);

    localparam ADDR_BITS = $clog2(IMEM_DEPTH);

    (* ramstyle = "M10K" *) logic [31:0] mem [0:IMEM_DEPTH-1];

    initial begin
        `ifdef IMEM_FILE
            $readmemh(`IMEM_FILE, mem);
        `endif
    end

    // Word index extraction — keep outside always_ff for Icarus compat
    logic [ADDR_BITS-1:0] word_index;
    assign word_index = addr[ADDR_BITS+1:2];

    // Out-of-bounds detection
    logic addr_out_of_bounds;
    assign addr_out_of_bounds = (addr[31:ADDR_BITS+2] != 0);

    // ── Combinational output (what IF/ID captures) ────────────────
    // The array read is combinational; Quartus infers M10K ROM with
    // unregistered output.  This is the path IF/ID samples at posedge.

    assign instruction = addr_out_of_bounds ? 32'h00000013 : mem[word_index];

    // ── Registered read (triggers M10K inference) ─────────────────
    // The always_ff tells Quartus "memory read pattern here", which
    // causes M10K ROM inference.  The registered value itself is not
    // used — it exists solely to satisfy the synthesis pattern.
    // Quartus implements OUTDATA_REG_A = UNREGISTERED, so the M10K
    // output is combinational anyway.
    localparam logic [31:0] BUBBLE = 32'h00000013;
    logic [31:0] mem_read /* synthesis keep */ = BUBBLE;
    logic        oob_reg  /* synthesis keep */ = 1'b0;
    always_ff @(posedge clk) begin
        mem_read <= mem[word_index];
        oob_reg  <= addr_out_of_bounds;
    end

endmodule
