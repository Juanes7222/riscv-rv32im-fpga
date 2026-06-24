// Synchronous-read data memory with byte-enable writes.
// Uses four independent byte-lane arrays for guaranteed M10K inference.
// All byte/half/word selection and sign extension is applied to
// the registered memory output, producing the final rd_data.
`include "../shared/mem_config.vh"

module data_memory_pipe #(
    parameter int unsigned DMEM_DEPTH = 8192
)(
    input  logic        clk,
    input  logic [31:0] addr,
    input  logic [31:0] wr_data,
    input  logic        dm_wr,
    input  logic [2:0]  dm_ctrl,
    output logic [31:0] rd_data
);

    // Four byte-lane arrays.  Each independient array lets Quartus infer
    // a dedicated M10K block with native byte-enable behaviour.
    (* ramstyle = "M10K" *) logic [7:0] mem_b0 [0:DMEM_DEPTH-1];
    (* ramstyle = "M10K" *) logic [7:0] mem_b1 [0:DMEM_DEPTH-1];
    (* ramstyle = "M10K" *) logic [7:0] mem_b2 [0:DMEM_DEPTH-1];
    (* ramstyle = "M10K" *) logic [7:0] mem_b3 [0:DMEM_DEPTH-1];

    initial begin
        `ifdef DMEM_FILE
            $readmemh(`DMEM_FILE, mem_b0);
            // NOTE: $readmemh loads 32-bit words packed into byte lanes.
            // For synthesis the initial content is embedded via the
            // generated .mif file; the sim-only path is simpler.
        `endif
    end


    localparam [1:0] WIDTH_BYTE = 2'b00;
    localparam [1:0] WIDTH_HALF = 2'b01;
    localparam [1:0] WIDTH_WORD = 2'b10;

    logic [1:0] access_width;
    logic       zero_ext;
    assign access_width = dm_ctrl[1:0];
    assign zero_ext     = dm_ctrl[2];


    logic [12:0] word_addr;
    logic        addr_bit1;
    logic [1:0]  addr_bits10;
    assign word_addr   = addr[14:2];
    assign addr_bit1   = addr[1];
    assign addr_bits10 = addr[1:0];


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

    // Write data is replicated across byte lanes so that any enabled lane
    // receives the byte for its position.  For a store byte to lane 2 the
    // byte on lanes 0,1,3 is also the store byte, but we only write the
    // enabled lane, so the extra copies have no effect.
    logic [31:0] wr_data_rep;
    logic [7:0]  wr_byte;
    logic [15:0] wr_half;
    assign wr_byte = wr_data[7:0];
    assign wr_half = wr_data[15:0];

    always_comb begin
        case (access_width)
            WIDTH_BYTE: wr_data_rep = {4{wr_byte}};
            WIDTH_HALF: wr_data_rep = {2{wr_half}};
            default:    wr_data_rep = wr_data;
        endcase
    end


    logic [7:0] rd_b0, rd_b1, rd_b2, rd_b3;
    logic [31:0] mem_word_reg;

    always_ff @(posedge clk) begin
        // Write — only affected byte lanes
        if (dm_wr && be[0]) mem_b0[word_addr] <= wr_data_rep[7:0];
        if (dm_wr && be[1]) mem_b1[word_addr] <= wr_data_rep[15:8];
        if (dm_wr && be[2]) mem_b2[word_addr] <= wr_data_rep[23:16];
        if (dm_wr && be[3]) mem_b3[word_addr] <= wr_data_rep[31:24];

        // Read — always read from all four lanes
        rd_b0 <= mem_b0[word_addr];
        rd_b1 <= mem_b1[word_addr];
        rd_b2 <= mem_b2[word_addr];
        rd_b3 <= mem_b3[word_addr];
    end

    assign mem_word_reg = {rd_b3, rd_b2, rd_b1, rd_b0};


    logic [1:0] access_width_reg;
    logic       zero_ext_reg;
    logic       addr_bit1_reg;
    logic [1:0] addr_bits10_reg;

    always_ff @(posedge clk) begin
        access_width_reg <= access_width;
        zero_ext_reg     <= zero_ext;
        addr_bit1_reg    <= addr_bit1;
        addr_bits10_reg  <= addr_bits10;
    end


    logic [15:0] mem_half_hi, mem_half_lo;
    logic [7:0]  mem_byte_0, mem_byte_1, mem_byte_2, mem_byte_3;
    assign mem_half_hi = mem_word_reg[31:16];
    assign mem_half_lo = mem_word_reg[15:0];
    assign mem_byte_0  = mem_word_reg[7:0];
    assign mem_byte_1  = mem_word_reg[15:8];
    assign mem_byte_2  = mem_word_reg[23:16];
    assign mem_byte_3  = mem_word_reg[31:24];

    logic half_sign_hi, half_sign_lo;
    logic byte_sign_0, byte_sign_1, byte_sign_2, byte_sign_3;
    assign half_sign_hi = mem_half_hi[15];
    assign half_sign_lo = mem_half_lo[15];
    assign byte_sign_0  = mem_byte_0[7];
    assign byte_sign_1  = mem_byte_1[7];
    assign byte_sign_2  = mem_byte_2[7];
    assign byte_sign_3  = mem_byte_3[7];

    logic [15:0] half;
    logic [7:0]  byte_val;
    logic        half_sign;
    logic        byte_sign;

    always_comb begin
        half      = addr_bit1_reg ? mem_half_hi : mem_half_lo;
        half_sign = addr_bit1_reg ? half_sign_hi : half_sign_lo;
        byte_val  = mem_byte_0;
        byte_sign = byte_sign_0;
        case (addr_bits10_reg)
            2'b00: begin byte_val = mem_byte_0; byte_sign = byte_sign_0; end
            2'b01: begin byte_val = mem_byte_1; byte_sign = byte_sign_1; end
            2'b10: begin byte_val = mem_byte_2; byte_sign = byte_sign_2; end
            2'b11: begin byte_val = mem_byte_3; byte_sign = byte_sign_3; end
        endcase
    end


    always_comb begin
        case (access_width_reg)
            WIDTH_WORD: rd_data = mem_word_reg;
            WIDTH_HALF: rd_data = zero_ext_reg ? {16'b0, half}    : {{16{half_sign}}, half};
            WIDTH_BYTE: rd_data = zero_ext_reg ? {24'b0, byte_val} : {{24{byte_sign}}, byte_val};
            default:    rd_data = 32'b0;
        endcase
    end

endmodule
