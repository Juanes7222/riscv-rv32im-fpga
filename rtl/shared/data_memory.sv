`include "mem_config.vh"

// Data memory: byte-enable writes, asynchronous read, M10K inference target.
module data_memory #(
    parameter int unsigned DMEM_DEPTH = 8192
) (
    input  logic        clk,
    input  logic [31:0] addr,
    input  logic [31:0] wr_data,
    input  logic        dm_wr,
    input  logic [2:0]  dm_ctrl,
    output logic [31:0] rd_data
);

    logic [31:0] mem [0:DMEM_DEPTH-1];

    initial begin
        `ifdef DMEM_FILE
            $readmemh(`DMEM_FILE, mem);
        `endif
    end

    `ifndef SYNTHESIS
      task load_imem(input string filename);
         $readmemh(filename, u_imem.mem);
      endtask

      task load_dmem(input string filename);
         $readmemh(filename, u_dmem.mem);
      endtask
    `endif

    localparam [1:0] WIDTH_BYTE = 2'b00;
    localparam [1:0] WIDTH_HALF = 2'b01;
    localparam [1:0] WIDTH_WORD = 2'b10;

    logic [1:0] access_width;
    logic       zero_ext;
    assign access_width = dm_ctrl[1:0];
    assign zero_ext     = dm_ctrl[2];

    // Address extractions — Icarus workaround for constant selects in always_*
    logic [12:0] word_addr;
    logic        addr_bit1;
    logic [1:0]  addr_bits10;
    assign word_addr   = addr[14:2];
    assign addr_bit1   = addr[1];
    assign addr_bits10 = addr[1:0];

    // Write data lane extractions
    logic [7:0]  wr_byte;
    logic [15:0] wr_half;
    assign wr_byte = wr_data[7:0];
    assign wr_half = wr_data[15:0];

    // Byte enable
    logic [3:0] be;
    always_comb begin
        be = 4'b0000;
        case (access_width)
            WIDTH_WORD: be = 4'b1111;
            WIDTH_HALF: be = addr_bit1 ? 4'b1100 : 4'b0011;
            WIDTH_BYTE: begin
                case (addr_bits10)
                    2'b00: be = 4'b0001;
                    2'b01: be = 4'b0010;
                    2'b10: be = 4'b0100;
                    2'b11: be = 4'b1000;
                endcase
            end
            default: be = 4'b0000;
        endcase
    end

    // Write data replication
    logic [31:0] wr_data_rep;
    always_comb begin
        case (access_width)
            WIDTH_BYTE: wr_data_rep = {4{wr_byte}};
            WIDTH_HALF: wr_data_rep = {2{wr_half}};
            default:    wr_data_rep = wr_data;
        endcase
    end

    logic [7:0] wr_rep_b0, wr_rep_b1, wr_rep_b2, wr_rep_b3;
    assign wr_rep_b0 = wr_data_rep[7:0];
    assign wr_rep_b1 = wr_data_rep[15:8];
    assign wr_rep_b2 = wr_data_rep[23:16];
    assign wr_rep_b3 = wr_data_rep[31:24];

    // Synchronous write
    always_ff @(posedge clk) begin
        if (dm_wr) begin
            if (be[0]) mem[word_addr][7:0]   <= wr_rep_b0;
            if (be[1]) mem[word_addr][15:8]  <= wr_rep_b1;
            if (be[2]) mem[word_addr][23:16] <= wr_rep_b2;
            if (be[3]) mem[word_addr][31:24] <= wr_rep_b3;
        end
    end

    // Asynchronous read
    logic [31:0] mem_word;
    assign mem_word = mem[word_addr];

    logic [15:0] mem_half_hi, mem_half_lo;
    logic [7:0]  mem_byte_0, mem_byte_1, mem_byte_2, mem_byte_3;
    assign mem_half_hi = mem_word[31:16];
    assign mem_half_lo = mem_word[15:0];
    assign mem_byte_0  = mem_word[7:0];
    assign mem_byte_1  = mem_word[15:8];
    assign mem_byte_2  = mem_word[23:16];
    assign mem_byte_3  = mem_word[31:24];

    logic half_sign_hi, half_sign_lo;
    logic byte_sign_0, byte_sign_1, byte_sign_2, byte_sign_3;
    assign half_sign_hi = mem_half_hi[15];
    assign half_sign_lo = mem_half_lo[15];
    assign byte_sign_0  = mem_byte_0[7];
    assign byte_sign_1  = mem_byte_1[7];
    assign byte_sign_2  = mem_byte_2[7];
    assign byte_sign_3  = mem_byte_3[7];

    // Half/byte selection
    logic [15:0] half;
    logic [7:0]  byte_val;
    logic        half_sign;
    logic        byte_sign;

    always_comb begin
        half      = addr_bit1 ? mem_half_hi : mem_half_lo;
        half_sign = addr_bit1 ? half_sign_hi : half_sign_lo;
        byte_val  = mem_byte_0;
        byte_sign = byte_sign_0;
        case (addr_bits10)
            2'b00: begin byte_val = mem_byte_0; byte_sign = byte_sign_0; end
            2'b01: begin byte_val = mem_byte_1; byte_sign = byte_sign_1; end
            2'b10: begin byte_val = mem_byte_2; byte_sign = byte_sign_2; end
            2'b11: begin byte_val = mem_byte_3; byte_sign = byte_sign_3; end
        endcase
    end

    // Read output
    always_comb begin
        case (access_width)
            WIDTH_WORD: rd_data = mem_word;
            WIDTH_HALF: rd_data = zero_ext ? {16'b0, half}    : {{16{half_sign}}, half};
            WIDTH_BYTE: rd_data = zero_ext ? {24'b0, byte_val} : {{24{byte_sign}}, byte_val};
            default:    rd_data = 32'b0;
        endcase
    end

endmodule