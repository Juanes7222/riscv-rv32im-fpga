module pc (
      input logic clk,
      input logic rst_n,
      input logic [31:0] next_pc,
      output logic [31:0] pc
);

   always_ff @(posedge clk or negedge rst_n) begin
      if (!rst_n) begin
         pc <= 32'h0000_0000; // Reset to address 0
      end else begin
         pc <= next_pc; // Update PC with the next address
      end
   end
   
endmodule