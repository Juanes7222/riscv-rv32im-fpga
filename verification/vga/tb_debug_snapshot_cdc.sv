`timescale 1ns/1ps
module tb_debug_snapshot_cdc;
    logic src_clk = 0, dst_clk = 0;
    logic src_reset_n = 0, dst_reset_n = 0;
    logic [63:0] sequence_value = 0;
    wire [191:0] data_in = {sequence_value, ~sequence_value, sequence_value ^ 64'h123456789ABCDEF0};
    wire [191:0] data_out;
    wire data_valid;
    int received = 0;
    logic [191:0] previous_payload;
    logic previous_request;

    debug_snapshot_cdc #(.WIDTH(192)) dut (.*);
    always #12.5 src_clk = ~src_clk;
    initial begin
        #1.7;
        forever #6.734 dst_clk = ~dst_clk;
    end
    always @(negedge src_clk) sequence_value <= sequence_value + 64'h00000001FFFFFFFF;

    always @(posedge src_clk) begin
        if (dut.source_ready && previous_request && dut.request && !dut.ack_sync)
            if (dut.payload_hold !== previous_payload)
                $fatal(1, "Payload changed while waiting for acknowledgement");
        previous_payload <= dut.payload_hold;
        previous_request <= dut.request;
    end
    always @(posedge dst_clk) begin
        #0.1;
        if (data_valid) begin
            if (data_out[127:64] !== ~data_out[191:128] ||
                data_out[63:0] !== (data_out[191:128] ^ 64'h123456789ABCDEF0))
                $fatal(1, "Torn multiword snapshot");
            received++;
        end
    end

    initial begin
        #31 src_reset_n = 1;
        #19 dst_reset_n = 1;
        #7000;
        if (received < 10) $fatal(1, "Transfer did not make progress");
        // Either side can restart while the other clock continues.
        src_reset_n = 0;
        #83 src_reset_n = 1;
        #3000;
        dst_reset_n = 0;
        #41 dst_reset_n = 1;
        #3000;
        if (received < 30) $fatal(1, "Transfer did not recover after reset");
        // A stable completed result must eventually reach the console.
        force sequence_value = 64'h89ABCDEF01234567;
        #1000;
        if (data_out !== data_in) $fatal(1, "Final frozen counters did not arrive");
        $display("PASS: %0d coherent packets, independent resets and final convergence", received);
        $finish;
    end
    initial begin
        #20000;
        $fatal(1, "CDC test timed out");
    end
endmodule
