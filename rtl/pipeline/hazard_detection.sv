// Hazard detection unit: detects load-use hazards and division stalls.
// RAW hazards on ALU results are resolved by forwarding from EX/MEM
// and MEM/WB - no stall is needed. Only loads (whose data is available
// at the end of MEM, into WB) require a stall when a consumer is in ID.
//
// Note: mem_raw_hazard is restricted to load instructions (WB_MEM path).
// Without this guard, a back-to-back sequence like AUIPC-->ADDI that
// writes and reads the same register would assert stall forever because
// each copy of the instruction entering MEM keeps triggering the stall
// against the stalled copy in ID - a permanent deadlock.
module hazard_detection_unit (
    input  logic [4:0]  id_rs1_addr,
    input  logic [4:0]  id_rs2_addr,
    input  logic [4:0]  ex_rd_addr,
    input  logic [1:0]  ex_ru_data_wr_src,
    input  logic [4:0]  mem_rd_addr,
    input  logic        mem_ru_wr,
    input  logic [1:0]  mem_ru_data_wr_src,
    input  logic        div_busy,
    output logic        stall,
    output logic        load_use
);
    logic load_use_hazard;
    logic mem_raw_hazard;

    localparam [1:0] WB_MEM = 2'b01;

    always_comb begin
        // load-use: a load in EX whose destination is read by ID.
        load_use_hazard = (ex_ru_data_wr_src == WB_MEM) &&
                          (ex_rd_addr != 5'b0) &&
                          ((ex_rd_addr == id_rs1_addr) || (ex_rd_addr == id_rs2_addr));

        // mem_raw: a load in MEM whose destination is read by ID.
        // ALU instructions in MEM are excluded - forwarding resolves them.
        mem_raw_hazard = mem_ru_wr &&
                         (mem_ru_data_wr_src == WB_MEM) &&
                         (mem_rd_addr != 5'b0) &&
                         ((mem_rd_addr == id_rs1_addr) || (mem_rd_addr == id_rs2_addr));

        load_use = load_use_hazard;
        stall    = load_use_hazard || mem_raw_hazard || div_busy;
    end
endmodule
