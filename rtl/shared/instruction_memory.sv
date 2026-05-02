module instruction_memory #(
   parameter int unsigned DEPTH = 1024,
   parameter string MEM_FILE = "program.mem"
)(
      input logic [31:0] addr,
      output logic [31:0] instruction
);

   localparam ADDR_BITS = $clog2(DEPTH);

   logic [31:0] memory [0:DEPTH-1];

   initial begin
      $readmemh(MEM_FILE, memory);
   end

   always_comb begin
      if (addr[31:ADDR_BITS+2] != 0) begin
         instruction = 32'h00002013; // Return NOP for out-of-bounds access  
      end else begin
         instruction = memory[addr[ADDR_BITS+1:2]];
      end
   end
   
endmodule