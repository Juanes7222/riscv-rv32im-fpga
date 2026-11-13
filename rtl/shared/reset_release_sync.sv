// Assert reset without a clock; release it after two local rising edges.
module reset_release_sync (
    input  logic clk,
    input  logic async_reset_n,
    output logic reset_n
);
    (* async_reg = "true", preserve,
       altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED_IF_ASYNCHRONOUS" *)
    logic release_meta = 1'b0;
    (* async_reg = "true", preserve,
       altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED_IF_ASYNCHRONOUS" *)
    logic release_ready = 1'b0;

    always_ff @(posedge clk or negedge async_reset_n) begin
        if (!async_reset_n) begin
            release_meta  <= 1'b0;
            release_ready <= 1'b0;
        end else begin
            release_meta  <= 1'b1;
            release_ready <= release_meta;
        end
    end
    assign reset_n = release_ready;
endmodule
