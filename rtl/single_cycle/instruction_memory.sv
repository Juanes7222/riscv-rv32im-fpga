// Instruction memory with synchronous (registered) read, inferred as M10K.
// Used by the single-cycle processor.  The pipelined processor uses
// instruction_memory_pipe.sv.
//
// The address port receives the NEXT pc, not the current one.  The array's
// address register therefore acts as the IF/ID boundary: the word read with
// the next pc at the end of cycle N is the instruction of cycle N+1, already
// available when it is executed.  The branch/jump target is computed
// combinationally in the same cycle, so no bubble is added and the CPI stays 1.
//
// M10K inference requires the read to be registered.  The out-of-range mux
// sits AFTER the output register: a mux in front of the array keeps Quartus
// from inferring the block (see vga_rom_shadow.sv).
`include "../shared/mem_config.vh"

module instruction_memory #(
    parameter int unsigned IMEM_DEPTH = 1024
)(
    input  logic        clk,
    input  logic        fetch_en,   // 0 holds the output register (DIV, step mode)
    input  logic [31:0] next_pc,
    output logic [31:0] instruction
);

    localparam ADDR_BITS = $clog2(IMEM_DEPTH);

    (* ramstyle = "M10K" *) logic [31:0] mem [0:IMEM_DEPTH-1];

    initial begin
        `ifdef IMEM_FILE
            $readmemh(`IMEM_FILE, mem);
        `endif
    end

    // Extract index outside always_ff to avoid Icarus constant-select bug
    logic [ADDR_BITS-1:0] word_index;
    logic                 addr_out_of_bounds;
    assign word_index         = next_pc[ADDR_BITS+1:2];
    assign addr_out_of_bounds = (next_pc[31:ADDR_BITS+2] != 0);

    // The output register is the fetch stage register: it holds the
    // instruction of the pc that the datapath is executing.  It lives in its
    // own always_ff so Quartus sees the plain RAM read pattern.
    logic [31:0] mem_q;

    always_ff @(posedge clk) begin
        if (fetch_en)
            mem_q <= mem[word_index];
    end

    // Registered with the word it belongs to, so the NOP stays aligned with
    // the instruction even across a stall.
    logic oob_q;

    always_ff @(posedge clk) begin
        if (fetch_en)
            oob_q <= addr_out_of_bounds;
    end

    assign instruction = oob_q ? 32'h0000_0013 : mem_q;

endmodule
