// Five-stage RV32IM pipelined processor top-level (RV32IM + Zicsr + trap handling).
// Shares instruction memory, data memory, ALU, register file, imm_gen,
// branch_unit, and csr_file with top_single_cycle without modification.
module top_pipeline #(
    parameter string IMEM_FILE  = "program.mem",
    parameter int    IMEM_DEPTH = 16384,
    parameter int    DMEM_DEPTH = 8192,
    parameter logic [31:0] TOHOST_ADDR = 32'h708  // riscv-tests tohost symbol address
)(
    input  logic        clk,        // 50 MHz — DE1-SoC PIN_AF14
    input  logic        rst_n,      // Active-low synchronous reset — KEY[0]
    output logic [9:0]  ledr,       // if_pc[9:0] — same convention as single-cycle
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
    output logic [7:0]  vga_b
);

    // Internal reset (active-high for modules that require it)            //

    logic rst;
    assign rst = ~rst_n;  // register_file, pipeline registers use active-high rst

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

    // IMEM address mux: bypass PC register on flush to capture redirect
    // target immediately (sync IMEM captures at posedge — must see target
    // during the flush cycle, not one cycle later).
    logic [31:0] imem_addr;

    // IF/ID register outputs                                               //

    logic [31:0] id_pc;
    logic [31:0] id_instruction;

    // ID decoded fields
    logic [4:0]  id_rs1_addr, id_rs2_addr, id_rd_addr;
    logic [31:0] id_rs1_data, id_rs2_data;
    logic [31:0] id_rs1_data_wb_fwd, id_rs2_data_wb_fwd;
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
    logic        ex_div_busy, ex_div_done;
    logic        ex_branch_taken, ex_mask_pc_lsb;
    logic [31:0] ex_pc_plus4;

    // Division detection — used in ID/EX stall logic (mirrors ADR 023)
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

    // MEM stage — DMEM registered output (aligned with MEM/WB outputs)
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

    assign branch_flush = ex_branch_taken;
    assign trap_flush   = wb_trap_entry || wb_mret_exec;
    assign flush        = branch_flush || trap_flush;

    // Performance counters                                                 //
    logic [63:0] cycle_count;
    logic [63:0] instr_retired;
    logic        program_done;

    // valid_wb: a real instruction retires in WB when it is not a bubble
    // and the pipeline is not stalled.
    logic valid_wb;
    assign valid_wb = (wb_instruction != 32'h00000013) && wb_ru_wr;

    // program_done: detect tohost write in MEM stage (ADR 026).
    // A store of value 1 to TOHOST_ADDR signals benchmark completion.
    // Registered to provide a clean edge for SignalTap II trigger.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            program_done <= 1'b0;
        end else if (mem_dm_wr && (mem_alu_result == TOHOST_ADDR) && (mem_rs2_data == 32'd1)) begin
            program_done <= 1'b1;
        end
    end

    perf_counters #(
        .PIPELINE_MODE (1'b1)
    ) u_perf (
        .clk                  (clk),
        .rst_n                (rst_n),
        .div_busy             (ex_div_busy),
        .valid_wb             (valid_wb),
        .program_done         (program_done),
        .cycle_count          (cycle_count),
        .instr_retired        (instr_retired),
        .program_done_synced  ()
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
      initial begin
         $dumpfile("dump.vcd");
         $dumpvars(0, top_pipeline);
      end
   `endif
// synthesis translate_on

    // IF stage
    // PC redirect target mux: trap (WB) > branch/jump (EX) > sequential
    logic [31:0] pc_redirect_target;
    always_comb begin
        if (trap_flush)
            pc_redirect_target = wb_mret_exec ? mepc_value : trap_target;
        else
            pc_redirect_target = {ex_alu_result[31:1],
                                  ex_mask_pc_lsb ? 1'b0 : ex_alu_result[0]};
    end

    pc_unit u_pcunit (
        .clk           (clk),
        .rst           (rst),
        .stall         (stall && !trap_flush),
        .branch_taken  (branch_flush || trap_flush),
        .mask_pc_lsb   (1'b0),              // masking already applied above
        .branch_target (pc_redirect_target),
        .pc            (if_pc)
    );

    // IMEM address: during a flush, feed the redirect target directly
    // so the synchronous IMEM captures the correct instruction at posedge.
    // IMEM address: during a flush, feed the redirect target directly.
    assign imem_addr = flush ? pc_redirect_target : if_pc;

    instruction_memory_pipe #(
        .IMEM_DEPTH (IMEM_DEPTH)
    ) u_imem (
        .clk         (clk),
        .addr        (imem_addr),
        .instruction (if_instruction)
    );

    // IF/ID register: captures from if_pc and IMEM combinational output,
    // both aligned to the same fetch.
    if_id_register u_if_id (
        .clk            (clk),
        .rst            (rst),
        .stall          (stall && !trap_flush),
        .flush          (flush),
        .if_pc          (if_pc),
        .if_instruction (if_instruction),
        .id_pc          (id_pc),
        .id_instruction (id_instruction)
    );

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
        .wr_en    (wb_wr_en_gated),
        .rs1_data (id_rs1_data),
        .rs2_data (id_rs2_data)
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
        .load_use               (load_use_hazard)
    );

    // ID/EX flush: bubble on branch, trap, AND load-use. The standard
    // MIPS load-use stall inserts a NOP into ID/EX (so the load can advance
    // to MEM and the consumer enters EX in the next cycle). It does NOT
    // hold ID/EX, because holding would keep the load stuck in EX and
    // the data would never reach MEM/WB. The div stall, on the other hand,
    // holds ID/EX (so the div stays in EX for 34 cycles).
    logic id_ex_flush;
    assign id_ex_flush = flush || load_use_hazard;

    // ID/EX register                                                       //
    // flush: id_ex_flush (branch/trap/load-use). stall: only on div_busy
    // (the div must stay in EX for 34 cycles; load-use does NOT stall here
    // because the load needs to advance to MEM).
    id_ex_register u_id_ex (
        .clk               (clk),
        .rst               (rst),
        .flush             (id_ex_flush),
        .stall             (ex_div_busy),
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
        .rst_n   (rst_n),          // alu_rv32im uses active-low rst_n directly
        .a       (ex_alu_a),
        .b       (ex_alu_b),
        .alu_op  (ex_alu_op),
        .alu_res (ex_alu_result),
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
        .stall              (ex_div_busy),
        .flush              (trap_flush),
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
    data_memory_pipe #(
        .DMEM_DEPTH (DMEM_DEPTH)
    ) u_dmem (
        .clk     (clk),
        .addr    (mem_alu_result),
        .wr_data (mem_rs2_data),
        .dm_wr   (mem_dm_wr),
        .dm_ctrl (mem_dm_ctrl),
        .rd_data (dmem_rd_data)
    );

    // MEM/WB register                                                      //
    // stall: holds current contents during div stall. The trap itself
    // is in WB when trap_flush is asserted, so the trap must be allowed
    // to commit normally — MEM/WB is not flushed.
    // Note: dm_rd_data bypasses MEM/WB; the DMEM registered output feeds
    // the WB mux directly.  mem_dm_rd_data is tied to 0 for port compat.
    mem_wb_register u_mem_wb (
        .clk                (clk),
        .rst                (rst),
        .stall              (ex_div_busy),
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
        .rst_n      (rst_n),
        .csr_addr   (wb_csr_addr),
        .csr_wdata  (wb_csr_wdata),
        .csr_wr     (wb_csr_wr_gated),
        .csr_op     (wb_csr_op),
        .csr_rdata  (csr_rdata),
        .trap_entry (wb_trap_entry),
        .trap_pc4   (wb_pc + 32'd4),   // mepc = PC+4 of the ECALL instruction
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

    vga_pll u_vga_pll (
        .clk_in  (clk),
        .rst_in  (~rst_n),
        .clk_out (vga_pixel_clk),
        .locked  (pll_locked)
    );

    logic [10:0] vga_hcount;
    logic [9:0]  vga_vcount;
    logic        vga_video_on;

    vga_controller_1280x720 u_vga (
        .clk      (vga_pixel_clk),
        .reset    (1'b0),
        .hsync    (vga_hsync),
        .vsync    (vga_vsync),
        .hcount   (vga_hcount),
        .vcount   (vga_vcount),
        .video_on (vga_video_on)
    );

    assign vmem_rd_addr = (vga_vcount[9:4] * 11'd160) + vga_hcount[10:3];

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
        .hcount     (vga_hcount),
        .vcount     (vga_vcount),
        .video_on   (vga_video_on),
        .char_data  (vmem_rd_data),
        .vga_r      (vga_r),
        .vga_g      (vga_g),
        .vga_b      (vga_b)
    );

    screen_writer_pipeline u_writer (
        .clk            (vga_pixel_clk),
        .rst_n          (pll_locked),
        .if_pc          (if_pc),
        .if_instruction (if_instruction),
        .id_pc          (id_pc),
        .id_instruction (id_instruction),
        .ex_alu_result  (ex_alu_result),
        .ex_instruction (ex_instruction),
        .mem_alu_result (mem_alu_result),
        .mem_dm_rd_data (dmem_rd_data),
        .wb_rd_data     (wb_rd_data),
        .wb_rd_addr     (wb_rd_addr),
        .stall          (stall),
        .flush          (flush),
        .load_use_hazard(load_use_hazard),
        .vmem_wr_en     (vmem_wr_en),
        .vmem_wr_addr   (vmem_wr_addr),
        .vmem_wr_data   (vmem_wr_data)
    );

endmodule