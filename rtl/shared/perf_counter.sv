module perf_counters #(
    parameter logic   PIPELINE_MODE = 1'b0,
    parameter [31:0]  TOHOST_ADDR   = 32'h8000_1000
) (
    input  logic        clk,
    input  logic        rst_n,

    // Single-cycle: connect div_busy. Tie to 1'b0 when PIPELINE_MODE = 1.
    input  logic        div_busy,

    // Pipeline: connect valid_wb. Tie to 1'b0 when PIPELINE_MODE = 0.
    input  logic        valid_wb,

    // Shared inputs
    input  logic        dm_wr,
    input  logic [31:0] alu_res,

    // Outputs — all registered, tapped by SignalTap II (ADR 026)
    output logic [63:0] cycle_count,
    output logic [63:0] instr_retired,
    output logic        program_done
);

    logic frozen;
    logic tohost_hit;
    logic instr_retired_en;

    // tohost detection
    assign tohost_hit = dm_wr & (alu_res == TOHOST_ADDR);

    // no runtime mux on increment enable
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
            program_done  <= 1'b0;
            frozen        <= 1'b0;
        end else if (tohost_hit && !frozen) begin
            // Register program_done one cycle after tohost write.
            // cycle_count already reflects complete execution at this point.
            program_done <= 1'b1;
            frozen       <= 1'b1;
        end else if (!frozen) begin
            cycle_count   <= cycle_count + 64'h1;
            instr_retired <= instr_retired + {{63{1'b0}}, instr_retired_en};
        end
    end

endmodule