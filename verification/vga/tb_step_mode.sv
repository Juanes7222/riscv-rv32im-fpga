// Step-mode testbench: SW[9] freezes the processor and one KEY[1] press
// releases it for exactly one clock cycle, so the console shows a single
// instruction step instead of a value that changes a thousand times per
// second.
//
// The freeze is exercised through the clock enables the processor tops
// use: the pipeline stall net (pc_unit / if_id_register) and the
// single-cycle PC.  The VGA PLL and the memories are not needed, so the
// tops themselves are not instantiated.
module tb_step_mode;

    localparam int CLK_HALF_NS = 10;   // 50 MHz processor clock

    logic clk = 0;
    logic rst_n = 0;

    // Board inputs: KEY[1] (active high) and SW[9] (active high).
    logic key_step  = 0;
    logic step_mode = 0;

    // The freeze request produced by the step logic under test.
    logic step_hold;

    step_mode u_step (
        .clk       (clk),
        .rst_n     (rst_n),
        .key_step  (key_step),
        .step_mode (step_mode),
        .step_hold (step_hold)
    );

    // ── Pipeline side: the freeze is OR-ed into the hazard stall ─────
    logic        stall_hazard = 0;
    logic [31:0] pc;
    logic [31:0] id_pc;
    logic [31:0] id_instruction;

    pc_unit u_pc_unit (
        .clk           (clk),
        .rst           (~rst_n),
        .stall         (stall_hazard | step_hold),
        .branch_taken  (1'b0),
        .mask_pc_lsb   (1'b0),
        .branch_target (32'd0),
        .pc            (pc)
    );

    if_id_register u_if_id (
        .clk            (clk),
        .rst            (~rst_n),
        .stall          (stall_hazard | step_hold),
        .flush          (1'b0),
        .if_pc          (pc),
        .if_instruction (32'h00000013),
        .id_pc          (id_pc),
        .id_instruction (id_instruction)
    );

    // ── Single-cycle side: the PC holds while the processor is frozen ─
    logic [31:0] sc_pc;

    pc u_sc_pc (
        .clk         (clk),
        .rst_n       (rst_n),
        .branch      (1'b0),
        .mask_pc_lsb (1'b0),
        .alu_res     (32'd0),
        .div_busy    (1'b0),
        .trap_entry  (1'b0),
        .mret_exec   (1'b0),
        .trap_target (32'd0),
        .mepc_value  (32'd0),
        .step_hold   (step_hold),
        .pc          (sc_pc),
        .pc_plus4    ()
    );

    // ── Performance counters: they stop while the processor is frozen ─
    logic [63:0] cycle_count;
    logic [63:0] instr_retired;

    perf_counters u_counters (
        .clk                (clk),
        .rst_n              (rst_n),
        .enable             (~step_hold),
        .div_busy           (1'b0),
        .valid_wb           (1'b0),
        .program_done       (1'b0),
        .cycle_count        (cycle_count),
        .instr_retired      (instr_retired),
        .program_done_synced(),
        .cycles_at_done     (),
        .instr_at_done      ()
    );

    always #(CLK_HALF_NS) clk = ~clk;

    // One clock cycle, sampled one time unit after the rising edge.
    task automatic tick;
        @(posedge clk);
        #1;
    endtask

    logic [31:0] pc_frozen;
    logic [31:0] sc_pc_frozen;
    logic [31:0] id_pc_frozen;
    logic [63:0] cycles_frozen;
    logic [31:0] pc_prev;
    int          pc_advances;

    initial begin
        // ── Reset ────────────────────────────────────────────────────
        repeat (2) tick();
        rst_n = 1;

        // ── Anchor: the stall net is the clock enable of the pipeline ─
        tick();
        if (pc !== 32'd4) $fatal(1, "PC did not advance while running");
        if (sc_pc !== 32'd4) $fatal(1, "single-cycle PC did not advance while running");
        tick();
        if (pc !== 32'd8) $fatal(1, "PC did not advance while running");
        if (sc_pc !== 32'd8) $fatal(1, "single-cycle PC did not advance while running");
        if (cycle_count !== 64'd2) $fatal(1, "the cycle counter did not advance");

        stall_hazard = 1;
        tick();
        if (pc !== 32'd8) $fatal(1, "PC advanced while stalled");
        repeat (5) tick();
        if (pc !== 32'd8) $fatal(1, "PC advanced while stalled");
        stall_hazard = 0;
        tick();
        if (pc !== 32'd12) $fatal(1, "PC did not advance after the release");

        // ── SW[9] freezes the processor ──────────────────────────────
        step_mode = 1;
        repeat (3) tick();          // the switch synchroniser needs two cycles
        if (step_hold !== 1'b1) $fatal(1, "the freeze was not requested");

        pc_frozen    = pc;
        sc_pc_frozen = sc_pc;
        id_pc_frozen = id_pc;
        cycles_frozen = cycle_count;

        repeat (5) tick();
        if (pc !== pc_frozen)        $fatal(1, "the pipeline PC advanced while frozen");
        if (sc_pc !== sc_pc_frozen)  $fatal(1, "the single-cycle PC advanced while frozen");
        if (id_pc !== id_pc_frozen)  $fatal(1, "the IF/ID register advanced while frozen");
        if (cycle_count !== cycles_frozen) $fatal(1, "the cycle counter advanced while frozen");

        // ── One KEY[1] press releases the processor for one cycle ───
        key_step = 1;
        repeat (3) tick();          // the button is held
        key_step = 0;

        pc_advances = 0;
        pc_prev     = pc;
        repeat (8) begin
            tick();
            if (pc != pc_prev) pc_advances++;
            pc_prev = pc;
        end
        if (pc_advances != 1) $fatal(1, "the press advanced the PC %0d times instead of once",
                                     pc_advances);
        if (pc !== pc_frozen + 32'd4) $fatal(1, "the PC did not advance by one instruction");
        if (sc_pc !== sc_pc_frozen + 32'd4) $fatal(1, "the single-cycle PC did not advance");
        if (cycle_count !== cycles_frozen + 64'd1) $fatal(1, "the cycle counter did not advance once");

        // The processor is frozen again once the release cycle is over.
        repeat (4) tick();
        if (pc !== pc_frozen + 32'd4) $fatal(1, "the PC advanced after the release");
        if (sc_pc !== sc_pc_frozen + 32'd4) $fatal(1, "the single-cycle PC advanced after the release");
        if (cycle_count !== cycles_frozen + 64'd1) $fatal(1, "the cycle counter advanced after the release");

        $display("PASS");
        $finish;
    end
endmodule
