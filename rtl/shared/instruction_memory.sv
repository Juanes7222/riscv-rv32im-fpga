`include "mem_config.vh"

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

   `ifndef SYNTHESIS
      task load_imem(input string filename);
         $readmemh(filename, u_imem.mem);
      endtask

      task load_dmem(input string filename);
         $readmemh(filename, u_dmem.mem);
      endtask
    `endif

    // Extract index outside always_comb to avoid Icarus constant-select bug
    logic [ADDR_BITS-1:0] word_index;
    assign word_index = addr[ADDR_BITS+1:2];

    logic addr_out_of_bounds;
    assign addr_out_of_bounds = (addr[31:ADDR_BITS+2] != 0);

    always_comb begin
        if (addr_out_of_bounds) begin
            instruction = 32'h00000013;
        end else begin
            instruction = mem[word_index];
        end
    end

endmodule