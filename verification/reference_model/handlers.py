"""
RV32IM instruction handlers for the reference model.

Each handler is a function (cpu, instr) that updates the CPU's state
(regs, mem, csr, pc) per the ISA spec. The handler is responsible
for setting cpu.pc; if it does not, cpu.step() advances PC by 4
automatically. The handlers dispatch table is HANDLERS.

Sign-extension: most arithmetic uses 32-bit modular arithmetic, with
_sign_extend() used when signed comparison is needed (SLT, BLT, BGE,
SRA, JALR with negative offsets, etc.). The result is always masked
to 32 bits via & 0xFFFFFFFF.
"""


def _write_rd(cpu, instr, value):
    if instr.rd != 0:
        cpu.regs[instr.rd] = value & 0xFFFFFFFF


def _sign_extend(value, bits):
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)


# ── R-type ALU ──────────────────────────────────────────────────────

def h_ADD(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] + cpu.regs[instr.rs2])

def h_SUB(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] - cpu.regs[instr.rs2])

def h_SLL(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] << (cpu.regs[instr.rs2] & 0x1F))

def h_SLT(cpu, instr):
    a = _sign_extend(cpu.regs[instr.rs1], 32)
    b = _sign_extend(cpu.regs[instr.rs2], 32)
    _write_rd(cpu, instr, 1 if a < b else 0)

def h_SLTU(cpu, instr):
    _write_rd(cpu, instr, 1 if cpu.regs[instr.rs1] < cpu.regs[instr.rs2] else 0)

def h_XOR(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] ^ cpu.regs[instr.rs2])

def h_SRL(cpu, instr):
    _write_rd(cpu, instr, (cpu.regs[instr.rs1] & 0xFFFFFFFF) >> (cpu.regs[instr.rs2] & 0x1F))

def h_SRA(cpu, instr):
    a = _sign_extend(cpu.regs[instr.rs1], 32)
    _write_rd(cpu, instr, (a >> (cpu.regs[instr.rs2] & 0x1F)) & 0xFFFFFFFF)

def h_OR(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] | cpu.regs[instr.rs2])

def h_AND(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] & cpu.regs[instr.rs2])


# ── I-type ALU ──────────────────────────────────────────────────────

def h_ADDI(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] + instr.imm)

def h_SLTI(cpu, instr):
    a = _sign_extend(cpu.regs[instr.rs1], 32)
    b = _sign_extend(instr.imm, 32)
    _write_rd(cpu, instr, 1 if a < b else 0)

def h_SLTIU(cpu, instr):
    # imm is sign-extended in the decoder; we want the unsigned value here,
    # which is the lower 32 bits of the sign-extended imm.
    b = instr.imm & 0xFFFFFFFF
    _write_rd(cpu, instr, 1 if cpu.regs[instr.rs1] < b else 0)

def h_XORI(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] ^ (instr.imm & 0xFFFFFFFF))

def h_ORI(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] | (instr.imm & 0xFFFFFFFF))

def h_ANDI(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] & (instr.imm & 0xFFFFFFFF))

def h_SLLI(cpu, instr):
    _write_rd(cpu, instr, cpu.regs[instr.rs1] << (instr.imm & 0x1F))

def h_SRLI(cpu, instr):
    _write_rd(cpu, instr, (cpu.regs[instr.rs1] & 0xFFFFFFFF) >> (instr.imm & 0x1F))

def h_SRAI(cpu, instr):
    a = _sign_extend(cpu.regs[instr.rs1], 32)
    _write_rd(cpu, instr, (a >> (instr.imm & 0x1F)) & 0xFFFFFFFF)


# ── Loads ───────────────────────────────────────────────────────────

def h_LB(cpu, instr):
    addr = (cpu.regs[instr.rs1] + instr.imm) & 0xFFFFFFFF
    val = cpu.load_byte(addr)
    _write_rd(cpu, instr, _sign_extend(val, 8))

def h_LH(cpu, instr):
    addr = (cpu.regs[instr.rs1] + instr.imm) & 0xFFFFFFFF
    val = cpu.load_half(addr)
    _write_rd(cpu, instr, _sign_extend(val, 16))

def h_LW(cpu, instr):
    addr = (cpu.regs[instr.rs1] + instr.imm) & 0xFFFFFFFF
    _write_rd(cpu, instr, cpu.load_word(addr))

def h_LBU(cpu, instr):
    addr = (cpu.regs[instr.rs1] + instr.imm) & 0xFFFFFFFF
    _write_rd(cpu, instr, cpu.load_byte(addr))

def h_LHU(cpu, instr):
    addr = (cpu.regs[instr.rs1] + instr.imm) & 0xFFFFFFFF
    _write_rd(cpu, instr, cpu.load_half(addr))


# ── Stores ──────────────────────────────────────────────────────────

def h_SB(cpu, instr):
    addr = (cpu.regs[instr.rs1] + instr.imm) & 0xFFFFFFFF
    cpu.store_byte(addr, cpu.regs[instr.rs2] & 0xFF)

