// Instruction memory of the pipelined processor: M10K block RAM with a
// registered read (ADR 011 §3) and a write port for the program loader.
//
// The output register is the IF/ID boundary: the word read with the address
// presented in cycle N is the instruction decoded in cycle N+1, so the fetch
// costs no extra cycle and a redirect only loses the word that was being
// fetched.  The out-of-range mux sits after the output register, otherwise
// Quartus does not infer the block (same pattern as the single-cycle memory).
`include "../shared/mem_config.vh"

module instruction_memory_pipe #(
    parameter int unsigned IMEM_DEPTH = 16384
)(
    input  logic        clk,
    input  logic        fetch_en,   // 0 holds the output register (stall, step)
    input  logic [31:0] next_pc,    // PC of the instruction fetched this cycle
    output logic [31:0] instruction,
    // Write port of the program loader.  Only enabled while the CPU is
    // halted; wr_en is 0 during normal execution.
    input  logic        wr_en,
    input  logic [31:0] wr_addr,
    input  logic [31:0] wr_data
);

    localparam ADDR_BITS = $clog2(IMEM_DEPTH);

    (* ramstyle = "M10K" *) logic [31:0] mem [0:IMEM_DEPTH-1];

    initial begin
        `ifdef IMEM_FILE
            $readmemh(`IMEM_FILE, mem);
        `endif
    end

    always_ff @(posedge clk) begin
        if (wr_en)
            mem[wr_addr[ADDR_BITS+1:2]] <= wr_data;
    end

    // Indices kept out of the always_ff for Icarus compatibility.
    logic [ADDR_BITS-1:0] word_index;
    logic                 addr_out_of_bounds;
    assign word_index         = next_pc[ADDR_BITS+1:2];
    assign addr_out_of_bounds = (next_pc[31:ADDR_BITS+2] != 0);

    logic [31:0] mem_q;
    logic        oob_q;

    always_ff @(posedge clk) begin
        if (fetch_en) begin
            mem_q <= mem[word_index];
            oob_q <= addr_out_of_bounds;
        end
    end

    assign instruction = oob_q ? 32'h00000013 : mem_q;

endmodule
