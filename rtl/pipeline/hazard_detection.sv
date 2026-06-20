// Hazard detection unit: detects RAW hazards and division stalls.
module hazard_detection_unit (
    input  logic [4:0]  id_rs1_addr,
    input  logic [4:0]  id_rs2_addr,
    input  logic [4:0]  ex_rd_addr,
    input  logic [1:0]  ex_ru_data_wr_src,
    input  logic [4:0]  mem_rd_addr,
    input  logic        mem_ru_wr,
    input  logic        div_busy,
    output logic        stall,
    output logic        load_use
);
    logic load_use_hazard;
    logic mem_raw_hazard;

    always_comb begin
        load_use_hazard = (ex_ru_data_wr_src == 2'b01) &&
                          (ex_rd_addr != 5'b0) &&
                          ((ex_rd_addr == id_rs1_addr) || (ex_rd_addr == id_rs2_addr));

        mem_raw_hazard = mem_ru_wr &&
                          (mem_rd_addr != 5'b0) &&
                          ((mem_rd_addr == id_rs1_addr) || (mem_rd_addr == id_rs2_addr));

        load_use = load_use_hazard;
        stall    = load_use_hazard || mem_raw_hazard || div_busy;
    end
endmodule
