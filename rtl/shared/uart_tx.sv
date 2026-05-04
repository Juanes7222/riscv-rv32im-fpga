module uart_tx #(
    parameter int unsigned CLK_FREQ  = 50_000_000,
    parameter int unsigned BAUD_RATE = 115_200
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [7:0] tx_data,
    input  logic       tx_valid,
    output logic       tx_ready,
    output logic       tx_pin
);

    localparam int CLKS_PER_BIT = CLK_FREQ / BAUD_RATE;   // 434 for 50 MHz / 115200

    localparam [1:0] IDLE  = 2'b00;
    localparam [1:0] START = 2'b01;
    localparam [1:0] DATA  = 2'b10;
    localparam [1:0] STOP  = 2'b11;

    logic [1:0]  state;
    logic [15:0] clk_count;
    logic [2:0]  bit_index;
    logic [7:0]  tx_shift;

    assign tx_ready = (state == IDLE);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state     <= IDLE;
            clk_count <= 16'b0;
            bit_index <= 3'b0;
            tx_shift  <= 8'b0;
            tx_pin    <= 1'b1;      // idle high (UART mark state)
        end else begin
            case (state)

                IDLE: begin
                    tx_pin <= 1'b1;
                    if (tx_valid) begin
                        tx_shift  <= tx_data;
                        clk_count <= 16'b0;
                        state     <= START;
                    end
                end

                START: begin
                    tx_pin <= 1'b0;     // start bit
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= 16'b0;
                        bit_index <= 3'b0;
                        state     <= DATA;
                    end else begin
                        clk_count <= clk_count + 16'd1;
                    end
                end

                DATA: begin
                    tx_pin <= tx_shift[bit_index];
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= 16'b0;
                        if (bit_index == 3'd7) begin
                            state <= STOP;
                        end else begin
                            bit_index <= bit_index + 3'd1;
                        end
                    end else begin
                        clk_count <= clk_count + 16'd1;
                    end
                end

                STOP: begin
                    tx_pin <= 1'b1;     // stop bit
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= 16'b0;
                        state     <= IDLE;
                    end else begin
                        clk_count <= clk_count + 16'd1;
                    end
                end

                default: state <= IDLE;

            endcase
        end
    end

endmodule