def h_SH(cpu, instr):
    addr = (cpu.regs[instr.rs1] + instr.imm) & 0xFFFFFFFF
    cpu.store_half(addr, cpu.regs[instr.rs2] & 0xFFFF)

def h_SW(cpu, instr):
    addr = (cpu.regs[instr.rs1] + instr.imm) & 0xFFFFFFFF
    cpu.store_word(addr, cpu.regs[instr.rs2] & 0xFFFFFFFF)


# ── Branches ────────────────────────────────────────────────────────

def _branch(cpu, instr, taken):
    if taken:
        cpu.pc = (cpu.pc + instr.imm) & 0xFFFFFFFF
    else:
        cpu.pc = (cpu.pc + 4) & 0xFFFFFFFF

def h_BEQ(cpu, instr):
    _branch(cpu, instr, cpu.regs[instr.rs1] == cpu.regs[instr.rs2])

def h_BNE(cpu, instr):
    _branch(cpu, instr, cpu.regs[instr.rs1] != cpu.regs[instr.rs2])

def h_BLT(cpu, instr):
    a = _sign_extend(cpu.regs[instr.rs1], 32)
    b = _sign_extend(cpu.regs[instr.rs2], 32)
    _branch(cpu, instr, a < b)

def h_BGE(cpu, instr):
    a = _sign_extend(cpu.regs[instr.rs1], 32)
    b = _sign_extend(cpu.regs[instr.rs2], 32)
    _branch(cpu, instr, a >= b)

def h_BLTU(cpu, instr):
    _branch(cpu, instr, cpu.regs[instr.rs1] < cpu.regs[instr.rs2])

def h_BGEU(cpu, instr):
    _branch(cpu, instr, cpu.regs[instr.rs1] >= cpu.regs[instr.rs2])


# ── U-type ──────────────────────────────────────────────────────────

def h_LUI(cpu, instr):
    _write_rd(cpu, instr, instr.imm & 0xFFFFFFFF)

def h_AUIPC(cpu, instr):
    _write_rd(cpu, instr, (cpu.pc + instr.imm) & 0xFFFFFFFF)


# ── Jumps ───────────────────────────────────────────────────────────

def h_JAL(cpu, instr):
    target = (cpu.pc + instr.imm) & 0xFFFFFFFF
    _write_rd(cpu, instr, (cpu.pc + 4) & 0xFFFFFFFF)
    cpu.pc = target

def h_JALR(cpu, instr):
    target = ((cpu.regs[instr.rs1] + instr.imm) & 0xFFFFFFFF) & ~1
    _write_rd(cpu, instr, (cpu.pc + 4) & 0xFFFFFFFF)
    cpu.pc = target


# ── System / traps ──────────────────────────────────────────────────

def h_ECALL(cpu, instr):
    # Cause depends on current privilege. The DUT sets mpp=11 (M-mode)
    # after reset, so cause=11. The model matches.
    cpu.take_trap(cause=11 if cpu.csrs.mpp == 0b11 else 8)

def h_EBREAK(cpu, instr):
    cpu.take_trap(cause=3)  # breakpoint

def h_MRET(cpu, instr):
    cpu.pc = cpu.csrs.trap_exit()


# ── CSR instructions ────────────────────────────────────────────────

def _do_csr(cpu, instr, op):
    """Common CSR instruction logic.

    For CSRRW (op=CSRFile.OP_CSRRW): always write to CSR.
    For CSRRS/CSRRC (op=CSRRS/CSRRC): only write if rs1 != 0 (or zimm != 0).
    Always write the OLD CSR value to rd (unless rd == 0, in which case skip)."""
    addr = instr.csr_addr
    old = cpu.csrs.read(addr)
    is_imm = instr.name.endswith("I")
    rs1_val = (instr.imm & 0x1F) if is_imm else cpu.regs[instr.rs1]

    if op == cpu.csrs.OP_CSRRW:
        cpu.csrs.write(addr, rs1_val, op)
    else:  # CSRRS or CSRRC
        if rs1_val != 0:
            cpu.csrs.write(addr, rs1_val, op)
        # else: no write per spec

    if instr.rd != 0:
        cpu.regs[instr.rd] = old

def h_CSRRW(cpu, instr):  _do_csr(cpu, instr, cpu.csrs.OP_CSRRW)
def h_CSRRS(cpu, instr):  _do_csr(cpu, instr, cpu.csrs.OP_CSRRS)
def h_CSRRC(cpu, instr):  _do_csr(cpu, instr, cpu.csrs.OP_CSRRC)
def h_CSRRWI(cpu, instr): _do_csr(cpu, instr, cpu.csrs.OP_CSRRW)
def h_CSRRSI(cpu, instr): _do_csr(cpu, instr, cpu.csrs.OP_CSRRS)
def h_CSRRCI(cpu, instr): _do_csr(cpu, instr, cpu.csrs.OP_CSRRC)


# ── Fence (NOP) ─────────────────────────────────────────────────────

def h_FENCE(cpu, instr):   pass
def h_FENCE_I(cpu, instr): pass


