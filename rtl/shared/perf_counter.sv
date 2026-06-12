module perf_counters #(
    parameter logic PIPELINE_MODE = 1'b0
) (
    input  logic        clk,
    input  logic        rst_n,

    // Single-cycle: connect div_busy. Tie to 1'b0 when PIPELINE_MODE = 1.
    input  logic        div_busy,

    // Pipeline: connect valid_wb. Tie to 1'b0 when PIPELINE_MODE = 0.
    input  logic        valid_wb,

    // Outputs - observed by cocotb via DUT ports; tapped by SignalTap II (ADR 026)
    output logic [63:0] cycle_count,
    output logic [63:0] instr_retired
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
            cycle_count   <= 64'h0;
            instr_retired <= 64'h0;
        end else begin
            cycle_count   <= cycle_count + 64'h1;
            instr_retired <= instr_retired + {{63{1'b0}}, instr_retired_en};
        end
    end

endmodule