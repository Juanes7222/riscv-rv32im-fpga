// Instruction memory with asynchronous (combinational) read.
// Used by the single-cycle processor.  The pipelined processor uses
// instruction_memory_pipe.sv which provides M10K inference via
// synchronous-read RTL.
//
// M10K ROM inference on Cyclone V requires synchronous-read RTL
// (always_ff).  A purely combinational read cannot be placed in M10K
// blocks.  The single-cycle architecture needs combinational read,
// so this module targets logic-cell implementation.  Keep IMEM_DEPTH
// small enough that the array fits in the device.
`include "../shared/mem_config.vh"

module instruction_memory #(
    parameter int unsigned IMEM_DEPTH = 1024
)(
    input  logic [31:0] addr,
    output logic [31:0] instruction
);

    localparam ADDR_BITS = $clog2(IMEM_DEPTH);

    logic [31:0] mem [0:IMEM_DEPTH-1];

    initial begin
        `ifdef IMEM_FILE
            $readmemh(`IMEM_FILE, mem);
        `endif
    end

    // NOTE: load_imem/load_dmem debug tasks removed.
    // Quartus 25.1 parsed the hierarchical references inside
    // `ifndef SYNTHESIS, causing synthesis errors (aggregate value, u_imem/u_dmem
    // undeclared). Testbenches load .mem files via the initial block above.

    // Extract index outside always_comb to avoid Icarus constant-select bug
    logic [ADDR_BITS-1:0] word_index;
    assign word_index = addr[ADDR_BITS+1:2];

    logic addr_out_of_bounds;
    assign addr_out_of_bounds = (addr[31:ADDR_BITS+2] != 0);

    // Pure combinational read.  The mux is placed AFTER the array access
    // so tooling has the best chance of recognizing the memory pattern.
    logic [31:0] mem_read;
    assign mem_read = mem[word_index];

    assign instruction = addr_out_of_bounds ? 32'h00000013 : mem_read;

endmodule
