`include "../shared/mem_config.vh"

// Data memory: half-cycle M10K read, byte-enable writes.
//
// The single-cycle CPU computes the load address right after the rising edge
// and the register file takes the loaded word at the next rising edge, so the
// array only has the second half of the cycle.  The read address is captured
// on the falling edge and the output of the block is combinational, which
// keeps the load inside its own cycle (CPI = 1) and still lets Quartus infer
// M10K instead of 32 768 registers (ADR 048).
//
// Four byte-lane arrays, one per byte, guarantee the M10K inference and give
// native byte enables; the selection and sign extension run after the block
// output, exactly like the pipelined memory.
module data_memory #(
    parameter int unsigned DMEM_DEPTH = 8192
) (
    input  logic        clk,
    input  logic [31:0] addr,
    input  logic [31:0] wr_data,
    input  logic        dm_wr,
    input  logic [2:0]  dm_ctrl,
    output logic [31:0] rd_data,
    // Byte enables and per-lane write data of the pending write, exported
    // for the VGA console shadow so it mirrors this memory exactly.
    output logic [3:0]  dbg_wr_be,
    output logic [31:0] dbg_wr_data
);

    (* ramstyle = "M10K" *) logic [7:0] mem_b0 [0:DMEM_DEPTH-1];
    (* ramstyle = "M10K" *) logic [7:0] mem_b1 [0:DMEM_DEPTH-1];
    (* ramstyle = "M10K" *) logic [7:0] mem_b2 [0:DMEM_DEPTH-1];
    (* ramstyle = "M10K" *) logic [7:0] mem_b3 [0:DMEM_DEPTH-1];

    initial begin
        `ifdef DMEM_FILE
            // Load 32-bit words from the .mem file into a temporary array,
            // then distribute bytes to the four lane memories.
            logic [31:0] tmp [0:DMEM_DEPTH-1];
            $readmemh(`DMEM_FILE, tmp);
            for (int i = 0; i < DMEM_DEPTH; i++) begin
                mem_b0[i] = tmp[i][7:0];
                mem_b1[i] = tmp[i][15:8];
                mem_b2[i] = tmp[i][23:16];
                mem_b3[i] = tmp[i][31:24];
            end
        `endif
    end

    localparam [1:0] WIDTH_BYTE = 2'b00;
    localparam [1:0] WIDTH_HALF = 2'b01;
    localparam [1:0] WIDTH_WORD = 2'b10;

    logic [1:0] access_width;
    logic       zero_ext;
    assign access_width = dm_ctrl[1:0];
    assign zero_ext     = dm_ctrl[2];

    // The word index follows DMEM_DEPTH; a hardcoded 13-bit slice made the
    // parameter useless and put every address outside a 512-word array
    // (ADR 047).
    localparam int unsigned ADDR_BITS = $clog2(DMEM_DEPTH);
    logic [ADDR_BITS-1:0] word_addr;
    logic        addr_bit1;
    logic [1:0]  addr_bits10;
    assign word_addr   = addr[ADDR_BITS+1:2];
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

    // The console shadow writes what this memory writes, so it takes the
    // enables and the lane data from here instead of recomputing them.
    assign dbg_wr_be   = be;
    assign dbg_wr_data = wr_data_rep;

    // Synchronous write, only the enabled byte lanes.
    always_ff @(posedge clk) begin
        if (dm_wr && be[0]) mem_b0[word_addr] <= wr_rep_b0;
        if (dm_wr && be[1]) mem_b1[word_addr] <= wr_rep_b1;
        if (dm_wr && be[2]) mem_b2[word_addr] <= wr_rep_b2;
        if (dm_wr && be[3]) mem_b3[word_addr] <= wr_rep_b3;
    end

    // Half-cycle read: the address is captured on the falling edge, so the
    // lane outputs settle before the rising edge that writes the register
    // file.  A store at the previous rising edge is already in the lanes.
    logic [ADDR_BITS-1:0] word_addr_q;
    always_ff @(negedge clk) word_addr_q <= word_addr;

    logic [7:0] rd_b0, rd_b1, rd_b2, rd_b3;
    assign rd_b0 = mem_b0[word_addr_q];
    assign rd_b1 = mem_b1[word_addr_q];
    assign rd_b2 = mem_b2[word_addr_q];
    assign rd_b3 = mem_b3[word_addr_q];

    logic [31:0] mem_word;
    assign mem_word = {rd_b3, rd_b2, rd_b1, rd_b0};

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
