// Step mode: freeze the processor and release it for a single clock cycle.
//
// SW[9] (step_mode) requests the freeze, KEY[1] (key_step) releases the
// processor for exactly one cycle.  The instruction then advances by one
// stage and the console shows it travelling through the pipeline.
//
// The module only produces the freeze request.  Each design applies it to
// its own clock enables, so the clock itself is never gated.
//
// Button polarity and timing
// -------------------------
// key_step is the RAW KEY[1] pin level: the DE1-SoC push buttons are
// active low, so the pin is wired directly and needs no inversion.  The
// pin is 1 while the button is released and 0 while it is pressed.  The
// module detects the falling edge of the synchronised pin, so the step
// fires after the PRESS.
//
// Timing, counted in processor clocks from the clock that samples the
// press (clock 0):
//   clock 2: the synchronised key has fallen, the one-cycle release
//             request is asserted,
//   clock 3: the request is registered,
//   clock 4: the processor advances - the single clock in which the
//             freeze is released.  step_run_q is cleared at edge 4, so
//             step_hold goes high at edge 4 and the processor stays
//             frozen from that edge on.
module step_mode_ctrl (
    input  logic clk,        // processor clock
    input  logic rst_n,      // active-low synchronous reset
    input  logic key_step,   // KEY[1] raw pin, active low: 0 while pressed
    input  logic step_mode,  // SW[9], active high: 1 freezes the processor
    output logic step_hold   // 1 while the processor is frozen
);

    // KEY[1] is asynchronous: four flops make the press edge detectable.
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
    // after the press, so the pulse marks the press itself.
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
