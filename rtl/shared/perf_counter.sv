module perf_counters #(
    parameter logic [31:0] TOHOST_ADDR = 32'h8000_1000
) (
    input  logic        clk,
    input  logic        rst_n,

    // Single-cycle: tie valid_wb to 0, connect div_busy
    input  logic        div_busy,       // from alu_rv32im (single-cycle)

    // Pipeline: tie div_busy to 0, connect valid_wb
    input  logic        valid_wb,       // 1 when non-bubble instruction at WB (pipeline)

    // Shared inputs
    input  logic        dm_wr,
    input  logic [31:0] alu_res,

    // Mode selector: 0 = single-cycle, 1 = pipeline
    input  logic        pipeline_mode,

    // Outputs
    output logic [31:0] cycle_count,
    output logic [31:0] instr_retired,
    output logic        program_done    // combinational: pulses 1 cycle on tohost write
);

    logic        frozen;
    logic        instr_retired_en;

    // Combinational: tohost detection
    assign program_done    = dm_wr & (alu_res == TOHOST_ADDR);

    // Combinational: retire condition differs by mode
    assign instr_retired_en = pipeline_mode ? valid_wb : ~div_busy;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cycle_count   <= 32'b0;
            instr_retired <= 32'b0;
            frozen        <= 1'b0;
        end else if (program_done && !frozen) begin
            // Freeze on first tohost write; do not increment this cycle
            frozen        <= 1'b1;
        end else if (!frozen) begin
            // Saturating increment (no wrap-around)
            cycle_count   <= (cycle_count   == 32'hFFFF_FFFF) ? 32'hFFFF_FFFF
                                                               : cycle_count + 32'd1;
            instr_retired <= (instr_retired == 32'hFFFF_FFFF) ? 32'hFFFF_FFFF
                           : instr_retired_en                 ? instr_retired + 32'd1
                                                               : instr_retired;
        end
    end

endmodule