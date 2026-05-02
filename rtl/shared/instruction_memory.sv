module instruction_memory #(
   parameter int unsigned IMEM_DEPTH = 1024
)(
      input logic [31:0] addr,
      output logic [31:0] instruction
);

   localparam ADDR_BITS = $clog2(IMEM_DEPTH);

   logic [31:0] memory [0:IMEM_DEPTH-1];

   initial begin
      $readmemh("program.hex", memory);
   end

   always_comb begin
      if (addr[31:ADDR_BITS+2] != 0) begin
         instruction = 32'h00000013; // Return NOP for out-of-bounds access  
      end else begin
         instruction = memory[addr[ADDR_BITS+1:2]];
      end
   end
   
endmodule