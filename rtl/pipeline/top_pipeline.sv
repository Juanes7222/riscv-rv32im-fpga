// Five-stage RV32IM pipelined processor top-level (RV32IM + Zicsr + trap handling).
// Shares instruction memory, data memory, ALU, register file, imm_gen,
// branch_unit, and csr_file with top_single_cycle without modification.
module top_pipeline #(
    parameter string IMEM_FILE  = "program.mem",
    parameter int    IMEM_DEPTH = 16384,
    parameter int    DMEM_DEPTH = 8192,
    parameter logic [31:0] TOHOST_ADDR = 32'h708  // riscv-tests tohost symbol address
)(
    input  logic        clk,        // 50 MHz - DE1-SoC PIN_AF14
    input  logic        rst_n,      // Active-low synchronous reset - KEY[0]
    input  logic        key_step,   // KEY[1] raw pin, active low: 0 while pressed
    input  logic        key_load,   // KEY[2] raw pin, active low: 0 while pressed (program load)
    input  logic [3:0]  sw,         // SW[0:3]: program selector for the loader
    input  logic        step_mode,  // SW[9], active high: freezes the processor
    output logic [9:0]  ledr,       // if_pc[9:0] - same convention as single-cycle
    output logic [6:0]  seven_seg_display0,
    output logic [6:0]  seven_seg_display1,
    output logic [6:0]  seven_seg_display2,
    output logic [6:0]  seven_seg_display3,
    output logic [6:0]  seven_seg_display4,
    output logic [6:0]  seven_seg_display5,

    // VGA outputs (720p60 text mode)
    output logic        vga_hsync,
    output logic        vga_vsync,
    output logic [7:0]  vga_r,
    output logic [7:0]  vga_g,
    output logic [7:0]  vga_b,
    output logic        vga_clock,
    output logic        vga_blank_n,
    output logic        vga_sync_n
);

    // Internal reset (active-high for modules that require it)            //

    logic rst;
    // Pulse the CPU reset right after the loader finishes copying a program,
    // so the PC restarts at 0 and the newly loaded program executes.  The
    // loader itself resets on the board reset (rst_n), so the pulse only
    // restarts the pipeline, not the loader state machine.
    logic        loader_load_done;
    logic        load_done_q;
    logic        loader_reset_pulse;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            load_done_q <= 1'b0;
        end else begin
            load_done_q <= loader_load_done;
        end
    end
    assign loader_reset_pulse = loader_load_done & ~load_done_q;

    // Power-on reset: the FPGA configures with KEY[0] released, so rst_n never
    // pulses by itself.  Without this the pipeline registers power up to 0
    // instead of the architectural bubble (0x13), and the retirement counter
    // counts three phantom 0x00000000 words before the first real instruction.
    // An external reset already leaves the CPU in a defined state, so it
    // satisfies the POR immediately and adds no cycles to a testbench.
    logic [4:0] por_cnt;
    logic       por_done;
    logic       rst_n_int;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            por_cnt  <= '0;
            por_done <= 1'b1;
        end else if (!por_done) begin
            por_cnt  <= por_cnt + 5'd1;
            if (por_cnt == 5'h1F)
                por_done <= 1'b1;
        end
    end

    assign rst_n_int = rst_n & por_done;   // CPU-domain reset

    assign rst = ~rst_n_int | loader_reset_pulse;

    // ALU operation localparams (for div gate)                            //

    localparam [4:0] ALU_DIV  = 5'b01110;
    localparam [4:0] ALU_DIVU = 5'b01111;
    localparam [4:0] ALU_REM  = 5'b10000;
    localparam [4:0] ALU_REMU = 5'b10001;

    localparam [1:0] WB_ALU = 2'b00;
    localparam [1:0] WB_MEM = 2'b01;
    localparam [1:0] WB_PC4 = 2'b10;
    localparam [1:0] WB_CSR = 2'b11;

    // IF stage signals                                                     //

    logic [31:0] if_pc;
    logic [31:0] if_instruction;

    // Address the instruction memory captures this cycle, and the fill flag
    // that keeps the ID stage empty until the first word is available.
    logic [31:0] imem_addr;
    logic [31:0] next_if_pc;
    logic        fetch_valid;

    // IF/ID register outputs                                               //

    logic [31:0] id_pc;
    logic [31:0] id_instruction;

    // ID decoded fields
    logic [4:0]  id_rs1_addr, id_rs2_addr, id_rd_addr;
    logic [31:0] id_rs1_data, id_rs2_data;
    logic [31:0] id_rs1_data_wb_fwd, id_rs2_data_wb_fwd;
    logic [1023:0] rf_dbg_regs;   // whole register file, for the VGA console
    logic [31:0] id_imm;

    // ID control signals
    logic        id_ru_wr;
    logic [2:0]  id_imm_src;
    logic [1:0]  id_alua_src;
    logic        id_alub_src;
    logic [4:0]  id_alu_op;
    logic [4:0]  id_br_op;
    logic        id_dm_wr;
    logic [2:0]  id_dm_ctrl;
    logic [1:0]  id_ru_data_wr_src;
    logic        id_trap_entry, id_mret_exec;
    logic [11:0] id_csr_addr;
    logic        id_csr_wr;
    logic [1:0]  id_csr_op;
    logic        id_csr_imm;

    // ID/EX register outputs                                               //

    logic [31:0] ex_pc;
    logic [31:0] ex_instruction;
    logic [31:0] ex_rs1_data, ex_rs2_data;
    logic [31:0] ex_imm;
    logic [4:0]  ex_rs1_addr, ex_rs2_addr, ex_rd_addr;
    logic        ex_ru_wr;
    logic [2:0]  ex_imm_src;
    logic [1:0]  ex_alua_src;
    logic        ex_alub_src;
    logic [4:0]  ex_alu_op;
    logic [4:0]  ex_br_op;
    logic        ex_dm_wr;
    logic [2:0]  ex_dm_ctrl;
    logic [1:0]  ex_ru_data_wr_src;
    logic        ex_trap_entry, ex_mret_exec;
    logic [11:0] ex_csr_addr;
    logic        ex_csr_wr;
    logic [1:0]  ex_csr_op;
    logic        ex_csr_imm;

    // EX stage internals                                                   //

    logic [31:0] ex_rs1_fwd, ex_rs2_fwd;
    logic [1:0]  fwd_a_sel, fwd_b_sel;
    logic [31:0] ex_alu_a, ex_alu_b;
    logic [31:0] ex_alu_result;
    logic [31:0] ex_alu_sum;      // adder result, free of the multiplier
    logic        ex_div_busy, ex_div_done;
    logic        ex_branch_taken, ex_mask_pc_lsb;
    logic [31:0] ex_pc_plus4;

    // Division detection - used in ID/EX stall logic (mirrors ADR 023)
    // ex_alu_op is checked directly; no separate ex_is_div signal needed.

    // EX/MEM register outputs                                              //

    logic [31:0] mem_alu_result;
    logic [31:0] mem_rs2_data;
    logic [31:0] mem_rs1_data;
    logic [31:0] mem_instruction;
    logic [4:0]  mem_rd_addr;
    logic [4:0]  mem_rs1_addr;
    logic        mem_ru_wr;
    logic        mem_dm_wr;
    logic [2:0]  mem_dm_ctrl;
    logic [1:0]  mem_ru_data_wr_src;
    logic [31:0] mem_pc_plus4;
    logic [31:0] mem_pc;
    logic        mem_trap_entry, mem_mret_exec;
    logic [11:0] mem_csr_addr;
    logic        mem_csr_wr;
    logic [1:0]  mem_csr_op;
    logic        mem_csr_imm;

    // MEM stage - DMEM registered output (aligned with MEM/WB outputs)
    logic [31:0] dmem_rd_data;

    // MEM/WB register outputs                                              //

    logic [31:0] wb_alu_result;
    logic [31:0] wb_dm_rd_data_unused;  // retained for MEM/WB port compat only
    logic [31:0] wb_rs1_data;
    logic [4:0]  wb_rd_addr;
    logic [4:0]  wb_rs1_addr;
    logic        wb_ru_wr;
    logic [1:0]  wb_ru_data_wr_src;
    logic [31:0] wb_pc_plus4;
    logic [31:0] wb_pc;
    logic [31:0] wb_instruction;
    logic        wb_trap_entry, wb_mret_exec;
    logic [11:0] wb_csr_addr;
    logic        wb_csr_wr;
    logic [1:0]  wb_csr_op;
    logic        wb_csr_imm;

    // WB writeback
    logic [31:0] wb_rd_data;

    // Division gate in WB (instruction arrives after 34-cycle stall,
    // so div_done pulse coincides with the cycle the result is used).
    // NOTE: div gating is applied at the register file write enable.
    // Because div_busy stalls the whole pipeline, the DIV instruction stays
    // in EX for 34 cycles. When div_done pulses, the stall drops and the
    // instruction advances to MEM/WB normally, so wb_ru_wr already reflects
    // the correct enable. No additional gating is needed in WB beyond wb_ru_wr.
    logic        wb_wr_en_gated;
    assign wb_wr_en_gated = wb_ru_wr;

    // CSR outputs                                                          //
    logic [31:0] csr_rdata;
    logic [31:0] trap_target;
    logic [31:0] mepc_value;

    // Hazard / flush control                                               //
    logic stall;
    logic branch_flush;
    logic trap_flush;
    logic flush;
    logic load_use_hazard;
    logic mem_raw_hazard;

    assign branch_flush = ex_branch_taken;
    assign trap_flush   = wb_trap_entry || wb_mret_exec;
    assign flush        = branch_flush || trap_flush;

    // Step mode: SW[9] freezes the pipeline, KEY[1] releases it for one
    // cycle.  The freeze is OR-ed into the clock enables of the pipeline
    // registers, never into the clock itself.
    logic step_hold;

    // Power-on pause: hold the processor for a few cycles after reset releases,
    // so the initial state (PC=0, first instruction fetch) is visible on the
    // console before execution begins.  Independent of step_mode/SW[9].
    logic [3:0] power_on_pause_cnt;
    logic       power_on_pause;
    logic       step_hold_effective;
    logic       program_done;          // sticky HALTED flag, set at tohost write

    always_ff @(posedge clk) begin
        if (!rst_n_int)
            power_on_pause_cnt <= 4'd0;
        else if (power_on_pause_cnt != 4'd15)
            power_on_pause_cnt <= power_on_pause_cnt + 4'd1;
    end

    assign power_on_pause = (power_on_pause_cnt < 4'd4);
    // The pipeline keeps running after the tohost write, exactly like the
    // single-cycle: freezing it in MEM would drop the instructions still in
    // flight (and the benchmark's tail jump).  Only the performance counters
    // stop, which is what program_done gates at the perf_counters instance.
    assign step_hold_effective = step_hold | power_on_pause;

    step_mode_ctrl u_step_mode (
        .clk       (clk),
        .rst_n     (rst_n_int),
        .key_step  (key_step),
        .step_mode (step_mode),
        .step_hold (step_hold)
    );

    // Clock enable of the IF stage: the hazard stall plus the step freeze.
    // A pending trap still overrides the hazard stall, but not the freeze:
    // the pipeline must not move until the user releases it.
    logic pipe_stall;
    assign pipe_stall = (stall && !trap_flush) || step_hold_effective;

    // While the pipeline is frozen no flush may be applied: the flush
    // signals are combinational functions of the held state, so they would
    // destroy the frozen instructions.  The pending flush is applied on the
    // release cycle, when the pipeline advances again.

    // Performance counters                                                 //
    logic [63:0] cycle_count;
    logic [63:0] instr_retired;
    logic [63:0] cycles_at_done;
    logic [63:0] instr_at_done;

    // valid_wb: a real instruction retires in WB when it is not a bubble
    // and the WB stage is advancing.
    //
    // The counter must count every executed instruction, including the
    // branches and the stores, so that the CPI of the pipeline is defined
    // the same way as the CPI of the single-cycle (ADR 024).  Requiring
    // wb_ru_wr would exclude them and inflate the CPI.
    //
    // The division stall holds the MEM/WB register, so the instruction
    // that is already in WB would be counted again on every cycle of the
    // stall.  The division makes the pipeline advance flag false.
    logic valid_wb;
    assign valid_wb = (wb_instruction != 32'h00000013) && !ex_div_busy;

    // program_done: detect tohost write in MEM stage (ADR 026).
    // A store of value 1 to TOHOST_ADDR signals benchmark completion.
    // The pulse is the condition itself: the counters are frozen in the
    // cycle that carries the store into the register file, which is the
    // instant cocotb samples.
    logic program_done_pulse;
    assign program_done_pulse = mem_dm_wr && (mem_alu_result == TOHOST_ADDR)
                             && (mem_rs2_data == 32'd1);

    // Registered copy for the console and the SignalTap II trigger.
    always_ff @(posedge clk) begin
        if (!rst_n_int) begin
            program_done <= 1'b0;
        end else if (program_done_pulse) begin
            program_done <= 1'b1;
        end
    end

    perf_counters #(
        .PIPELINE_MODE (1'b1)
    ) u_perf (
        .clk                  (clk),
        .rst_n                (rst_n_int),
        .enable               (~step_hold_effective & ~program_done),
        .div_busy             (ex_div_busy),
        .valid_wb             (valid_wb),
        .program_done_pulse   (program_done_pulse),
        .cycle_count          (cycle_count),
        .instr_retired        (instr_retired),
        .program_done_synced  (),
        .cycles_at_done       (cycles_at_done),
        .instr_at_done        (instr_at_done)
    );

    // Board I/O                                                            //
    assign ledr = if_pc[9:0];

    // 7-segment displays show the instruction in WB (the committed instruction)
    seven_segment u_seven_seg0 (.val(wb_instruction[3:0]),   .display(seven_seg_display0));
    seven_segment u_seven_seg1 (.val(wb_instruction[7:4]),   .display(seven_seg_display1));
    seven_segment u_seven_seg2 (.val(wb_instruction[11:8]),  .display(seven_seg_display2));
    seven_segment u_seven_seg3 (.val(wb_instruction[15:12]), .display(seven_seg_display3));
    seven_segment u_seven_seg4 (.val(wb_instruction[19:16]), .display(seven_seg_display4));
    seven_segment u_seven_seg5 (.val(wb_instruction[23:20]), .display(seven_seg_display5));

// synthesis translate_off
   `ifndef SYNTHESIS
      // The waveform dump is disabled by default: a long benchmark run
      // writes gigabytes and becomes I/O bound.  Compile with -DDUMP_VCD
      // when the waveform is needed.
      `ifndef NO_VCD
      initial begin
         $dumpfile("dump.vcd");
         $dumpvars(0, top_pipeline);
      end
      `endif
   `endif
// synthesis translate_on

    // IF stage
    // PC redirect target mux: trap (WB) > branch/jump (EX) > sequential
    logic [31:0] pc_redirect_target;
    always_comb begin
        if (trap_flush)
            pc_redirect_target = wb_mret_exec ? mepc_value : trap_target;
        else
            pc_redirect_target = {ex_alu_sum[31:1],
                                  ex_mask_pc_lsb ? 1'b0 : ex_alu_sum[0]};
    end

    pc_unit u_pcunit (
        .clk           (clk),
        .rst           (rst),
        .stall         (pipe_stall),
        .fetch_valid   (fetch_valid),
        .branch_taken  (branch_flush || trap_flush),
        .mask_pc_lsb   (1'b0),              // masking already applied above
        .branch_target (pc_redirect_target),
        .pc            (if_pc),
        .next_pc       (next_if_pc)
    );

    // IMEM address: the word read with next_if_pc at the end of this cycle is
    // the instruction of the pc the datapath executes next cycle.  Until the
    // first word is captured the PC is held at the reset vector, so the
    // address presented is the vector itself.
    assign imem_addr = fetch_valid ? next_if_pc : if_pc;

    // Program loader: escribe en imem/dmem sólo con CPU detenido
    logic        loader_imem_wr_en;
    logic [31:0] loader_imem_wr_addr;
    logic [31:0] loader_imem_wr_data;
    logic        loader_dmem_wr_en;
    logic [31:0] loader_dmem_wr_addr;
    logic [31:0] loader_dmem_wr_data;

    program_loader #(
        .IMEM_DEPTH (IMEM_DEPTH),
        .DMEM_DEPTH (DMEM_DEPTH)
    ) u_loader (
        .clk          (clk),
        .rst_n        (rst_n),
        .step_hold    (step_hold_effective),
        .prog_sel     (sw[3:0]),
        .key_load     (key_load),
        .load_done    (loader_load_done),
        .imem_wr_addr (loader_imem_wr_addr),
        .imem_wr_data (loader_imem_wr_data),
        .imem_wr_en   (loader_imem_wr_en),
        .dmem_wr_addr (loader_dmem_wr_addr),
        .dmem_wr_data (loader_dmem_wr_data),
        .dmem_wr_en   (loader_dmem_wr_en)
    );

    instruction_memory_pipe #(
        .IMEM_DEPTH (IMEM_DEPTH)
    ) u_imem (
        .clk         (clk),
        .fetch_en    (~pipe_stall),
        .next_pc     (imem_addr),
        .instruction (if_instruction),
        .wr_en       (loader_imem_wr_en),
        .wr_addr     (loader_imem_wr_addr),
        .wr_data     (loader_imem_wr_data)
    );

    // IF/ID boundary: the output register of the instruction memory is the
    // instruction of the pc that ID decodes, and id_pc is registered with the
    // same address, so both describe the same word.  There is no extra
    // register here: the branch redirect is resolved through next_if_pc, so a
    // taken branch costs one cycle (the wrong-path word in ID) instead of two.
    always_ff @(posedge clk) begin
        if (rst) begin
            fetch_valid <= 1'b0;
            id_pc       <= '0;
        end else if (!pipe_stall) begin
            fetch_valid <= 1'b1;
            id_pc       <= imem_addr;
        end
    end

    assign id_instruction = fetch_valid ? if_instruction : 32'h00000013;

    // ID stage                                                             //
    assign id_rs1_addr = id_instruction[19:15];
    assign id_rs2_addr = id_instruction[24:20];
    assign id_rd_addr  = id_instruction[11:7];

    register_file u_rf (
        .clk      (clk),
        .rst      (rst),           // active-high, matches single-cycle .rst(~rst_n)
        .rs1_addr (id_rs1_addr),
        .rs2_addr (id_rs2_addr),
        .rd_addr  (wb_rd_addr),
        .rd_data  (wb_rd_data),
        .wr_en    (wb_wr_en_gated & ~step_hold_effective),
        .rs1_data (id_rs1_data),
        .rs2_data (id_rs2_data),
        .dbg_regs (rf_dbg_regs)
    );

    // WB-to-ID forwarding: when the producer is in WB, the register file still
    // exposes the old value because the write is synchronous.  Capture the
    // new value directly into ID/EX so the consumer sees it without stalling.
    always_comb begin
        id_rs1_data_wb_fwd = (wb_ru_wr && (wb_rd_addr != 5'b0) && (wb_rd_addr == id_rs1_addr))
                              ? wb_rd_data : id_rs1_data;
        id_rs2_data_wb_fwd = (wb_ru_wr && (wb_rd_addr != 5'b0) && (wb_rd_addr == id_rs2_addr))
                              ? wb_rd_data : id_rs2_data;
    end

    imm_gen u_imm_gen (
        .instruction (id_instruction),
        .imm_src     (id_imm_src),
        .imm_out     (id_imm)
    );

    control_unit u_ctrl (
        .opcode         (id_instruction[6:0]),
        .funct3         (id_instruction[14:12]),
        .funct7         (id_instruction[31:25]),
        .instr_31_20    (id_instruction[31:20]),
        .ru_wr          (id_ru_wr),
        .imm_src        (id_imm_src),
        .alua_src       (id_alua_src),
        .alub_src       (id_alub_src),
        .alu_op         (id_alu_op),
        .br_op          (id_br_op),
        .dm_wr          (id_dm_wr),
        .dm_ctrl        (id_dm_ctrl),
        .ru_data_wr_src (id_ru_data_wr_src),
        .trap_entry     (id_trap_entry),
        .mret_exec      (id_mret_exec),
        .csr_addr       (id_csr_addr),
        .csr_wr         (id_csr_wr),
        .csr_op         (id_csr_op),
        .csr_imm        (id_csr_imm)
    );

    // Hazard detection unit                                                //
    hazard_detection_unit u_hdu (
        .id_rs1_addr            (id_rs1_addr),
        .id_rs2_addr            (id_rs2_addr),
        .ex_rd_addr             (ex_rd_addr),
        .ex_ru_data_wr_src      (ex_ru_data_wr_src),
        .mem_rd_addr            (mem_rd_addr),
        .mem_ru_wr              (mem_ru_wr),
        .mem_ru_data_wr_src     (mem_ru_data_wr_src),
        .div_busy               (ex_div_busy),
        .stall                  (stall),
        .load_use               (load_use_hazard),
        .mem_raw                (mem_raw_hazard)
    );

    // ID/EX flush: bubble on branch, trap, load-use and mem-raw.
    //
    // A load-use hazard costs two cycles: the load advances to MEM while the
    // consumer waits in ID, and the consumer then reads the value from
    // MEM/WB.  Both cycles have to keep the consumer in ID, and the IF/ID is
    // held for that.  The ID/EX register must not capture the consumer while
    // it is still in the IF/ID, or the consumer would be executed twice, so a
    // bubble is inserted instead.  Holding the ID/EX would duplicate the
    // instruction that is in the EX stage instead, because the EX/MEM
    // register captures it at the same clock edge.
    //
    // The div stall holds the ID/EX (so the div stays in EX for 34 cycles).
    // The step freeze suppresses the bubbles: they are combinational
    // functions of the held state and would destroy the frozen instruction.
    logic id_ex_flush;
    assign id_ex_flush = (flush || load_use_hazard || mem_raw_hazard) & ~step_hold_effective;

    // ID/EX register                                                       //
    // flush: id_ex_flush (branch/trap/load-use). stall: only on div_busy
    // (the div must stay in EX for 34 cycles; load-use does NOT stall here
    // because the load needs to advance to MEM).
    id_ex_register u_id_ex (
        .clk               (clk),
        .rst               (rst),
        .flush             (id_ex_flush),
        .stall             (ex_div_busy || step_hold_effective),
        .id_pc             (id_pc),
        .id_instruction    (id_instruction),
        .id_rs1_data       (id_rs1_data_wb_fwd),
        .id_rs2_data       (id_rs2_data_wb_fwd),
        .id_imm            (id_imm),
        .id_rs1_addr       (id_rs1_addr),
        .id_rs2_addr       (id_rs2_addr),
        .id_rd_addr        (id_rd_addr),
        .id_ru_wr          (id_ru_wr),
        .id_imm_src        (id_imm_src),
        .id_alua_src       (id_alua_src),
        .id_alub_src       (id_alub_src),
        .id_alu_op         (id_alu_op),
        .id_br_op          (id_br_op),
        .id_dm_wr          (id_dm_wr),
        .id_dm_ctrl        (id_dm_ctrl),
        .id_ru_data_wr_src (id_ru_data_wr_src),
        .id_trap_entry     (id_trap_entry),
        .id_mret_exec      (id_mret_exec),
        .id_csr_addr       (id_csr_addr),
        .id_csr_wr         (id_csr_wr),
        .id_csr_op         (id_csr_op),
        .id_csr_imm        (id_csr_imm),
        .ex_pc             (ex_pc),
        .ex_instruction    (ex_instruction),
        .ex_rs1_data       (ex_rs1_data),
        .ex_rs2_data       (ex_rs2_data),
        .ex_imm            (ex_imm),
        .ex_rs1_addr       (ex_rs1_addr),
        .ex_rs2_addr       (ex_rs2_addr),
        .ex_rd_addr        (ex_rd_addr),
        .ex_ru_wr          (ex_ru_wr),
        .ex_imm_src        (ex_imm_src),
        .ex_alua_src       (ex_alua_src),
        .ex_alub_src       (ex_alub_src),
        .ex_alu_op         (ex_alu_op),
        .ex_br_op          (ex_br_op),
        .ex_dm_wr          (ex_dm_wr),
        .ex_dm_ctrl        (ex_dm_ctrl),
        .ex_ru_data_wr_src (ex_ru_data_wr_src),
        .ex_trap_entry     (ex_trap_entry),
        .ex_mret_exec      (ex_mret_exec),
        .ex_csr_addr       (ex_csr_addr),
        .ex_csr_wr         (ex_csr_wr),
        .ex_csr_op         (ex_csr_op),
        .ex_csr_imm        (ex_csr_imm)
    );

    // EX stage                                                             //
    assign ex_pc_plus4 = ex_pc + 32'd4;

    forwarding_unit u_fwd (
        .ex_rs1_addr (ex_rs1_addr),
        .ex_rs2_addr (ex_rs2_addr),
        .mem_rd_addr (mem_rd_addr),
        .mem_ru_wr   (mem_ru_wr),
        .wb_rd_addr  (wb_rd_addr),
        .wb_ru_wr    (wb_ru_wr),
        .fwd_a_sel   (fwd_a_sel),
        .fwd_b_sel   (fwd_b_sel)
    );

    // Forwarded rs1 value
    always_comb begin
        unique case (fwd_a_sel)
            2'b10:   ex_rs1_fwd = mem_alu_result;
            2'b01:   ex_rs1_fwd = wb_rd_data;
            default: ex_rs1_fwd = ex_rs1_data;
        endcase
    end

    // Forwarded rs2 value (also feeds stores and CSR zimm path)
    always_comb begin
        unique case (fwd_b_sel)
            2'b10:   ex_rs2_fwd = mem_alu_result;
            2'b01:   ex_rs2_fwd = wb_rd_data;
            default: ex_rs2_fwd = ex_rs2_data;
        endcase
    end

    // ALU operand A: forwarded rs1 / PC / zero
    always_comb begin
        unique case (ex_alua_src)
            2'b01:   ex_alu_a = ex_pc;
            2'b10:   ex_alu_a = 32'd0;
            default: ex_alu_a = ex_rs1_fwd;
        endcase
    end

    // ALU operand B: forwarded rs2 or immediate
    assign ex_alu_b = ex_alub_src ? ex_imm : ex_rs2_fwd;

    alu_rv32im u_alu (
        .clk     (clk),
        .rst_n   (rst_n_int),          // alu_rv32im uses active-low rst_n directly
        .hold    (1'b0),           // the divider is not part of the freeze
        .a       (ex_alu_a),
        .b       (ex_alu_b),
        .alu_op  (ex_alu_op),
        .alu_res (ex_alu_result),
        .alu_sum (ex_alu_sum),
        .div_busy(ex_div_busy),
        .div_done(ex_div_done)
    );

    // Branch unit receives forwarded operands (ADR 007)
    branch_unit u_bu (
        .rs1_data    (ex_rs1_fwd),
        .rs2_data    (ex_rs2_fwd),
        .br_op       (ex_br_op),
        .branch      (ex_branch_taken),
        .mask_pc_lsb (ex_mask_pc_lsb)
    );

    // EX/MEM register                                                      //
    // flush: driven by trap_flush only. A taken branch in EX is the
    // correct instruction (not a younger one), so it advances to MEM
    // normally. A trap in WB must invalidate the EX-stage instruction
    // (one cycle younger than the trap), so EX/MEM gets bubbled.
    ex_mem_register u_ex_mem (
        .clk                (clk),
        .rst                (rst),
        .stall              (ex_div_busy || step_hold_effective),
        .flush              (trap_flush & ~step_hold_effective),
        .ex_alu_result      (ex_alu_result),
        .ex_rs2_data_fwd    (ex_rs2_fwd),
        .ex_rs1_data_fwd    (ex_rs1_fwd),
        .ex_instruction     (ex_instruction),
        .ex_rd_addr         (ex_rd_addr),
        .ex_ru_wr           (ex_ru_wr),
        .ex_dm_wr           (ex_dm_wr),
        .ex_dm_ctrl         (ex_dm_ctrl),
        .ex_ru_data_wr_src  (ex_ru_data_wr_src),
        .ex_pc_plus4        (ex_pc_plus4),
        .ex_pc              (ex_pc),
        .ex_trap_entry      (ex_trap_entry),
        .ex_mret_exec       (ex_mret_exec),
        .ex_csr_addr        (ex_csr_addr),
        .ex_csr_wr          (ex_csr_wr),
        .ex_csr_op          (ex_csr_op),
        .ex_csr_imm         (ex_csr_imm),
        .ex_rs1_addr        (ex_rs1_addr),
        .mem_alu_result     (mem_alu_result),
        .mem_rs2_data       (mem_rs2_data),
        .mem_rs1_data       (mem_rs1_data),
        .mem_instruction    (mem_instruction),
        .mem_rd_addr        (mem_rd_addr),
        .mem_ru_wr          (mem_ru_wr),
        .mem_dm_wr          (mem_dm_wr),
        .mem_dm_ctrl        (mem_dm_ctrl),
        .mem_ru_data_wr_src (mem_ru_data_wr_src),
        .mem_pc_plus4       (mem_pc_plus4),
        .mem_pc             (mem_pc),
        .mem_trap_entry     (mem_trap_entry),
        .mem_mret_exec      (mem_mret_exec),
        .mem_csr_addr       (mem_csr_addr),
        .mem_csr_wr         (mem_csr_wr),
        .mem_csr_op         (mem_csr_op),
        .mem_csr_imm        (mem_csr_imm),
        .mem_rs1_addr       (mem_rs1_addr)
    );

    // MEM stage                                                            //
    // DMEM synchronous read: rd_data is registered (captured at posedge),
    // naturally aligned with MEM/WB control outputs in the WB stage.
    logic [3:0]  dmem_dbg_wr_be;
    logic [31:0] dmem_dbg_wr_data;

    // DMEM write mux: CPU during execution, loader when CPU is halted.
    logic        dmem_wr_eff;
    logic [31:0] dmem_addr_eff;
    logic [31:0] dmem_wdata_eff;
    logic [2:0]  dm_ctrl_eff;

    assign dmem_wr_eff   = mem_dm_wr | loader_dmem_wr_en;
    assign dmem_addr_eff = loader_dmem_wr_en ? loader_dmem_wr_addr : mem_alu_result;
    assign dmem_wdata_eff= loader_dmem_wr_en ? loader_dmem_wr_data : mem_rs2_data;
    assign dm_ctrl_eff   = loader_dmem_wr_en ? 3'b100 : mem_dm_ctrl;

    data_memory_pipe #(
        .DMEM_DEPTH (DMEM_DEPTH)
    ) u_dmem (
        .clk        (clk),
        .addr       (dmem_addr_eff),
        .wr_data    (dmem_wdata_eff),
        .dm_wr      (dmem_wr_eff),
        .dm_ctrl    (dm_ctrl_eff),
        .rd_data    (dmem_rd_data),
        .dbg_wr_be  (dmem_dbg_wr_be),
        .dbg_wr_data(dmem_dbg_wr_data)
    );

    // VGA shadow: mirrors both CPU and loader writes.
    logic        shadow_wr_en;
    logic [31:0] shadow_wr_addr;
    logic [3:0]  shadow_wr_be;
    logic [31:0] shadow_wr_data;
    assign shadow_wr_en   = mem_dm_wr | loader_dmem_wr_en;
    assign shadow_wr_addr = loader_dmem_wr_en ? loader_dmem_wr_addr : mem_alu_result;
    assign shadow_wr_be   = loader_dmem_wr_en ? 4'b1111 : dmem_dbg_wr_be;
    assign shadow_wr_data = loader_dmem_wr_en ? loader_dmem_wr_data : dmem_dbg_wr_data;

    // MEM/WB register                                                      //
    // stall: holds current contents during div stall. The trap itself
    // is in WB when trap_flush is asserted, so the trap must be allowed
    // to commit normally - MEM/WB is not flushed.
    // Note: dm_rd_data bypasses MEM/WB; the DMEM registered output feeds
    // the WB mux directly.  mem_dm_rd_data is tied to 0 for port compat.
    mem_wb_register u_mem_wb (
        .clk                (clk),
        .rst                (rst),
        .stall              (ex_div_busy || step_hold_effective),
        .mem_alu_result     (mem_alu_result),
        .mem_dm_rd_data     ('0),
        .mem_rs1_data       (mem_rs1_data),
        .mem_instruction    (mem_instruction),
        .mem_rd_addr        (mem_rd_addr),
        .mem_ru_wr          (mem_ru_wr),
        .mem_ru_data_wr_src (mem_ru_data_wr_src),
        .mem_pc_plus4       (mem_pc_plus4),
        .mem_pc             (mem_pc),
        .mem_trap_entry     (mem_trap_entry),
        .mem_mret_exec      (mem_mret_exec),
        .mem_csr_addr       (mem_csr_addr),
        .mem_csr_wr         (mem_csr_wr),
        .mem_csr_op         (mem_csr_op),
        .mem_csr_imm        (mem_csr_imm),
        .mem_rs1_addr       (mem_rs1_addr),
        .wb_alu_result      (wb_alu_result),
        .wb_dm_rd_data      (wb_dm_rd_data_unused),
        .wb_rs1_data        (wb_rs1_data),
        .wb_instruction     (wb_instruction),
        .wb_rd_addr         (wb_rd_addr),
        .wb_ru_wr           (wb_ru_wr),
        .wb_ru_data_wr_src (wb_ru_data_wr_src),
        .wb_pc_plus4        (wb_pc_plus4),
        .wb_pc              (wb_pc),
        .wb_trap_entry      (wb_trap_entry),
        .wb_mret_exec       (wb_mret_exec),
        .wb_csr_addr        (wb_csr_addr),
        .wb_csr_wr          (wb_csr_wr),
        .wb_csr_op          (wb_csr_op),
        .wb_csr_imm         (wb_csr_imm),
        .wb_rs1_addr        (wb_rs1_addr)
    );

    // WB stage                                                             //

    // CSR write-enable gating (mirrors single-cycle ADR 027 logic):
    // CSRRS (csr_op==01) and CSRRC (csr_op==10) with rs1=x0 must not
    // write the CSR. For immediate forms, the equivalent is zimm=0 (rs1_addr==0).
    logic wb_csr_wr_gated;
    always_comb begin
        if (!wb_csr_wr) begin
            wb_csr_wr_gated = 1'b0;
        end else if (wb_csr_imm) begin
            // CSRRWI always writes; CSRRSI/CSRRCI skip write when zimm==0
            wb_csr_wr_gated = (wb_csr_op == 2'b00) || (wb_rs1_addr != 5'b0);
        end else begin
            // CSRRW always writes; CSRRS/CSRRC skip write when rs1==x0
            wb_csr_wr_gated = (wb_csr_op == 2'b00) || (wb_rs1_addr != 5'b0);
        end
    end

    // CSR write data: zimm or rs1 value (mirrors single-cycle assign csr_wdata)
    logic [31:0] wb_csr_wdata;
    assign wb_csr_wdata = wb_csr_imm
                          ? {27'b0, wb_rs1_addr}   // zero-extended zimm[4:0]
                          : wb_rs1_data;            // forwarded rs1 register value

    csr_file u_csr (
        .clk        (clk),
        .rst_n      (rst_n_int),
        .csr_addr   (wb_csr_addr),
        .csr_wdata  (wb_csr_wdata),
        .csr_wr     (wb_csr_wr_gated & ~step_hold_effective),
        .csr_op     (wb_csr_op),
        .csr_rdata  (csr_rdata),
        .trap_entry (wb_trap_entry),
        .trap_pc    (wb_pc),           // mepc = PC of the trapping instruction (ECALL)
        .mret_exec  (wb_mret_exec),
        .trap_target(trap_target),
        .mepc_value (mepc_value)
    );

    // WB writeback data mux
    always_comb begin
        wb_rd_data = wb_alu_result;
        unique case (wb_ru_data_wr_src)
            WB_MEM:  wb_rd_data = dmem_rd_data;
            WB_PC4:  wb_rd_data = wb_pc_plus4;
            WB_CSR:  wb_rd_data = csr_rdata;
            default: wb_rd_data = wb_alu_result;
        endcase
    end

    // wb_instruction is now driven by the mem_wb_register via the new
    // mem_instruction pipeline field. See ex_mem_register.sv and
    // mem_wb_register.sv for the propagation logic.

    // -----------------------------------------------------------------
    // VGA text-mode visualization (720p60)
    // -----------------------------------------------------------------
    logic        vga_pixel_clk;
    logic        pll_locked;
    logic        vmem_wr_en;
    logic [12:0] vmem_wr_addr;
    logic [15:0] vmem_wr_data;
    logic [12:0] vmem_rd_addr;
    logic [15:0] vmem_rd_data;

    assign vga_clock   = vga_pixel_clk;
    assign vga_blank_n = vga_video_on;
    assign vga_sync_n  = 1'b0;

    vga_pll u_vga_pll (
        .clk_in  (clk),
        .rst_in  (~rst_n),
        .clk_out (vga_pixel_clk),
        .locked  (pll_locked)
    );

    logic [10:0] vga_hcount;
    logic [9:0]  vga_vcount;
    logic        vga_video_on;

    // System reset synchronized into the pixel-clock domain.  The controller
    // uses a synchronous reset, so the counters start from a known state.
    logic [1:0]  vga_rst_sync;
    logic        vga_rst;

    always_ff @(posedge vga_pixel_clk) begin
        vga_rst_sync <= {vga_rst_sync[0], ~rst_n};
    end

    assign vga_rst = vga_rst_sync[1];

    vga_controller_1280x720 u_vga (
        .clk      (vga_pixel_clk),
        .reset    (vga_rst),
        .hsync    (vga_hsync),
        .vsync    (vga_vsync),
        .hcount   (vga_hcount),
        .vcount   (vga_vcount),
        .video_on (vga_video_on)
    );

    logic [13:0] vmem_char_addr;

    assign vmem_char_addr = ({8'd0, vga_vcount[9:4]} * 14'd160) + {6'd0, vga_hcount[10:3]};

    // Blanking addresses rows past the 7200-cell framebuffer; M10K reads
    // outside the array are undefined, so fold them back to a valid cell.
    assign vmem_rd_addr = (vmem_char_addr >= 14'd7200) ? 13'd0 : vmem_char_addr[12:0];

    video_memory u_vmem (
        .clk      (vga_pixel_clk),
        .wr_en    (vmem_wr_en),
        .wr_addr  (vmem_wr_addr),
        .wr_data  (vmem_wr_data),
        .rd_addr  (vmem_rd_addr),
        .rd_data  (vmem_rd_data)
    );

    vga_text_mode u_text_mode (
        .clk        (vga_pixel_clk),
        .reset      (vga_rst),
        .hcount     (vga_hcount),
        .vcount     (vga_vcount),
        .video_on   (vga_video_on),
        .char_data  (vmem_rd_data),
        .vga_r      (vga_r),
        .vga_g      (vga_g),
        .vga_b      (vga_b)
    );

    screen_writer_pipeline #(
        .DMEM_DEPTH (DMEM_DEPTH),
        .IMEM_DEPTH (IMEM_DEPTH)
    ) u_writer (
        .clk              (vga_pixel_clk),
        .rst_n            (~vga_rst),

        // FETCH / IF stage
        .pc               (if_pc),
        .instruction      (if_instruction),
        .next_pc          (if_pc + 32'd4),
        .if_pc            (if_pc),
        .if_instruction   (if_instruction),
        .branch           (branch_flush),

        // IF/ID register outputs
        .id_pc            (id_pc),
        .id_instruction   (id_instruction),

        // DECODE / ID stage
        .rs1_addr         (id_rs1_addr),
        .rs2_addr         (id_rs2_addr),
        .rd_addr          (id_rd_addr),
        .data_wr          (wb_rd_data),
        .ru_wr            (id_ru_wr),
        .rs1_data         (id_rs1_data),
        .rs2_data         (id_rs2_data),
        .imm_out          (id_imm),
        .imm_src          (id_imm_src),
        .opcode           (id_instruction[6:0]),
        .funct3           (id_instruction[14:12]),
        .funct7           (id_instruction[31:25]),

        // ID/EX register outputs
        .ex_pc            (ex_pc),
        .ex_instruction   (ex_instruction),
        .ex_rs1_data      (ex_rs1_data),
        .ex_rs2_data      (ex_rs2_data),
        .ex_imm           (ex_imm),

        // EXECUTE / EX stage
        .alu_a            (ex_alu_a),
        .alu_b            (ex_alu_b),
        .alu_res          (ex_alu_result),
        .alu_op           (ex_alu_op),
        .alua_src         (ex_alua_src),
        .alub_src         (ex_alub_src),
        .br_op            (ex_br_op),

        // EX/MEM register outputs
        .mem_rs1_data     (mem_rs1_data),
        .mem_rs2_data     (mem_rs2_data),
        .mem_alu_result   (mem_alu_result),
        .ex_alu_result    (ex_alu_result),
        .mem_instruction  (mem_instruction),
        .ex_branch_taken  (ex_branch_taken),

        // MEMORY / MEM stage
        .dm_addr          (mem_alu_result),
        .dm_wdata         (mem_rs2_data),
        .dm_rdata         (dmem_rd_data),
        .dm_ctrl          (mem_dm_ctrl),
        .dm_wr            (mem_dm_wr),

        // MEM/WB register outputs
        .wb_instruction   (wb_instruction),
        .wb_rd_addr       (wb_rd_addr),
        .wb_rd_data       (wb_rd_data),

        // WRITEBACK
        .ru_data_wr_src   (wb_ru_data_wr_src),

        // Counters
        .instr_retired    (instr_retired),
        .cycles_at_done   (cycles_at_done),
        .instr_at_done    (instr_at_done),
        .halted           (program_done),

        // Register file (whole file, for the register table)
        .reg_values       (rf_dbg_regs),

        // Live memory windows (VGA clock domain)
        .imem_rd_addr     (imem_shadow_rd_addr),
        .imem_rd_data     (imem_shadow_rd_data),
        .dmem_rd_addr     (dmem_shadow_rd_addr),
        .dmem_rd_data     (dmem_shadow_rd_data),

        // Hazard / control
        .stall            (stall),
        .load_use_hazard  (load_use_hazard),
        .branch_flush     (branch_flush),
        .trap_flush       (trap_flush),
        .flush            (flush),

        // Video memory interface
        .vmem_wr_en       (vmem_wr_en),
        .vmem_wr_addr     (vmem_wr_addr),
        .vmem_wr_data     (vmem_wr_data)
    );

    // -----------------------------------------------------------------
    // Console shadows: copies of the program and data memories that the
    // VGA console reads.  The write port of the data shadow lives in the
    // processor clock domain and is driven by the very same signals as the
    // CPU's data memory, so the mirror holds exactly what the CPU's memory
    // holds.  The read ports live in the VGA clock domain.
    // -----------------------------------------------------------------
    logic [31:0] dmem_shadow_rd_data;
    logic [31:0] imem_shadow_rd_data;
    // The screen writer walks the memories; it drives the read addresses.
    logic [31:0] dmem_shadow_rd_addr;
    logic [31:0] imem_shadow_rd_addr;

    vga_mem_shadow #(.DEPTH(DMEM_DEPTH)) u_dmem_shadow (
        .wr_clk (clk),
        .wr_en  (shadow_wr_en),
        .wr_addr(shadow_wr_addr),
        .wr_data(shadow_wr_data),
        .wr_be  (shadow_wr_be),
        .rd_clk (vga_pixel_clk),
        .rd_addr(dmem_shadow_rd_addr),
        .rd_data(dmem_shadow_rd_data)
    );

    vga_rom_shadow #(.DEPTH(IMEM_DEPTH)) u_imem_shadow (
        .wr_clk (clk),
        .wr_en  (loader_imem_wr_en),
        .wr_addr(loader_imem_wr_addr),
        .wr_data(loader_imem_wr_data),
        .rd_clk (vga_pixel_clk),
        .rd_addr(imem_shadow_rd_addr),
        .rd_data(imem_shadow_rd_data)
    );

endmodule