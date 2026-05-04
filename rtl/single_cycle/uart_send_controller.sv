module uart_send_controller (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        program_done,
    input  logic [31:0] cycle_count,
    input  logic [31:0] instr_retired,
    input  logic        tx_ready,
    output logic [7:0]  tx_data,
    output logic        tx_valid
);

    localparam int FRAME_LEN = 10;

    typedef enum logic [1:0] {
        WAIT,
        SEND,
        DONE
    } state_t;

    state_t     state;
    logic [3:0] byte_idx;
    logic [7:0] frame [0:FRAME_LEN-1];

    always_comb begin
        frame[0] = 8'hAA;
        frame[1] = cycle_count[31:24];
        frame[2] = cycle_count[23:16];
        frame[3] = cycle_count[15:8];
        frame[4] = cycle_count[7:0];
        frame[5] = instr_retired[31:24];
        frame[6] = instr_retired[23:16];
        frame[7] = instr_retired[15:8];
        frame[8] = instr_retired[7:0];
        frame[9] = 8'h55;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state    <= WAIT;
            byte_idx <= 4'b0;
            tx_valid <= 1'b0;
            tx_data  <= 8'b0;
        end else begin
            tx_valid <= 1'b0;
            case (state)

                WAIT: begin
                    if (program_done) begin
                        byte_idx <= 4'b0;
                        state    <= SEND;
                    end
                end

                SEND: begin
                    if (tx_ready && !tx_valid) begin
                        tx_data  <= frame[byte_idx];
                        tx_valid <= 1'b1;
                        if (byte_idx == FRAME_LEN - 1)
                            state <= DONE;
                        else
                            byte_idx <= byte_idx + 4'd1;
                    end
                end

                DONE: ;   // remain until reset

                default: state <= WAIT;

            endcase
        end
    end

endmodule