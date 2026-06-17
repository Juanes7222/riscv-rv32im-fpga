// Minimal Machine-mode CSR file for trap handling (ADR 027 + ADR 033).
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
// Supports CSR read/write instructions and trap entry/exit (ECALL/MRET).
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
    input  logic [31:0] trap_pc4,     // pc+4 to save in mepc

    // Trap exit (MRET)
    input  logic        mret_exec,    // MRET decoded

    // PC redirect targets
    output logic [31:0] trap_target,  // mtvec (forced MODE=direct) for trap entry
    output logic [31:0] mepc_value    // mepc for MRET return
);

    // ── CSR registers ──────────────────────────────────────────────
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

    // MSTATUS field aliases
    logic [1:0]  mpp;
    assign mpp = mstatus[12:11];

    // Derive trap cause from current privilege level in MPP
    // ECALL cause: U-mode=8, S-mode=9, M-mode=11
    logic [4:0]  trap_cause;
    always_comb begin
        case (mpp)
            2'b00:   trap_cause = 5'd8;   // User-mode ECALL
            2'b01:   trap_cause = 5'd9;   // Supervisor-mode ECALL
            default: trap_cause = 5'd11;  // Machine-mode ECALL
        endcase
    end

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

    // ── Sequential CSR updates (writeback / trap entry / MRET) ─────
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            mstatus    <= 32'h00001800;   // MPP = 2'b11 (Machine) per RISC-V spec
            misa       <= MISA_RESET;
            mtvec      <= 32'h00000000;
            mcounteren <= 32'h00000000;
            mscratch   <= 32'h00000000;
            mepc       <= 32'h00000000;
            mcause     <= 32'h00000000;
            mtval      <= 32'h00000000;
            mvendorid  <= 32'h00000000;
            marchid    <= 32'h00000000;
            mimpid     <= 32'h00000000;
            mhartid    <= 32'h00000000;
        end else begin
            // Trap entry: capture mepc and mcause
            if (trap_entry) begin
                mepc   <= trap_pc4;
                mcause <= {1'b0, 26'b0, trap_cause};  // Bit 31 = 0 for exceptions
            end

            // MRET: restore MPP to user mode (RISC-V spec)
            if (mret_exec) begin
                mstatus[12:11] <= 2'b00;   // MPP ← User mode
            end

            // CSR instruction write
            if (csr_wr) begin
                case (csr_addr)
                    12'h300: mstatus    <= wdata_masked;
                    12'h305: mtvec      <= wdata_masked;
                    12'h306: mcounteren <= wdata_masked;
                    12'h340: mscratch   <= wdata_masked;
                    12'h341: mepc       <= wdata_masked;
                    12'h342: mcause     <= wdata_masked;
                    12'h343: mtval      <= wdata_masked;
                    // 0x301 misa, 0xF11 mvendorid, 0xF12 marchid,
                    // 0xF13 mimpid, 0xF14 mhartid are read-only.
                    default: ;
                endcase
            end
        end
    end

    // ── Combinational read ─────────────────────────────────────────
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

    // ── Trap target / MRET return address ──────────────────────────
    // mtvec MODE[1:0] forced to 00 (direct) — ADR 006.
    // trap_target and mepc_value are output ports, assigned directly.
    assign trap_target = {mtvec[31:2], 2'b00};
    assign mepc_value  = mepc;

endmodule
