module data_memory #(
    parameter int unsigned DMEM_DEPTH = 8192    // words (32 KB)
) (
    input  logic        clk,
    input  logic [31:0] addr,
    input  logic [31:0] wr_data,
    input  logic        dm_wr,
    input  logic [2:0]  dm_ctrl,
    output logic [31:0] rd_data
);

    // Memory array
    // Word-addressed; Quartus infers M10K blocks from this declaration.
    // $readmemh is only called when MEM_FILE is non-empty (data + BSS init).
    logic [31:0] mem [0:DMEM_DEPTH-1];


    // dm_ctrl field decoding
    // dm_ctrl[1:0] — access width: 00=byte, 01=halfword, 10=word
    // dm_ctrl[2]   — extension:    0=sign,  1=zero  (loads only)
    localparam [1:0] WIDTH_BYTE = 2'b00;   // funct3[1:0] = 00 → LB/SB/LBU
    localparam [1:0] WIDTH_HALF = 2'b01;   // funct3[1:0] = 01 → LH/SH/LHU
    localparam [1:0] WIDTH_WORD = 2'b10;   // funct3[1:0] = 10 → LW/SW

    logic [1:0] access_width;
    logic       zero_ext;

    assign access_width = dm_ctrl[1:0];
    assign zero_ext     = dm_ctrl[2];

    // Byte enable generation (combinational)
    logic [3:0] be;

    always_comb begin
        be = 4'b0000;
        case (access_width)
            WIDTH_WORD: be = 4'b1111;
            WIDTH_HALF: be = addr[1] ? 4'b1100 : 4'b0011;
            WIDTH_BYTE: begin
                case (addr[1:0])
                    2'b00: be = 4'b0001;
                    2'b01: be = 4'b0010;
                    2'b10: be = 4'b0100;
                    2'b11: be = 4'b1000;
                endcase
            end
            default: be = 4'b0000;
        endcase
    end

    // Write data replication (combinational)
    // Byte lanes not selected by 'be' are written with replicated data but
    // the enable prevents those lanes from being stored.
    logic [31:0] wr_data_rep;

    always_comb begin
        case (access_width)
            WIDTH_BYTE: wr_data_rep = {4{wr_data[7:0]}};
            WIDTH_HALF: wr_data_rep = {2{wr_data[15:0]}};
            default:    wr_data_rep = wr_data;            // WIDTH_WORD
        endcase
    end

    // Synchronous write with byte enables
    always_ff @(posedge clk) begin
        if (dm_wr) begin
            if (be[0]) mem[addr[14:2]][7:0]   <= wr_data_rep[7:0];
            if (be[1]) mem[addr[14:2]][15:8]  <= wr_data_rep[15:8];
            if (be[2]) mem[addr[14:2]][23:16] <= wr_data_rep[23:16];
            if (be[3]) mem[addr[14:2]][31:24] <= wr_data_rep[31:24];
        end
    end

    // Asynchronous read
    // Full 32-bit word read combinationally; extraction and extension follow.
    logic [31:0] mem_word;
    assign mem_word = mem[addr[14:2]];

    // Read extraction and extension (combinational)
    always_comb begin
        rd_data = 32'b0;
        case (access_width)
            WIDTH_WORD: rd_data = mem_word;

            WIDTH_HALF: begin
                logic [15:0] half;
                half = addr[1] ? mem_word[31:16] : mem_word[15:0];
                rd_data = zero_ext ? {16'b0, half}
                                   : {{16{half[15]}}, half};
            end

            WIDTH_BYTE: begin
                logic [7:0] byte_val;
                case (addr[1:0])
                    2'b00: byte_val = mem_word[7:0];
                    2'b01: byte_val = mem_word[15:8];
                    2'b10: byte_val = mem_word[23:16];
                    2'b11: byte_val = mem_word[31:24];
                endcase
                rd_data = zero_ext ? {24'b0, byte_val}
                                   : {{24{byte_val[7]}}, byte_val};
            end

            default: rd_data = 32'b0;
        endcase
    end

endmodule