// Step mode: freeze the processor and release it for a single clock cycle.
//
// SW[9] (step_mode) requests the freeze, KEY[1] (key_step) releases the
// processor for exactly one cycle.  The instruction then advances by one
// stage and the console shows it travelling through the pipeline.
//
// The module only produces the freeze request.  Each design applies it to
// its own clock enables, so the clock itself is never gated.
module step_mode (
    input  logic clk,        // processor clock
    input  logic rst_n,      // active-low synchronous reset
    input  logic key_step,   // KEY[1], active high: 1 while the button is pressed
    input  logic step_mode,  // SW[9], active high: 1 freezes the processor
    output logic step_hold   // 1 while the processor is frozen
);

    // KEY[1] is asynchronous: four flops make the release edge detectable.
    // SW[9] is a switch: two flops are enough.
    logic [3:0] key_sync;
    logic [1:0] sw_sync;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            key_sync <= '0;
            sw_sync  <= '0;
        end else begin
            key_sync <= {key_sync[2:0], key_step};
            sw_sync  <= {sw_sync[0], step_mode};
        end
    end

    // One-cycle release request.  The synchronised key falls three clocks
    // after KEY[1] is released, so the pulse marks the end of the press.
    logic step_press;
    assign step_press = key_sync[3] & ~key_sync[2];

    // The request lasts exactly one cycle: the processor advances during it
    // and is frozen again on the next clock.
    logic step_run_q;
    always_ff @(posedge clk) begin
        if (!rst_n) step_run_q <= 1'b0;
        else        step_run_q <= step_press;
    end

    assign step_hold = sw_sync[1] & ~step_run_q;

endmodule
