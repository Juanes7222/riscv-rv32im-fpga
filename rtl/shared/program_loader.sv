// Program loader: loads test programs into imem/dmem at runtime.
// Select with SW[0:3], load with KEY[2]. Writes only when CPU is halted.

module program_loader #(
    parameter int IMEM_DEPTH = 16384,
    parameter int DMEM_DEPTH = 8192,
    parameter int N_PROGS    = 6
)(
    input  logic        clk,
    input  logic        rst_n,
    input  logic        step_hold,
    input  logic [3:0]  prog_sel,
    input  logic        key_load,
    output logic        load_done,
    output logic [31:0] imem_wr_addr,
    output logic [31:0] imem_wr_data,
    output logic        imem_wr_en,
    output logic [31:0] dmem_wr_addr,
    output logic [31:0] dmem_wr_data,
    output logic        dmem_wr_en
);

    logic [1:0] key_sync;
    always_ff @(posedge clk) begin
        if (!rst_n) key_sync <= 2'b11;
        else        key_sync <= {key_sync[0], key_load};
    end
    wire key_press = key_sync[1] & ~key_sync[0];

    typedef enum logic [1:0] {S_IDLE, S_COPY, S_DONE} state_t;
    state_t state, state_n;

    logic [$clog2(IMEM_DEPTH)-1:0] imem_i;
    logic [$clog2(DMEM_DEPTH)-1:0] dmem_i;
    logic [3:0]  prog_sel_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state      <= S_IDLE;
            imem_i     <= '0;
            dmem_i     <= '0;
            prog_sel_q <= 4'd0;
            load_done  <= 1'b0;
        end else begin
            state      <= state_n;
            prog_sel_q <= (state == S_IDLE) ? prog_sel : prog_sel_q;

            if (state == S_COPY) begin
                imem_i <= imem_i + 1'b1;
                dmem_i <= dmem_i + 1'b1;
            end else begin
                imem_i <= '0;
                dmem_i <= '0;
            end

            load_done <= (state_n == S_DONE);
        end
    end

    always_comb begin
        state_n   = state;
        imem_wr_en  = 1'b0;
        dmem_wr_en  = 1'b0;
        imem_wr_addr = 32'h0;
        imem_wr_data = 32'h0;
        dmem_wr_addr = 32'h0;
        dmem_wr_data = 32'h0;

        unique case (state)
            S_IDLE: begin
                // Escribe solo con el CPU detenido (step_hold == 1).
                // El usuario pone SW[9]=1 (step mode), selecciona con
                // SW[0:3] y pulsa KEY[2] para cargar el programa.
                if (key_press && step_hold == 1'b1)
                    state_n = S_COPY;
            end

            S_COPY: begin
                imem_wr_en  = 1'b1;
                dmem_wr_en  = 1'b1;
                imem_wr_addr = {20'd0, imem_i} << 2;
                dmem_wr_addr = {20'd0, dmem_i} << 2;
                imem_wr_data = prog_imem_word(prog_sel_q, imem_i);
                dmem_wr_data = prog_dmem_word(prog_sel_q, dmem_i);

                if (imem_i == prog_imem_len(prog_sel_q) - 1)
                    state_n = S_DONE;
            end

            S_DONE: begin
                state_n = S_IDLE;
            end
        endcase
    end

    function automatic logic [31:0] prog_imem_word(input logic [3:0] p,
                                                   input logic [13:0] w);
        case (p)
            4'd0: begin  // halt: NOP + ECALL
                case (w)
                    14'd0: prog_imem_word = 32'h00000013; // nop
                    14'd1: prog_imem_word = 32'h00000073; // ecall
                    default: prog_imem_word = 32'h00000013;
                endcase
            end
            4'd1: begin  // fibonacci (compiled from fib.S)
                case (w)
                    14'd0:  prog_imem_word = 32'h00a00513; // li a0,10
                    14'd1:  prog_imem_word = 32'h00000593; // li a1,0
                    14'd2:  prog_imem_word = 32'h00100613; // li a2,1
                    14'd3:  prog_imem_word = 32'h00100693; // li a3,1
                    14'd4:  prog_imem_word = 32'h00a6dc63; // bge a3,a0,done
                    14'd5:  prog_imem_word = 32'h00c58733; // add a4,a1,a2
                    14'd6:  prog_imem_word = 32'h00060593; // mv a1,a2
                    14'd7:  prog_imem_word = 32'h00070613; // mv a2,a4
                    14'd8:  prog_imem_word = 32'h00168693; // addi a3,a3,1
                    14'd9:  prog_imem_word = 32'hfedff06f; // j loop
                    14'd10: prog_imem_word = 32'h00a00893; // li a7,10
                    14'd11: prog_imem_word = 32'h00000073; // ecall
                    14'd12: prog_imem_word = 32'hff9ff06f; // j done
                    default: prog_imem_word = 32'h00000013;
                endcase
            end
            4'd2: begin  // alu_test (compiled from alu_test.S, RV32I)
                case (w)
                    14'd0:  prog_imem_word = 32'h123450b7; // lui ra,0x12345
                    14'd1:  prog_imem_word = 32'h67808093; // addi ra,ra,1656
                    14'd2:  prog_imem_word = 32'h9abce137; // lui sp,0x9abce
                    14'd3:  prog_imem_word = 32'hef010113; // addi sp,sp,-272
                    14'd4:  prog_imem_word = 32'h002081b3; // add gp,ra,sp
                    14'd5:  prog_imem_word = 32'h40208233; // sub tp,ra,sp
                    14'd6:  prog_imem_word = 32'h0020f2b3; // and t0,ra,sp
                    14'd7:  prog_imem_word = 32'h0020e333; // or t1,ra,sp
                    14'd8:  prog_imem_word = 32'h0020c3b3; // xor t2,ra,sp
                    14'd9:  prog_imem_word = 32'h00209433; // sll s0,ra,sp
                    14'd10: prog_imem_word = 32'h0020d4b3; // srl s1,ra,sp
                    14'd11: prog_imem_word = 32'h4020d533; // sra a0,ra,sp
                    14'd12: prog_imem_word = 32'h0020a5b3; // slt a1,ra,sp
                    14'd13: prog_imem_word = 32'h0020b633; // sltu a2,ra,sp
                    14'd14: prog_imem_word = 32'h00100693; // li a3,1
                    14'd15: prog_imem_word = 32'h00100713; // li a4,1
                    14'd16: prog_imem_word = 32'h00e68463; // beq a3,a4,taken
                    14'd17: prog_imem_word = 32'h00000013; // nop
                    14'd18: prog_imem_word = 32'hdeadc7b7; // lui a5,0xdeadc
                    14'd19: prog_imem_word = 32'heef78793; // addi a5,a5,-273
                    14'd20: prog_imem_word = 32'h00000073; // ecall
                    14'd21: prog_imem_word = 32'h0000006f; // j .
                    default: prog_imem_word = 32'h00000013;
                endcase
            end
            4'd3: begin  // mul_div_test (compiled from mul_div.S, RV32M)
                case (w)
                    14'd0:  prog_imem_word = 32'h000010b7; // lui ra,0x1
                    14'd1:  prog_imem_word = 32'h20008093; // addi ra,ra,512
                    14'd2:  prog_imem_word = 32'h00008137; // lui sp,0x8
                    14'd3:  prog_imem_word = 32'he0010113; // addi sp,sp,-512
                    14'd4:  prog_imem_word = 32'h022081b3; // mul gp,ra,sp
                    14'd5:  prog_imem_word = 32'h02209233; // mulh tp,ra,sp
                    14'd6:  prog_imem_word = 32'h0220c2b3; // div t0,ra,sp
                    14'd7:  prog_imem_word = 32'h0220d333; // divu t1,ra,sp
                    14'd8:  prog_imem_word = 32'h0220e3b3; // rem t2,ra,sp
                    14'd9:  prog_imem_word = 32'h0220f433; // remu s0,ra,sp
                    14'd10: prog_imem_word = 32'h800004b7; // lui s1,0x80000
                    14'd11: prog_imem_word = 32'h0214c533; // div a0,s1,ra
                    14'd12: prog_imem_word = 32'h00000073; // ecall
                    14'd13: prog_imem_word = 32'h0000006f; // j .
                    default: prog_imem_word = 32'h00000013;
                endcase
            end
            4'd4: begin  // factorial (compiled from factorial.S, RV32M)
                case (w)
                    14'd0:  prog_imem_word = 32'h00500093; // li x1,5
                    14'd1:  prog_imem_word = 32'h00100113; // li x2,1
                    14'd2:  prog_imem_word = 32'h00100193; // li x3,1
                    14'd3:  prog_imem_word = 32'h02310133; // mul x2,x2,x3
                    14'd4:  prog_imem_word = 32'h00118193; // addi x3,x3,1
                    14'd5:  prog_imem_word = 32'hfe11cce3; // blt x3,x1,loop
                    14'd6:  prog_imem_word = 32'h00000073; // ecall
                    14'd7:  prog_imem_word = 32'h0000006f; // j .
                    default: prog_imem_word = 32'h00000013;
                endcase
            end
            4'd5: begin  // accumulator (compiled from accum.S, RV32I)
                case (w)
                    14'd0:  prog_imem_word = 32'h00a00093; // li x1,10
                    14'd1:  prog_imem_word = 32'h00000113; // li x2,0
                    14'd2:  prog_imem_word = 32'h00100193; // li x3,1
                    14'd3:  prog_imem_word = 32'h00310133; // add x2,x2,x3
                    14'd4:  prog_imem_word = 32'h00118193; // addi x3,x3,1
                    14'd5:  prog_imem_word = 32'hfe11cce3; // blt x3,x1,loop
                    14'd6:  prog_imem_word = 32'h00000073; // ecall
                    14'd7:  prog_imem_word = 32'h0000006f; // j .
                    default: prog_imem_word = 32'h00000013;
                endcase
            end
            default: prog_imem_word = 32'h00000013;
        endcase
    endfunction

    function automatic logic [31:0] prog_dmem_word(input logic [3:0] p,
                                                   input logic [12:0] w);
        case (p)
            default: prog_dmem_word = 32'h00000000;
        endcase
    endfunction

    function automatic logic [13:0] prog_imem_len(input logic [3:0] p);
        case (p)
            4'd0: prog_imem_len = 14'd2;
            4'd1: prog_imem_len = 14'd13;
            4'd2: prog_imem_len = 14'd22;
            4'd3: prog_imem_len = 14'd14;
            4'd4: prog_imem_len = 14'd8;
            4'd5: prog_imem_len = 14'd8;
            default: prog_imem_len = 14'd1;
        endcase
    endfunction

    function automatic logic [12:0] prog_dmem_len(input logic [3:0] p);
        prog_dmem_len = 13'd0;
    endfunction

endmodule
