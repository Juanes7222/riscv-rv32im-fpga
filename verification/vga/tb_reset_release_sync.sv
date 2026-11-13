`timescale 1ns/1ps
module tb_reset_release_sync;
    logic clk = 0;
    logic async_reset_n = 0;
    wire reset_n;
    reset_release_sync dut (.*);
    always #5 clk = ~clk;

    task automatic release_and_check;
        begin
            #2 async_reset_n = 1;
            #1;
            if (reset_n !== 0) $fatal(1, "Reset released before a local edge");
            @(posedge clk); #0.1;
            if (reset_n !== 0) $fatal(1, "Reset released after only one edge");
            @(posedge clk); #0.1;
            if (reset_n !== 1) $fatal(1, "Reset did not release after two edges");
        end
    endtask

    initial begin
        #1;
        if (reset_n !== 0) $fatal(1, "Power-up reset must be asserted");
        release_and_check();
        #1 async_reset_n = 0;
        #0.1;
        if (reset_n !== 0) $fatal(1, "Assertion waited for a clock");
        release_and_check();
        #1 async_reset_n = 0;
        #1 async_reset_n = 1;
        #1 async_reset_n = 0;
        #0.1;
        if (reset_n !== 0) $fatal(1, "A short reset pulse was lost");
        release_and_check();
        $display("PASS: asynchronous assertion, local release and interrupted release");
        $finish;
    end
endmodule