# ── M Extension ─────────────────────────────────────────────────────
# All M-extension operations are computed in Python's big-int arithmetic
# and masked to 32 bits. Division uses int(a/b) which truncates toward
# zero (matches C semantics and the RISC-V spec).
# Edge cases per the RISC-V spec:
#   - DIV/REM by 0: DIV returns -1 (0xFFFFFFFF), REM returns the dividend.
#   - DIV/REM with dividend=INT_MIN, divisor=-1: DIV returns INT_MIN
#     (overflow), REM returns 0.

def h_MUL(cpu, instr):
    a = _sign_extend(cpu.regs[instr.rs1], 32)
    b = _sign_extend(cpu.regs[instr.rs2], 32)
    _write_rd(cpu, instr, (a * b) & 0xFFFFFFFF)

def h_MULH(cpu, instr):
    a = _sign_extend(cpu.regs[instr.rs1], 32)
    b = _sign_extend(cpu.regs[instr.rs2], 32)
    _write_rd(cpu, instr, ((a * b) >> 32) & 0xFFFFFFFF)

def h_MULHSU(cpu, instr):
    a = _sign_extend(cpu.regs[instr.rs1], 32)
    b = cpu.regs[instr.rs2]
    _write_rd(cpu, instr, ((a * b) >> 32) & 0xFFFFFFFF)

def h_MULHU(cpu, instr):
    a = cpu.regs[instr.rs1]
    b = cpu.regs[instr.rs2]
    _write_rd(cpu, instr, ((a * b) >> 32) & 0xFFFFFFFF)

def _div_rem_common(cpu, instr, signed):
    a = cpu.regs[instr.rs1]
    b = cpu.regs[instr.rs2]
    if b == 0:
        return a, 0xFFFFFFFF  # (rem, div) - by-zero: div=-1, rem=dividend
    if signed and a == 0x80000000 and b == 0xFFFFFFFF:
        return 0, 0x80000000  # overflow: rem=0, div=INT_MIN
    sa = _sign_extend(a, 32)
    sb = _sign_extend(b, 32) if signed else b
    if signed:
        q = int(sa / sb)
        r = sa - q * sb
    else:
        q = (a // b) & 0xFFFFFFFF
        r = a - q * b
    return r & 0xFFFFFFFF, q & 0xFFFFFFFF

def h_DIV(cpu, instr):
    _, q = _div_rem_common(cpu, instr, signed=True)
    _write_rd(cpu, instr, q)

def h_DIVU(cpu, instr):
    _, q = _div_rem_common(cpu, instr, signed=False)
    _write_rd(cpu, instr, q)

def h_REM(cpu, instr):
    r, _ = _div_rem_common(cpu, instr, signed=True)
    _write_rd(cpu, instr, r)

def h_REMU(cpu, instr):
    r, _ = _div_rem_common(cpu, instr, signed=False)
    _write_rd(cpu, instr, r)


# ── Dispatch table ──────────────────────────────────────────────────

HANDLERS = {
    # R-type ALU
    "ADD":  h_ADD,  "SUB":  h_SUB,  "SLL":  h_SLL,  "SLT":  h_SLT,
    "SLTU": h_SLTU, "XOR":  h_XOR,  "SRL":  h_SRL,  "SRA":  h_SRA,
    "OR":   h_OR,   "AND":  h_AND,
    # I-type ALU
    "ADDI":  h_ADDI,  "SLTI":  h_SLTI,  "SLTIU": h_SLTIU,
    "XORI":  h_XORI,  "ORI":   h_ORI,   "ANDI":  h_ANDI,
    "SLLI":  h_SLLI,  "SRLI":  h_SRLI,  "SRAI":  h_SRAI,
    # Loads / stores
    "LB":  h_LB,  "LH":  h_LH,  "LW":  h_LW,  "LBU":  h_LBU,  "LHU":  h_LHU,
    "SB":  h_SB,  "SH":  h_SH,  "SW":  h_SW,
    # Branches
    "BEQ": h_BEQ, "BNE": h_BNE, "BLT": h_BLT, "BGE": h_BGE,
    "BLTU": h_BLTU, "BGEU": h_BGEU,
    # U-type
    "LUI":   h_LUI,  "AUIPC": h_AUIPC,
    # Jumps
    "JAL":  h_JAL,  "JALR":  h_JALR,
    # System
    "ECALL":  h_ECALL,  "EBREAK":  h_EBREAK,  "MRET":  h_MRET,
    # CSR
    "CSRRW":  h_CSRRW,  "CSRRS":  h_CSRRS,  "CSRRC":  h_CSRRC,
    "CSRRWI": h_CSRRWI, "CSRRSI": h_CSRRSI, "CSRRCI": h_CSRRCI,
    # Fence
    "FENCE": h_FENCE, "FENCE_I": h_FENCE_I,
    # M extension
    "MUL":   h_MUL,   "MULH":   h_MULH,   "MULHSU": h_MULHSU, "MULHU": h_MULHU,
    "DIV":   h_DIV,   "DIVU":   h_DIVU,   "REM":    h_REM,    "REMU":  h_REMU,
}
