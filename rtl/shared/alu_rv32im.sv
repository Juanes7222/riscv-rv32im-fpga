module alu_rv32im (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [31:0] a,
    input  logic [31:0] b,
    input  logic [4:0]  alu_op,
    output logic [31:0] alu_res,
    output logic        div_busy,
    output logic        div_done
);

    localparam [4:0] ALU_ADD    = 5'b00000;
    localparam [4:0] ALU_SUB    = 5'b00001;
    localparam [4:0] ALU_SLL    = 5'b00010;
    localparam [4:0] ALU_SLT    = 5'b00011;
    localparam [4:0] ALU_SLTU   = 5'b00100;
    localparam [4:0] ALU_XOR    = 5'b00101;
    localparam [4:0] ALU_SRL    = 5'b00110;
    localparam [4:0] ALU_SRA    = 5'b00111;
    localparam [4:0] ALU_OR     = 5'b01000;
    localparam [4:0] ALU_AND    = 5'b01001;
    localparam [4:0] ALU_MUL    = 5'b01010;
    localparam [4:0] ALU_MULH   = 5'b01011;
    localparam [4:0] ALU_MULHSU = 5'b01100;
    localparam [4:0] ALU_MULHU  = 5'b01101;
    localparam [4:0] ALU_DIV    = 5'b01110;
    localparam [4:0] ALU_DIVU   = 5'b01111;
    localparam [4:0] ALU_REM    = 5'b10000;
    localparam [4:0] ALU_REMU   = 5'b10001;

    localparam [1:0] DIV_IDLE    = 2'b00;
    localparam [1:0] DIV_RUNNING = 2'b01;
    localparam [1:0] DIV_DONE    = 2'b10;

    logic signed [63:0] mul_ss;
    logic        [63:0] mul_uu;
    logic signed [32:0] a_33, b_33;
    logic signed [65:0] mul_su;

    assign mul_ss = $signed(a) * $signed(b);
    assign mul_uu = a * b;
    assign a_33   = {a[31], a};
    assign b_33   = {1'b0,  b};
    assign mul_su = a_33 * b_33;

    logic [4:0]  shamt;
    logic [31:0] mul_ss_lo, mul_ss_hi, mul_su_hi, mul_uu_hi;

    assign shamt     = b[4:0];
    assign mul_ss_lo = mul_ss[31:0];
    assign mul_ss_hi = mul_ss[63:32];
    assign mul_su_hi = mul_su[63:32];
    assign mul_uu_hi = mul_uu[63:32];

    logic div_by_zero;
    logic div_overflow;
    logic is_div_op;

    assign div_by_zero  = (b == 32'b0);
    assign div_overflow = (a == 32'h8000_0000) && (b == 32'hFFFF_FFFF);
    assign is_div_op    = (alu_op == ALU_DIV  || alu_op == ALU_DIVU ||
                           alu_op == ALU_REM  || alu_op == ALU_REMU);

    logic [1:0]  div_state;
    logic [4:0]  div_count;
    logic [4:0]  div_op_r;
    logic [31:0] div_dividend;
    logic [31:0] div_divisor;
    logic [32:0] div_partial;
    logic [31:0] div_quotient;
    logic [31:0] div_result;
    logic        div_neg_quot;
    logic        div_neg_rem;
    logic        div_done_r;
    
    // Combinational "next" values for div_quotient/div_partial: the value
    // they WILL have after this iteration's update. Used on the last
    // iteration to include the LSB of the quotient in the latched result
    // (which is otherwise lost because the FSM transitions out of
    // DIV_RUNNING on the same cycle).
    logic [31:0] next_quotient;
    logic [32:0] next_partial;

    logic [32:0] sub_res;
    logic        sub_res_sign;
    logic [31:0] div_partial_word;
    logic [30:0] div_dividend_low;
    logic        div_dividend_msb;

    assign div_dividend_msb = div_dividend[31];
    assign sub_res_sign     = sub_res[32];
    assign div_partial_word = div_partial[31:0];
    assign div_dividend_low = div_dividend[30:0];

    logic a_31, b_31;
    assign a_31 = a[31];
    assign b_31 = b[31];

    // div_busy holds the PC while a DIV is in flight. The FSM state alone
    // is not enough on the fetch cycle: div_state is still IDLE on the
    // cycle the DIV is presented, so div_state-based busy would drop and
    // the PC would advance before the writeback. We OR in the combinational
    // is_div_op for that case, gated by div_processed to break the deadlock
    // (otherwise the held PC would keep the current instruction as a DIV
    // forever, keeping is_div_op asserted).
    logic div_processed;
    assign div_busy = (div_state != DIV_IDLE) || (is_div_op & ~div_processed);
    assign div_done = div_done_r;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            div_state     <= DIV_IDLE;
            div_count     <= 5'd0;
            div_result    <= 32'b0;
            div_dividend  <= 32'b0;
            div_divisor   <= 32'b0;
            div_partial   <= 33'b0;
            div_quotient  <= 32'b0;
            div_neg_quot  <= 1'b0;
            div_neg_rem   <= 1'b0;
            div_op_r      <= 5'b0;
            div_done_r    <= 1'b0;
            div_processed <= 1'b0;
        end else begin
            // div_processed is the one-cycle pulse that masks is_div_op on
            // the cycle immediately after the writeback, allowing the PC to
            // finally advance.
            case (div_state)
                DIV_DONE: div_processed <= 1'b1;
                DIV_IDLE: div_processed <= 1'b0;
                default: ;
            endcase

            case (div_state)

                DIV_IDLE: begin
                    div_done_r <= 1'b0;
                    if (is_div_op & ~div_processed) begin
                        div_op_r <= alu_op;
                        if (div_by_zero) begin
                            case (alu_op)
                                ALU_DIV:  div_result <= 32'hFFFF_FFFF;
                                ALU_DIVU: div_result <= 32'hFFFF_FFFF;
                                ALU_REM:  div_result <= a;
                                ALU_REMU: div_result <= a;
                                default:  div_result <= 32'b0;
                            endcase
                            // One-cycle stall in DIV_DONE so the writeback
                            // uses the DIV's rd_addr, not the next
                            // instruction's. The PC stays held because
                            // div_busy also includes the combinational
                            // is_div_op term while div_processed is 0.
                            div_state  <= DIV_DONE;
                            div_done_r <= 1'b1;
                        end else if ((alu_op == ALU_DIV || alu_op == ALU_REM)
                                      && div_overflow) begin
                            div_result <= (alu_op == ALU_DIV) ? 32'h8000_0000 : 32'b0;
                            div_state  <= DIV_DONE;
                            div_done_r <= 1'b1;
                        end else begin
                            div_neg_quot <= (alu_op == ALU_DIV) && (a_31 ^ b_31);
                            div_neg_rem  <= (alu_op == ALU_REM) && a_31;
                            div_dividend <= ((alu_op == ALU_DIV || alu_op == ALU_REM) && a_31)
                                            ? (~a + 1) : a;
                            div_divisor  <= ((alu_op == ALU_DIV || alu_op == ALU_REM) && b_31)
                                            ? (~b + 1) : b;
                            div_partial  <= 33'b0;
                            div_quotient <= 32'b0;
                            div_count    <= 5'd0;
                            div_state    <= DIV_RUNNING;
                        end
                    end
                end

                DIV_RUNNING: begin
                    div_done_r <= 1'b0;
                    // Update quotient and partial on every iteration,
                    // including the last one - the LSB of the quotient is
                    // produced on iteration 31 and would otherwise be lost
                    // because we leave DIV_RUNNING on the same cycle.
                    div_partial  <= next_partial;
                    div_quotient <= next_quotient;
                    div_dividend <= {div_dividend_low, 1'b0};

                    if (div_count == 5'd31) begin
                        // Latch the final result using the combinational
                        // next_quotient/next_partial so the LSB of the
                        // quotient (or the final remainder) is included.
                        case (div_op_r)
                            ALU_DIV:  div_result <= div_neg_quot ? (~next_quotient + 1) : next_quotient;
                            ALU_DIVU: div_result <= next_quotient;
                            ALU_REM:  div_result <= div_neg_rem  ? (~next_partial[31:0] + 1) : next_partial[31:0];
                            ALU_REMU: div_result <= next_partial[31:0];
                            default:  div_result <= 32'b0;
                        endcase
                        div_state  <= DIV_DONE;
                        div_done_r <= 1'b1;
                    end else begin
                        div_count    <= div_count + 5'd1;
                    end
                end

                // Writeback cycle: PC is still held (div_busy = 1 because
                // DIV_DONE != DIV_IDLE, plus the is_div_op term is still
                // active while div_processed is 0). div_done_r was set on
                // entry so the top-level register file write fires for
                // exactly this cycle.
                DIV_DONE: begin
                    div_done_r <= 1'b0;
                    div_state  <= DIV_IDLE;
                end

                default: begin
                    div_state  <= DIV_IDLE;
                    div_done_r <= 1'b0;
                end

            endcase
        end
    end


    always_comb begin
        sub_res  = {div_partial_word, div_dividend_msb} - {1'b0, div_divisor};
        if (!sub_res_sign) begin
            next_quotient = {div_quotient[30:0], 1'b1};
            next_partial  = sub_res;
        end else begin
            next_quotient = {div_quotient[30:0], 1'b0};
            next_partial  = {div_partial_word, div_dividend_msb};
        end
    end

    always_comb begin
        if (div_busy || div_done_r || div_processed) begin
            alu_res = div_result;
        end else begin
            case (alu_op)
                ALU_ADD:    alu_res = a + b;
                ALU_SUB:    alu_res = a - b;
                ALU_SLL:    alu_res = a << shamt;
                ALU_SLT:    alu_res = {31'b0, $signed(a) < $signed(b)};
                ALU_SLTU:   alu_res = {31'b0, a < b};
                ALU_XOR:    alu_res = a ^ b;
                ALU_SRL:    alu_res = a >> shamt;
                ALU_SRA:    alu_res = $signed(a) >>> shamt;
                ALU_OR:     alu_res = a | b;
                ALU_AND:    alu_res = a & b;
                ALU_MUL:    alu_res = mul_ss_lo;
                ALU_MULH:   alu_res = mul_ss_hi;
                ALU_MULHSU: alu_res = mul_su_hi;
                ALU_MULHU:  alu_res = mul_uu_hi;
                default:    alu_res = 32'b0;
            endcase
        end
    end

endmodule