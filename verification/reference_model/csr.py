"""
Machine-mode CSR file. Mirrors the DUT's csr_file.sv (ADR 027 + ADR 033).

The reset values match the DUT exactly. The mtvec low-2-bit MODE
field is forced to 0 (direct mode) per ADR 006, so trap_target is
mtvec with the low 2 bits cleared.

Note: the DUT stores mepc = pc + 4 of the trapping instruction
(see csr_file.sv: `mepc <= trap_pc4`). This is the address AFTER
the trap instruction, not the address of the trapping instruction.
The RISC-V spec says mepc should be the trapping instruction's
address, but the DUT (and the rv32mi tests written for it) use
pc + 4. This model matches the DUT's behavior.
"""


class CSRFile:
    """Machine-mode CSR file. Addresses and widths match the DUT."""

    # Reset values from csr_file.sv
    MSTATUS_RESET = 0x00001800  # MPP = 2'b11 (machine mode)
    MISA_RESET    = 0x40001100  # I+M, XLEN=32
    MTVEC_RESET   = 0x00000000

    # CSR operation codes (match the DUT's csr_op encoding)
    OP_CSRRW = 0
    OP_CSRRS = 1
    OP_CSRRC = 2

    # Read-only CSR addresses
    _RO_ADDRS = frozenset({0x301, 0xF11, 0xF12, 0xF13, 0xF14})

    def __init__(self):
        self.reset()

    def reset(self):
        self.mstatus    = self.MSTATUS_RESET
        self.misa       = self.MISA_RESET
        self.mtvec      = self.MTVEC_RESET
        self.mscratch   = 0
        self.mepc       = 0
        self.mcause     = 0
        self.mtval      = 0
        self.mcounteren = 0
        self.mvendorid  = 0
        self.marchid    = 0
        self.mimpid     = 0
        self.mhartid    = 0

    # ── Read ──

    def read(self, addr):
        if addr == 0x300: return self.mstatus
        if addr == 0x301: return self.misa
        if addr == 0x305: return self.mtvec
        if addr == 0x306: return self.mcounteren
        if addr == 0x340: return self.mscratch
        if addr == 0x341: return self.mepc
        if addr == 0x342: return self.mcause
        if addr == 0x343: return self.mtval
        if addr == 0xF11: return self.mvendorid
        if addr == 0xF12: return self.marchid
        if addr == 0xF13: return self.mimpid
        if addr == 0xF14: return self.mhartid
        return 0  # unknown CSR returns 0 (matches DUT default)

    # ── Write ──

    def write(self, addr, wdata, op):
        """Apply a CSR instruction write. op is one of OP_CSRRW/CSRRS/CSRRC.

        Per the RISC-V spec:
          - CSRRW: always write (unless CSR is RO).
          - CSRRS/CSRRC: only write if rs1 != 0 (caller is responsible for
            this check; this method writes unconditionally)."""
        if addr in self._RO_ADDRS:
            return
        old = self.read(addr)
        if op == self.OP_CSRRW:
            new = wdata & 0xFFFFFFFF
        elif op == self.OP_CSRRS:
            new = (old | (wdata & 0xFFFFFFFF)) & 0xFFFFFFFF
        elif op == self.OP_CSRRC:
            new = (old & ~(wdata & 0xFFFFFFFF)) & 0xFFFFFFFF
        else:
            return
        self._store(addr, new)

    def _store(self, addr, value):
        if   addr == 0x300: self.mstatus    = value
        elif addr == 0x305: self.mtvec      = value
        elif addr == 0x306: self.mcounteren = value
        elif addr == 0x340: self.mscratch   = value
        elif addr == 0x341: self.mepc       = value
        elif addr == 0x342: self.mcause     = value
        elif addr == 0x343: self.mtval      = value
        # RO CSRs (misa, mvendorid, marchid, mimpid, mhartid) are silently ignored

    # ── Trap handling ──

    def trap_enter(self, trap_pc4, cause):
        """Trap entry: save PC+4 to mepc, set mcause.

        The DUT saves trap_pc4 (which is the trapping instruction's
        pc + 4) to mepc. This is non-standard (the RISC-V spec
        wants mepc = pc of trapping instruction) but matches what
        the DUT and the rv32mi tests expect."""
        self.mepc   = trap_pc4 & 0xFFFFFFFF
        self.mcause = cause & 0xFFFFFFFF
        self.mtval  = 0

    def trap_exit(self):
        """MRET: return to mepc, transition MPP from M-mode to U-mode.

        Returns the new PC value."""
        target = self.mepc
        # MPP ← 0 (U-mode) per RISC-V spec.
        self.mstatus = (self.mstatus & ~(0x3 << 11)) | (0 << 11)
        return target

    @property
    def trap_target(self):
        """Address to jump to on a trap (mtvec with low 2 bits forced to 0)."""
        return self.mtvec & ~0x3

    @property
    def mpp(self):
        """Current privilege level (MPP field of mstatus, bits 12:11)."""
        return (self.mstatus >> 11) & 0x3
