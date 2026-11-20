// Minimal Machine-mode CSR file for trap handling (ADR 030 + ADR 033).
// Implements the CSRs required by the riscv-tests rv32mi suite:
//   - mstatus (0x300), mtvec (0x305), mscratch (0x340), mepc (0x341),
//     mcause (0x342), mtval (0x343): the standard trap-related CSRs.
//   - misa (0x301), mhartid (0xF14): read-only CSRs checked by mcsr.S.
//   - mvendorid (0xF11), marchid (0xF12), mimpid (0xF13): read-only
//     CSRs that the tests just read without checking the value.
//   - mcounteren (0x306): read-write CSR that the s-mode test writes to.
// cycle (0xC00), instret (0xC02), and the time*/hpmcounter* CSRs
// (Zicntr) are NOT implemented here; they are exposed via perf_counter
// (ADR 024) only at the dut.* hierarchy level for cocotb observability.
//
// Supports the documented CSR subset and explicit synchronous exception metadata.
// M-only: unsupported lower privilege modes are not advertised through MPP.
module csr_file (
    input  logic        clk,
    input  logic        rst_n,

    // CSR instruction interface
    input  logic [11:0] csr_addr,     // CSR address from instr[31:20]
    input  logic [31:0] csr_wdata,    // Write data (rs1_data or zimm)
    input  logic        csr_wr,       // Write enable from CSR instruction
    input  logic [1:0]  csr_op,       // 00=CSRRW, 01=CSRRS, 10=CSRRC, 11=unused
    output logic [31:0] csr_rdata,    // Read data to rd mux

    // Trap entry (ECALL)
    input  logic        trap_entry,   // ECALL decoded
    input  logic [31:0] trap_pc,      // PC of the trapping instruction, saved into mepc

    input  logic [4:0]  trap_cause,
    input  logic [31:0] trap_value,

    // Trap exit (MRET)
    input  logic        mret_exec,    // MRET decoded

    // PC redirect targets
    output logic [31:0] trap_target,  // mtvec (forced MODE=direct) for trap entry
    output logic [31:0] mepc_value    // mepc for MRET return
);

    // CSR registers
    logic [31:0] mstatus;
    logic [31:0] misa;          // (0x301) RO. Encodes I+M, XLEN=32
    logic [31:0] mtvec;
    logic [31:0] mscratch;      // (0x340) RW
    logic [31:0] mepc;
    logic [31:0] mcause;
    logic [31:0] mtval;         // (0x343) RW. Set on trap; not used by any
                                // implemented trap, but the csr.S test
                                // reads it after a synchronous exception.
    logic [31:0] mcounteren;    // (0x306) RW. m-mode access to cycle/instret.
    logic [31:0] mvendorid;     // (0xF11) RO. 0 = not implemented
    logic [31:0] marchid;       // (0xF12) RO. 0 = not implemented
    logic [31:0] mimpid;        // (0xF13) RO. 0 = not implemented
    logic [31:0] mhartid;       // (0xF14) RO. 0 = single-core

    // misa reset value: I+M, XLEN=32.
    // Encoding per the RISC-V Unprivileged ISA Spec §3.1.5:
    //   bits 31:30 = XLEN (01 = 32-bit)
    //   bit 12    = M extension
    //   bit 8     = I extension
    localparam logic [31:0] MISA_RESET = 32'h4000_1100;

    // Only M-mode is implemented. MPP is WARL and remains M (misa.U/S=0).
    // The exception unit supplies the cause independently of MPP.

    // ── Write data computation (handles CSRRS/CSRRC bitmask ops) ──
    logic [31:0] old_csr_val;
    logic [31:0] wdata_masked;

    // Select old CSR value by address
    always_comb begin
        case (csr_addr)
            12'h300: old_csr_val = mstatus;
            12'h301: old_csr_val = misa;
            12'h305: old_csr_val = mtvec;
            12'h306: old_csr_val = mcounteren;
            12'h340: old_csr_val = mscratch;
            12'h341: old_csr_val = mepc;
            12'h342: old_csr_val = mcause;
            12'h343: old_csr_val = mtval;
            12'hF11: old_csr_val = mvendorid;
            12'hF12: old_csr_val = marchid;
            12'hF13: old_csr_val = mimpid;
            12'hF14: old_csr_val = mhartid;
            default: old_csr_val = 32'b0;
        endcase
    end

    always_comb begin
        case (csr_op)
            2'b00:   wdata_masked = csr_wdata;              // CSRRW: direct write
            2'b01:   wdata_masked = old_csr_val | csr_wdata; // CSRRS: set bits
            2'b10:   wdata_masked = old_csr_val & ~csr_wdata;// CSRRC: clear bits
            default: wdata_masked = csr_wdata;              // Should not occur
        endcase
    end

    // Precise exception entry takes priority over ordinary CSR writes.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            mstatus <= 32'h00001800;
            misa <= MISA_RESET;
            mtvec <= '0;
            mcounteren <= '0;
            mscratch <= '0;
            mepc <= '0;
            mcause <= '0;
            mtval <= '0;
            mvendorid <= '0;
            marchid <= '0;
            mimpid <= '0;
            mhartid <= '0;
        end else if (trap_entry) begin
            mepc <= {trap_pc[31:2], 2'b00};
            mcause <= {27'd0, trap_cause};
            mtval <= trap_value;
            mstatus[7] <= mstatus[3]; // MPIE <- MIE
            mstatus[3] <= 1'b0;
            mstatus[12:11] <= 2'b11;
        end else if (mret_exec) begin
            mstatus[3] <= mstatus[7];
            mstatus[7] <= 1'b1;
            mstatus[12:11] <= 2'b11;
        end else if (csr_wr) begin
            case (csr_addr)
                12'h300: mstatus <= (wdata_masked & 32'h00000088) | 32'h00001800;
                12'h305: mtvec <= {wdata_masked[31:2], 2'b00};
                12'h306: mcounteren <= wdata_masked;
                12'h340: mscratch <= wdata_masked;
                12'h341: mepc <= {wdata_masked[31:2], 2'b00};
                12'h342: mcause <= wdata_masked;
                12'h343: mtval <= wdata_masked;
                default: ;
            endcase
        end
    end

    // Combinational read
    always_comb begin
        case (csr_addr)
            12'h300: csr_rdata = mstatus;
            12'h301: csr_rdata = misa;
            12'h305: csr_rdata = mtvec;
            12'h306: csr_rdata = mcounteren;
            12'h340: csr_rdata = mscratch;
            12'h341: csr_rdata = mepc;
            12'h342: csr_rdata = mcause;
            12'h343: csr_rdata = mtval;
            12'hF11: csr_rdata = mvendorid;
            12'hF12: csr_rdata = marchid;
            12'hF13: csr_rdata = mimpid;
            12'hF14: csr_rdata = mhartid;
            default: csr_rdata = 32'b0;
        endcase
    end

    // Trap target / MRET return address
    // mtvec MODE[1:0] forced to 00 (direct) - ADR 006.
    // trap_target and mepc_value are output ports, assigned directly.
    assign trap_target = {mtvec[31:2], 2'b00};
    assign mepc_value  = mepc;

endmodule
