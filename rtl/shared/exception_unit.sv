// Synchronous RV32IM exceptions for the implemented M-only execution environment.
// Misaligned data accesses trap before any register or memory side effect.
module exception_unit (
    input logic valid,
    input logic [31:0] instruction,
    input logic [31:0] pc,
    input logic [31:0] data_address,
    input logic control_taken,
    input logic [31:0] control_target,
    output logic trap,
    output logic [4:0] cause,
    output logic [31:0] value
);
    logic legal_encoding;
    logic [6:0] opcode, funct7;
    logic [2:0] funct3;
    logic misaligned_data;
    assign opcode = instruction[6:0];
    assign funct3 = instruction[14:12];
    assign funct7 = instruction[31:25];

    always_comb begin
        legal_encoding = 1'b0;
        case (opcode)
            7'h37, 7'h17, 7'h6f: legal_encoding = 1'b1;
            7'h67: legal_encoding = (funct3 == 3'b000);
            7'h63: legal_encoding = (funct3 == 3'b000 || funct3 == 3'b001 ||
                                    funct3 == 3'b100 || funct3 == 3'b101 ||
                                    funct3 == 3'b110 || funct3 == 3'b111);
            7'h03: legal_encoding = (funct3 == 3'b000 || funct3 == 3'b001 ||
                                    funct3 == 3'b010 || funct3 == 3'b100 || funct3 == 3'b101);
            7'h23: legal_encoding = (funct3 == 3'b000 || funct3 == 3'b001 || funct3 == 3'b010);
            7'h13: begin
                case (funct3)
                    3'b001: legal_encoding = (funct7 == 7'h00);
                    3'b101: legal_encoding = (funct7 == 7'h00 || funct7 == 7'h20);
                    default: legal_encoding = 1'b1;
                endcase
            end
            7'h33: legal_encoding = (funct7 == 7'h00 || funct7 == 7'h01 ||
                                     (funct7 == 7'h20 && (funct3 == 3'b000 || funct3 == 3'b101)));
            7'h0f: legal_encoding = (funct3 == 3'b000); // FENCE, without caches
            7'h73: begin
                if (funct3 == 3'b000)
                    legal_encoding = (instruction == 32'h00000073 || // ECALL
                                      instruction == 32'h00100073 || // EBREAK
                                      instruction == 32'h30200073 || // MRET
                                      instruction == 32'h10500073);  // WFI may act as NOP
                else
                    legal_encoding = (funct3 != 3'b100); // Zicsr instruction encodings
            end
            default: legal_encoding = 1'b0;
        endcase

        misaligned_data = ((funct3 == 3'b001 || funct3 == 3'b101) && data_address[0]) ||
                          (funct3 == 3'b010 && (data_address[1:0] != 2'b00));
        trap = 1'b0;
        cause = 5'd0;
        value = 32'd0;
        if (valid) begin
            if (pc[1:0] != 2'b00) begin
                trap = 1'b1; cause = 5'd0; value = pc;
            end else if (!legal_encoding) begin
                trap = 1'b1; cause = 5'd2;
                // mtval=0 is permitted for illegal instructions in this environment.
            end else if (instruction == 32'h00100073) begin
                trap = 1'b1; cause = 5'd3; value = pc;
            end else if (instruction == 32'h00000073) begin
                trap = 1'b1; cause = 5'd11;
            end else if (control_taken && control_target[1:0] != 2'b00) begin
                trap = 1'b1; cause = 5'd0; value = control_target;
            end else if (opcode == 7'h03 && misaligned_data) begin
                trap = 1'b1; cause = 5'd4; value = data_address;
            end else if (opcode == 7'h23 && misaligned_data) begin
                trap = 1'b1; cause = 5'd6; value = data_address;
            end
        end
    end
endmodule
