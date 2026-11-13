// Four-phase bundled-data transfer. The source holds the entire payload
// until the destination acknowledges it and returns to the idle phase.
// SDC bounds the payload route; only the first control synchronizer stages
// are excluded from clock-to-clock timing analysis.
module debug_snapshot_cdc #(
    parameter int WIDTH = 32
) (
    input  logic src_clk,
    input  logic src_reset_n,
    input  logic [WIDTH-1:0] data_in,
    input  logic dst_clk,
    input  logic dst_reset_n,
    output logic [WIDTH-1:0] data_out,
    output logic data_valid
);
    logic transfer_reset_n;
    logic source_ready;
    logic destination_ready;
    assign transfer_reset_n = src_reset_n & dst_reset_n;
    reset_release_sync u_source_reset (
        .clk(src_clk), .async_reset_n(transfer_reset_n), .reset_n(source_ready)
    );
    reset_release_sync u_destination_reset (
        .clk(dst_clk), .async_reset_n(transfer_reset_n), .reset_n(destination_ready)
    );

    logic [WIDTH-1:0] payload_hold;
    logic request;
    logic acknowledge;
    (* async_reg = "true", preserve,
       altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED_IF_ASYNCHRONOUS" *)
    logic req_meta, req_sync;
    (* async_reg = "true", preserve,
       altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION FORCED_IF_ASYNCHRONOUS" *)
    logic ack_meta, ack_sync;

    always_ff @(posedge src_clk) begin
        if (!source_ready) begin
            ack_meta     <= 1'b0;
            ack_sync     <= 1'b0;
            request      <= 1'b0;
            payload_hold <= '0;
        end else begin
            ack_meta <= acknowledge;
            ack_sync <= ack_meta;
            if (!request && !ack_sync) begin
                payload_hold <= data_in;
                request <= 1'b1;
            end else if (request && ack_sync) begin
                request <= 1'b0;
            end
        end
    end

    always_ff @(posedge dst_clk) begin
        if (!destination_ready) begin
            req_meta    <= 1'b0;
            req_sync    <= 1'b0;
            acknowledge <= 1'b0;
            data_out    <= '0;
            data_valid  <= 1'b0;
        end else begin
            req_meta <= request;
            req_sync <= req_meta;
            data_valid <= 1'b0;
            if (req_sync && !acknowledge) begin
                data_out <= payload_hold;
                data_valid <= 1'b1;
                acknowledge <= 1'b1;
            end else if (!req_sync) begin
                acknowledge <= 1'b0;
            end
        end
    end
endmodule
