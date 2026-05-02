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

    // FSM states 
    localparam [1:0] DIV_IDLE    = 2'b00;
    localparam [1:0] DIV_RUNNING = 2'b01;
    localparam [1:0] DIV_DONE    = 2'b10;

    // Multiply: combinational 
    logic signed [63:0] mul_ss;
    logic        [63:0] mul_uu;
    logic signed [32:0] a_33, b_33;
    logic signed [65:0] mul_su;

    assign mul_ss = $signed(a) * $signed(b);
    assign mul_uu = a * b;
    assign a_33   = {a[31], a};   // sign-extend a to 33 bits
    assign b_33   = {1'b0,  b};   // zero-extend b to 33 bits (non-negative in signed)
    assign mul_su = a_33 * b_33;

    // Division: corner-case detection (combinational)
    logic div_by_zero;
    logic div_overflow;

    assign div_by_zero  = (b == 32'b0);
    assign div_overflow = (a == 32'h8000_0000) && (b == 32'hFFFF_FFFF);

    // Division FSM state and registers
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

    // Intermediate signals for DIV_RUNNING and DIV_DONE — module scope
    // to avoid Quartus inference issues with locally declared variables
    // inside always_ff begin...end blocks.
    logic [32:0] sub_res;
    logic [31:0] raw_quot, raw_rem;

    assign div_busy = (div_state != DIV_IDLE);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            div_state    <= DIV_IDLE;
            div_count    <= 5'd0;
            div_result   <= 32'b0;
            div_dividend <= 32'b0;
            div_divisor  <= 32'b0;
            div_partial  <= 33'b0;
            div_quotient <= 32'b0;
            div_neg_quot <= 1'b0;
            div_neg_rem  <= 1'b0;
            div_op_r     <= 5'b0;
        end else begin
            case (div_state)

                DIV_IDLE: begin
                    if (alu_op == ALU_DIV || alu_op == ALU_DIVU ||
                            alu_op == ALU_REM || alu_op == ALU_REMU) begin
                        div_op_r <= alu_op;
                        if (div_by_zero) begin
                            case (alu_op)
                                ALU_DIV:  div_result <= 32'hFFFF_FFFF;
                                ALU_DIVU: div_result <= 32'hFFFF_FFFF;
                                ALU_REM:  div_result <= a;
                                ALU_REMU: div_result <= a;
                                default:  div_result <= 32'b0;
                            endcase
                            // Stay in IDLE: div_busy never asserted
                        end else if ((alu_op == ALU_DIV || alu_op == ALU_REM)
                                      && div_overflow) begin
                            div_result <= (alu_op == ALU_DIV) ? 32'h8000_0000 : 32'b0;
                            // Stay in IDLE
                        end else begin
                            div_neg_quot <= (alu_op == ALU_DIV) && (a[31] ^ b[31]);
                            div_neg_rem  <= (alu_op == ALU_REM) && a[31];
                            div_dividend <= ((alu_op == ALU_DIV || alu_op == ALU_REM) && a[31])
                                            ? (~a + 1) : a;
                            div_divisor  <= ((alu_op == ALU_DIV || alu_op == ALU_REM) && b[31])
                                            ? (~b + 1) : b;
                            div_partial  <= 33'b0;
                            div_quotient <= 32'b0;
                            div_count    <= 5'd0;
                            div_state    <= DIV_RUNNING;
                        end
                    end
                end

                DIV_RUNNING: begin
                    // Radix-2 restoring division: one bit of quotient per cycle.
                    // sub_res is driven combinationally from div_partial/div_dividend
                    // (see always_comb below); result sampled here.
                    if (!sub_res[32]) begin
                        div_partial  <= sub_res;
                        div_quotient <= {div_quotient[30:0], 1'b1};
                    end else begin
                        div_partial  <= {div_partial[31:0], div_dividend[31]};
                        div_quotient <= {div_quotient[30:0], 1'b0};
                    end
                    div_dividend <= {div_dividend[30:0], 1'b0};

                    if (div_count == 5'd31) begin
                        div_state <= DIV_DONE;
                    end else begin
                        div_count <= div_count + 5'd1;
                    end
                end

                DIV_DONE: begin
                    // raw_quot and raw_rem driven combinationally (always_comb below)
                    case (div_op_r)
                        ALU_DIV:  div_result <= div_neg_quot ? (~raw_quot + 1) : raw_quot;
                        ALU_DIVU: div_result <= raw_quot;
                        ALU_REM:  div_result <= div_neg_rem  ? (~raw_rem  + 1) : raw_rem;
                        ALU_REMU: div_result <= raw_rem;
                        default:  div_result <= 32'b0;
                    endcase
                    div_state <= DIV_IDLE;
                end

                default: div_state <= DIV_IDLE;

            endcase
        end
    end

    // Combinational signals consumed by the FSM in the next always_ff edge.
    // Declared here to satisfy Quartus's requirement that all signals driven
    // in always_comb are not also driven in always_ff.
    always_comb begin
        // DIV_RUNNING: trial subtraction
        sub_res  = {div_partial[31:0], div_dividend[31]} - {1'b0, div_divisor};

        // DIV_DONE: raw quotient and remainder before sign correction
        raw_quot = div_quotient;
        raw_rem  = div_partial[31:0];
    end

    // Result mux
    always_comb begin
        if (div_busy) begin
            alu_res = div_result;
        end else begin
            case (alu_op)
                ALU_ADD:    alu_res = a + b;
                ALU_SUB:    alu_res = a - b;
                ALU_SLL:    alu_res = a << b[4:0];
                ALU_SLT:    alu_res = {31'b0, $signed(a) < $signed(b)};
                ALU_SLTU:   alu_res = {31'b0, a < b};
                ALU_XOR:    alu_res = a ^ b;
                ALU_SRL:    alu_res = a >> b[4:0];
                ALU_SRA:    alu_res = $signed(a) >>> b[4:0];
                ALU_OR:     alu_res = a | b;
                ALU_AND:    alu_res = a & b;
                ALU_MUL:    alu_res = mul_ss[31:0];
                ALU_MULH:   alu_res = mul_ss[63:32];
                ALU_MULHSU: alu_res = mul_su[63:32];
                ALU_MULHU:  alu_res = mul_uu[63:32];
                default:    alu_res = 32'b0;
            endcase
        end
    end

    assign div_done = (div_state == DIV_DONE) ||
                  (div_state == DIV_IDLE &&
                   (alu_op == ALU_DIV || alu_op == ALU_DIVU ||
                    alu_op == ALU_REM || alu_op == ALU_REMU) &&
                   (div_by_zero || div_overflow));

endmodule