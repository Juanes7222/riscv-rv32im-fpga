// Shadow copy of the data memory for the VGA console.
//
// The write port lives in the processor clock domain and is driven by the
// same signals as the CPU's data memory, so the mirrored content is exact:
// sampling the write event in the VGA domain would tear the address and the
// data pair.  The read port lives in the VGA clock domain.
//
// wr_be and wr_data come from the data memory module itself: wr_be holds the
// byte enables of the pending write and wr_data the write data already
// replicated per byte lane, so both memories store the very same bytes.
`include "../shared/mem_config.vh"

module vga_mem_shadow #(
    parameter int DEPTH = 512
)(
    input  logic        wr_clk,
    input  logic        wr_en,
    input  logic [31:0] wr_addr,
    input  logic [31:0] wr_data,
    input  logic [3:0]  wr_be,
    input  logic        rd_clk,
    input  logic [31:0] rd_addr,
    output logic [31:0] rd_data
);
    localparam int ADDR_BITS = $clog2(DEPTH);

    // Four byte lanes: a byte write updates one lane only, exactly like the
    // CPU's data memory.
    (* ramstyle = "M10K" *) logic [7:0] lane0 [0:DEPTH-1];
    (* ramstyle = "M10K" *) logic [7:0] lane1 [0:DEPTH-1];
    (* ramstyle = "M10K" *) logic [7:0] lane2 [0:DEPTH-1];
    (* ramstyle = "M10K" *) logic [7:0] lane3 [0:DEPTH-1];

    // The lanes take the program image, exactly like the CPU's data memory,
    // so the mirror starts from the same content.  Without an image they
    // start empty, the way the M10K blocks come out of configuration.
    initial begin
        `ifdef DMEM_FILE
            logic [31:0] img [0:DEPTH-1];
            $readmemh(`DMEM_FILE, img);
            for (int i = 0; i < DEPTH; i++) begin
                lane0[i] = img[i][7:0];
                lane1[i] = img[i][15:8];
                lane2[i] = img[i][23:16];
                lane3[i] = img[i][31:24];
            end
        `else
            for (int i = 0; i < DEPTH; i++) begin
                lane0[i] = 8'h00;
                lane1[i] = 8'h00;
                lane2[i] = 8'h00;
                lane3[i] = 8'h00;
            end
        `endif
    end

    // The CPU indexes addr[14:2] regardless of DEPTH, so the hardware
    // truncates the index to the array depth.  The shadow does the same, so
    // the mirror shows exactly what the CPU's memory holds.
    logic [ADDR_BITS-1:0] wr_word;
    logic [ADDR_BITS-1:0] rd_word;
    assign wr_word = wr_addr[ADDR_BITS+1:2];
    assign rd_word = rd_addr[ADDR_BITS+1:2];

    always_ff @(posedge wr_clk) begin
        if (wr_en) begin
            if (wr_be[0]) lane0[wr_word] <= wr_data[7:0];
            if (wr_be[1]) lane1[wr_word] <= wr_data[15:8];
            if (wr_be[2]) lane2[wr_word] <= wr_data[23:16];
            if (wr_be[3]) lane3[wr_word] <= wr_data[31:24];
        end
    end

    logic [7:0] rd_b0, rd_b1, rd_b2, rd_b3;
    always_ff @(posedge rd_clk) begin
        rd_b0 <= lane0[rd_word];
        rd_b1 <= lane1[rd_word];
        rd_b2 <= lane2[rd_word];
        rd_b3 <= lane3[rd_word];
    end

    assign rd_data = {rd_b3, rd_b2, rd_b1, rd_b0};
endmodule
