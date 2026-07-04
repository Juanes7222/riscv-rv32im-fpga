// Pipeline screen writer - round-robin update of key pipeline stage signals
// into the VGA text-mode video memory. Runs on vga_pixel_clk.
// Refreshes 71 visible characters; full update = 71 cycles (~1.0 µs @ 74.25 MHz).

module screen_writer_pipeline (
    input  logic        clk,
    input  logic        rst_n,

    // IF stage
    input  logic [31:0] if_pc,
    input  logic [31:0] if_instruction,

    // ID stage
    input  logic [31:0] id_pc,
    input  logic [31:0] id_instruction,

    // EX stage
    input  logic [31:0] ex_alu_result,
    input  logic [31:0] ex_instruction,

    // MEM stage
    input  logic [31:0] mem_alu_result,
    input  logic [31:0] mem_dm_rd_data,

    // WB stage
    input  logic [31:0] wb_rd_data,
    input  logic [4:0]  wb_rd_addr,

    // Hazard / control
    input  logic        stall,
    input  logic        flush,
    input  logic        load_use_hazard,

    // Video memory interface
    output logic        vmem_wr_en,
    output logic [12:0] vmem_wr_addr,
    output logic [15:0] vmem_wr_data
);

    // Address map (matching screen_pipeline.mif placeholder positions)
    localparam int IF_PC_ADDR      = 9;
    localparam int IF_IR_ADDR      = 22;
    localparam int ID_PC_ADDR      = 169;
    localparam int ID_IR_ADDR      = 182;
    localparam int EX_ALU_ADDR     = 330;
    localparam int EX_IR_ADDR      = 343;
    localparam int MEM_ALU_ADDR    = 490;
    localparam int MEM_DM_ADDR     = 503;
    localparam int WB_RD_ADDR      = 649;
    localparam int WB_RA_ADDR      = 662;
    localparam int STALL_ADDR      = 807;
    localparam int FLUSH_ADDR      = 816;
    localparam int LDUSE_ADDR      = 825;

    // Round-robin index
    logic [6:0] idx;

    // Hex digits LUT
    function automatic logic [7:0] hex_digit(input logic [3:0] nibble);
        hex_digit = (nibble < 4'd10) ? (8'd48 + nibble) : (8'd55 + nibble);
    endfunction

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            idx <= '0;
        end else begin
            idx <= (idx >= 7'd76) ? 7'd0 : idx + 7'd1;
        end
    end

    always_comb begin
        // Default: no write
        vmem_wr_en   = 1'b0;
        vmem_wr_addr = '0;
        vmem_wr_data = '0;

        // Each case writes one character to video memory.
        // 71 characters total (indices 0..70).
        unique case (idx)
            // IF PC (8 hex digits) - indices 0..7
            7'd0:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_PC_ADDR+0; vmem_wr_data={8'h07, hex_digit(if_pc[31:28])}; end
            7'd1:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_PC_ADDR+1; vmem_wr_data={8'h07, hex_digit(if_pc[27:24])}; end
            7'd2:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_PC_ADDR+2; vmem_wr_data={8'h07, hex_digit(if_pc[23:20])}; end
            7'd3:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_PC_ADDR+3; vmem_wr_data={8'h07, hex_digit(if_pc[19:16])}; end
            7'd4:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_PC_ADDR+4; vmem_wr_data={8'h07, hex_digit(if_pc[15:12])}; end
            7'd5:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_PC_ADDR+5; vmem_wr_data={8'h07, hex_digit(if_pc[11: 8])}; end
            7'd6:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_PC_ADDR+6; vmem_wr_data={8'h07, hex_digit(if_pc[ 7: 4])}; end
            7'd7:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_PC_ADDR+7; vmem_wr_data={8'h07, hex_digit(if_pc[ 3: 0])}; end

            // IF Instruction (8 hex digits) - indices 8..15
            7'd8:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_IR_ADDR+0; vmem_wr_data={8'h07, hex_digit(if_instruction[31:28])}; end
            7'd9:  begin vmem_wr_en=1'b1; vmem_wr_addr=IF_IR_ADDR+1; vmem_wr_data={8'h07, hex_digit(if_instruction[27:24])}; end
            7'd10: begin vmem_wr_en=1'b1; vmem_wr_addr=IF_IR_ADDR+2; vmem_wr_data={8'h07, hex_digit(if_instruction[23:20])}; end
            7'd11: begin vmem_wr_en=1'b1; vmem_wr_addr=IF_IR_ADDR+3; vmem_wr_data={8'h07, hex_digit(if_instruction[19:16])}; end
            7'd12: begin vmem_wr_en=1'b1; vmem_wr_addr=IF_IR_ADDR+4; vmem_wr_data={8'h07, hex_digit(if_instruction[15:12])}; end
            7'd13: begin vmem_wr_en=1'b1; vmem_wr_addr=IF_IR_ADDR+5; vmem_wr_data={8'h07, hex_digit(if_instruction[11: 8])}; end
            7'd14: begin vmem_wr_en=1'b1; vmem_wr_addr=IF_IR_ADDR+6; vmem_wr_data={8'h07, hex_digit(if_instruction[ 7: 4])}; end
            7'd15: begin vmem_wr_en=1'b1; vmem_wr_addr=IF_IR_ADDR+7; vmem_wr_data={8'h07, hex_digit(if_instruction[ 3: 0])}; end

            // ID PC (8) - 16..23
            7'd16: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_PC_ADDR+0; vmem_wr_data={8'h07, hex_digit(id_pc[31:28])}; end
            7'd17: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_PC_ADDR+1; vmem_wr_data={8'h07, hex_digit(id_pc[27:24])}; end
            7'd18: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_PC_ADDR+2; vmem_wr_data={8'h07, hex_digit(id_pc[23:20])}; end
            7'd19: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_PC_ADDR+3; vmem_wr_data={8'h07, hex_digit(id_pc[19:16])}; end
            7'd20: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_PC_ADDR+4; vmem_wr_data={8'h07, hex_digit(id_pc[15:12])}; end
            7'd21: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_PC_ADDR+5; vmem_wr_data={8'h07, hex_digit(id_pc[11: 8])}; end
            7'd22: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_PC_ADDR+6; vmem_wr_data={8'h07, hex_digit(id_pc[ 7: 4])}; end
            7'd23: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_PC_ADDR+7; vmem_wr_data={8'h07, hex_digit(id_pc[ 3: 0])}; end

            // ID Instruction (8) - 24..31
            7'd24: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_IR_ADDR+0; vmem_wr_data={8'h07, hex_digit(id_instruction[31:28])}; end
            7'd25: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_IR_ADDR+1; vmem_wr_data={8'h07, hex_digit(id_instruction[27:24])}; end
            7'd26: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_IR_ADDR+2; vmem_wr_data={8'h07, hex_digit(id_instruction[23:20])}; end
            7'd27: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_IR_ADDR+3; vmem_wr_data={8'h07, hex_digit(id_instruction[19:16])}; end
            7'd28: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_IR_ADDR+4; vmem_wr_data={8'h07, hex_digit(id_instruction[15:12])}; end
            7'd29: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_IR_ADDR+5; vmem_wr_data={8'h07, hex_digit(id_instruction[11: 8])}; end
            7'd30: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_IR_ADDR+6; vmem_wr_data={8'h07, hex_digit(id_instruction[ 7: 4])}; end
            7'd31: begin vmem_wr_en=1'b1; vmem_wr_addr=ID_IR_ADDR+7; vmem_wr_data={8'h07, hex_digit(id_instruction[ 3: 0])}; end

            // EX ALU result (8) - 32..39
            7'd32: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_ALU_ADDR+0; vmem_wr_data={8'h07, hex_digit(ex_alu_result[31:28])}; end
            7'd33: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_ALU_ADDR+1; vmem_wr_data={8'h07, hex_digit(ex_alu_result[27:24])}; end
            7'd34: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_ALU_ADDR+2; vmem_wr_data={8'h07, hex_digit(ex_alu_result[23:20])}; end
            7'd35: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_ALU_ADDR+3; vmem_wr_data={8'h07, hex_digit(ex_alu_result[19:16])}; end
            7'd36: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_ALU_ADDR+4; vmem_wr_data={8'h07, hex_digit(ex_alu_result[15:12])}; end
            7'd37: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_ALU_ADDR+5; vmem_wr_data={8'h07, hex_digit(ex_alu_result[11: 8])}; end
            7'd38: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_ALU_ADDR+6; vmem_wr_data={8'h07, hex_digit(ex_alu_result[ 7: 4])}; end
            7'd39: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_ALU_ADDR+7; vmem_wr_data={8'h07, hex_digit(ex_alu_result[ 3: 0])}; end

            // EX Instruction (8) - 40..47
            7'd40: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_IR_ADDR+0; vmem_wr_data={8'h07, hex_digit(ex_instruction[31:28])}; end
            7'd41: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_IR_ADDR+1; vmem_wr_data={8'h07, hex_digit(ex_instruction[27:24])}; end
            7'd42: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_IR_ADDR+2; vmem_wr_data={8'h07, hex_digit(ex_instruction[23:20])}; end
            7'd43: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_IR_ADDR+3; vmem_wr_data={8'h07, hex_digit(ex_instruction[19:16])}; end
            7'd44: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_IR_ADDR+4; vmem_wr_data={8'h07, hex_digit(ex_instruction[15:12])}; end
            7'd45: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_IR_ADDR+5; vmem_wr_data={8'h07, hex_digit(ex_instruction[11: 8])}; end
            7'd46: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_IR_ADDR+6; vmem_wr_data={8'h07, hex_digit(ex_instruction[ 7: 4])}; end
            7'd47: begin vmem_wr_en=1'b1; vmem_wr_addr=EX_IR_ADDR+7; vmem_wr_data={8'h07, hex_digit(ex_instruction[ 3: 0])}; end

            // MEM ALU result (8) - 48..55
            7'd48: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_ALU_ADDR+0; vmem_wr_data={8'h07, hex_digit(mem_alu_result[31:28])}; end
            7'd49: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_ALU_ADDR+1; vmem_wr_data={8'h07, hex_digit(mem_alu_result[27:24])}; end
            7'd50: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_ALU_ADDR+2; vmem_wr_data={8'h07, hex_digit(mem_alu_result[23:20])}; end
            7'd51: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_ALU_ADDR+3; vmem_wr_data={8'h07, hex_digit(mem_alu_result[19:16])}; end
            7'd52: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_ALU_ADDR+4; vmem_wr_data={8'h07, hex_digit(mem_alu_result[15:12])}; end
            7'd53: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_ALU_ADDR+5; vmem_wr_data={8'h07, hex_digit(mem_alu_result[11: 8])}; end
            7'd54: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_ALU_ADDR+6; vmem_wr_data={8'h07, hex_digit(mem_alu_result[ 7: 4])}; end
            7'd55: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_ALU_ADDR+7; vmem_wr_data={8'h07, hex_digit(mem_alu_result[ 3: 0])}; end

            // MEM DM read data (8) - 56..63
            7'd56: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_DM_ADDR+0; vmem_wr_data={8'h07, hex_digit(mem_dm_rd_data[31:28])}; end
            7'd57: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_DM_ADDR+1; vmem_wr_data={8'h07, hex_digit(mem_dm_rd_data[27:24])}; end
            7'd58: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_DM_ADDR+2; vmem_wr_data={8'h07, hex_digit(mem_dm_rd_data[23:20])}; end
            7'd59: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_DM_ADDR+3; vmem_wr_data={8'h07, hex_digit(mem_dm_rd_data[19:16])}; end
            7'd60: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_DM_ADDR+4; vmem_wr_data={8'h07, hex_digit(mem_dm_rd_data[15:12])}; end
            7'd61: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_DM_ADDR+5; vmem_wr_data={8'h07, hex_digit(mem_dm_rd_data[11: 8])}; end
            7'd62: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_DM_ADDR+6; vmem_wr_data={8'h07, hex_digit(mem_dm_rd_data[ 7: 4])}; end
            7'd63: begin vmem_wr_en=1'b1; vmem_wr_addr=MEM_DM_ADDR+7; vmem_wr_data={8'h07, hex_digit(mem_dm_rd_data[ 3: 0])}; end

            // WB rd_data (8) - 64..71
            7'd64: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RD_ADDR+0; vmem_wr_data={8'h07, hex_digit(wb_rd_data[31:28])}; end
            7'd65: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RD_ADDR+1; vmem_wr_data={8'h07, hex_digit(wb_rd_data[27:24])}; end
            7'd66: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RD_ADDR+2; vmem_wr_data={8'h07, hex_digit(wb_rd_data[23:20])}; end
            7'd67: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RD_ADDR+3; vmem_wr_data={8'h07, hex_digit(wb_rd_data[19:16])}; end
            7'd68: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RD_ADDR+4; vmem_wr_data={8'h07, hex_digit(wb_rd_data[15:12])}; end
            7'd69: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RD_ADDR+5; vmem_wr_data={8'h07, hex_digit(wb_rd_data[11: 8])}; end
            7'd70: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RD_ADDR+6; vmem_wr_data={8'h07, hex_digit(wb_rd_data[ 7: 4])}; end
            7'd71: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RD_ADDR+7; vmem_wr_data={8'h07, hex_digit(wb_rd_data[ 3: 0])}; end

            // WB rd_addr (2) - 72..73
            7'd72: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RA_ADDR+0; vmem_wr_data={8'h07, hex_digit({3'b0, wb_rd_addr[4:3]})}; end
            7'd73: begin vmem_wr_en=1'b1; vmem_wr_addr=WB_RA_ADDR+1; vmem_wr_data={8'h07, hex_digit(wb_rd_addr[2:0])}; end

            // Control flags (1 each) - 74..76
            7'd74: begin vmem_wr_en=1'b1; vmem_wr_addr=STALL_ADDR; vmem_wr_data={8'h07, stall ? 8'h31 : 8'h30}; end
            7'd75: begin vmem_wr_en=1'b1; vmem_wr_addr=FLUSH_ADDR; vmem_wr_data={8'h07, flush ? 8'h31 : 8'h30}; end
            7'd76: begin vmem_wr_en=1'b1; vmem_wr_addr=LDUSE_ADDR; vmem_wr_data={8'h07, load_use_hazard ? 8'h31 : 8'h30}; end

            // Default case to avoid latch warnings
            default: ;
        endcase
    end

endmodule