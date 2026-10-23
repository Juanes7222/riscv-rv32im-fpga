module perf_counters #(
    parameter logic PIPELINE_MODE = 1'b0
) (
    input  logic        clk,
    input  logic        rst_n,

    // enable: 0 freezes the counters (step mode).
    input  logic        enable,

    // Single-cycle: connect div_busy. Tie to 1'b0 when PIPELINE_MODE = 1.
    input  logic        div_busy,

    // Pipeline: connect valid_wb. Tie to 1'b0 when PIPELINE_MODE = 0.
    input  logic        valid_wb,

    // program_done: pulsed high when the benchmark writes to tohost.
    // Registered inside and exposed for SignalTap II capture.
    input  logic        program_done,

    // Outputs - observed by cocotb via DUT ports; tapped by SignalTap II (ADR 026)
    // (* keep *) prevents Quartus from pruning these signals when they are not
    // connected to top-level outputs (program_done_synced is wired to () in
    // both top-levels).  SignalTap II needs them visible in the netlist.
    output logic [63:0] cycle_count        /* synthesis keep */,
    output logic [63:0] instr_retired      /* synthesis keep */,
    output logic        program_done_synced /* synthesis keep */,  // registered for SignalTap trigger

    // Counters frozen at the instant the program wrote to tohost.  They are
    // the on-board counterpart of the values cocotb reports, so the console
    // shows the same numbers the simulation measured.
    output logic [63:0] cycles_at_done     /* synthesis keep */,
    output logic [63:0] instr_at_done      /* synthesis keep */
);

    logic instr_retired_en;

    generate
        if (PIPELINE_MODE == 1'b0)
            assign instr_retired_en = ~div_busy;
        else
            assign instr_retired_en = valid_wb;
    endgenerate

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cycle_count          <= 64'h0;
            instr_retired        <= 64'h0;
            program_done_synced  <= 1'b0;
            cycles_at_done       <= 64'h0;
            instr_at_done        <= 64'h0;
        end else if (enable) begin
            cycle_count          <= cycle_count + 64'h1;
            instr_retired        <= instr_retired + {{63{1'b0}}, instr_retired_en};
            program_done_synced  <= program_done_synced || program_done;
            // Freeze the counters when the program terminates.  The stored
            // value is the counter of the cycle in which the program wrote to
            // tohost, which is the instant cocotb samples.
            if (program_done) begin
                cycles_at_done <= cycle_count;
                instr_at_done  <= instr_retired;
            end
        end
    end

endmodule