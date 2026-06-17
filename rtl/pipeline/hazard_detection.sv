// Hazard detection unit: detects load-use hazards and division stalls.
//
// Two distinct outputs:
//   - `stall`     : combined signal; asserted for either load-use or div_busy.
//                   Used by IF/ID (which must hold in both cases) and the PC.
//   - `load_use`  : asserted only on load-use. Used by ID/EX (which must
//                   bubble on load-use, not hold, so the load can advance
//                   to MEM and the consumer can enter EX in the next cycle).
//
// Per the standard MIPS load-use stall:
//   - On load-use: IF/ID holds, ID/EX bubbles (the load is killed from
//     ID/EX so it can advance to MEM; the consumer is then allowed to
//     advance to EX in the next cycle and forward from MEM/WB).
//   - On div_busy: IF/ID holds, ID/EX holds (the div must stay in EX for
//     34 cycles; the rest of the pipeline also holds).
module hazard_detection_unit (
    // Load-use detection
    input  logic [4:0]  id_rs1_addr,
    input  logic [4:0]  id_rs2_addr,
    input  logic [4:0]  ex_rd_addr,
    input  logic [1:0]  ex_ru_data_wr_src, // 01 = load instruction in EX
    // Division stall
    input  logic        div_busy,
    output logic        stall,
    output logic        load_use
);
    logic load_use_hazard;

    always_comb begin
        // Load-use: instruction in EX is a load (ru_data_wr_src == 01) and
        // its destination matches a source of the instruction currently in ID.
        load_use_hazard = (ex_ru_data_wr_src == 2'b01) &&
                          (ex_rd_addr != 5'b0) &&
                          ((ex_rd_addr == id_rs1_addr) || (ex_rd_addr == id_rs2_addr));
        load_use = load_use_hazard;
        stall    = load_use_hazard || div_busy;
    end
endmodule