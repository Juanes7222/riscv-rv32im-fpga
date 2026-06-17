"""
RV32IM instruction decoder: 32-bit raw encoding → Instruction named tuple.

The Instruction dataclass carries only the fields needed by the
executor; raw fields (opcode, rd, rs1, rs2, funct3, funct7) are
extracted and consumed once, and the signed immediate is precomputed.

Decoding is purely functional: decode(raw) returns an Instruction
object with no side effects. Errors result in an Instruction with
name="UNKNOWN" rather than an exception, so the model can keep
running on illegal encodings (the DUT's behavior on illegal
encodings is implementation-defined; for now we treat them as NOPs).
"""
from dataclasses import dataclass


@dataclass
class Instruction:
    raw: int
    name: str
    rd: int = 0
    funct3: int = 0
    rs1: int = 0
    rs2: int = 0
    funct7: int = 0
    imm: int = 0
    csr_addr: int = 0


def _sign_extend(value, bits):
    """Sign-extend a `bits`-wide unsigned value to a Python int."""
    sign_bit = 1 << (bits - 1)
    return (value & (sign_bit - 1)) - (value & sign_bit)


# ──────────────────────────────────────────────────────────────────────
# Lookup tables
# ──────────────────────────────────────────────────────────────────────

# (funct3, funct7) → name for OP_REG (R-type)
_R_TYPE = {
    (0b000, 0b0000000): "ADD",
    (0b000, 0b0100000): "SUB",
    (0b000, 0b0000001): "MUL",
    (0b001, 0b0000000): "SLL",
    (0b001, 0b0000001): "MULH",
    (0b010, 0b0000000): "SLT",
    (0b010, 0b0000001): "MULHSU",
    (0b011, 0b0000000): "SLTU",
    (0b011, 0b0000001): "MULHU",
    (0b100, 0b0000000): "XOR",
    (0b100, 0b0000001): "DIV",
    (0b101, 0b0000000): "SRL",
    (0b101, 0b0100000): "SRA",
    (0b101, 0b0000001): "DIVU",
    (0b110, 0b0000000): "OR",
    (0b110, 0b0000001): "REM",
    (0b111, 0b0000000): "AND",
    (0b111, 0b0000001): "REMU",
}

# funct3 → name for OP_IMM (I-type ALU)
_I_TYPE_ALU = {
    0b000: "ADDI",
    0b010: "SLTI",
    0b011: "SLTIU",
    0b100: "XORI",
    0b110: "ORI",
    0b111: "ANDI",
}

# funct3 → name for OP_LOAD
_LOADS = {
    0b000: "LB",
    0b001: "LH",
    0b010: "LW",
    0b100: "LBU",
    0b101: "LHU",
}

# funct3 → name for OP_STORE
_STORES = {
    0b000: "SB",
    0b001: "SH",
    0b010: "SW",
}

# funct3 → name for OP_BRANCH
_BRANCHES = {
    0b000: "BEQ",
    0b001: "BNE",
    0b100: "BLT",
    0b101: "BGE",
    0b110: "BLTU",
    0b111: "BGEU",
}


# ──────────────────────────────────────────────────────────────────────
# Decoder
# ──────────────────────────────────────────────────────────────────────

def decode(raw):
    """Decode a 32-bit instruction word into an Instruction."""
    raw &= 0xFFFFFFFF
    opcode     = raw & 0x7F
    rd         = (raw >> 7)  & 0x1F
    funct3     = (raw >> 12) & 0x7
    rs1        = (raw >> 15) & 0x1F
    rs2        = (raw >> 20) & 0x1F
    funct7     = (raw >> 25) & 0x7F
    instr_31_20 = (raw >> 20) & 0xFFF  # for CSR addr and ECALL funct12

    if opcode == 0b0110011:  # OP_REG
        name = _R_TYPE.get((funct3, funct7))
        return Instruction(raw, name or "UNKNOWN", rd, funct3, rs1, rs2, funct7)

    if opcode == 0b0010011:  # OP_IMM
        imm = _sign_extend((raw >> 20) & 0xFFF, 12)
        if funct3 in _I_TYPE_ALU:
            return Instruction(raw, _I_TYPE_ALU[funct3], rd, funct3, rs1, imm=imm)
        if funct3 == 0b001:  # SLLI
            return Instruction(raw, "SLLI", rd, funct3, rs1, imm=(raw >> 20) & 0x1F)
        if funct3 == 0b101:
            if funct7 == 0b0000000:
                return Instruction(raw, "SRLI", rd, funct3, rs1, imm=(raw >> 20) & 0x1F)
            if funct7 == 0b0100000:
                return Instruction(raw, "SRAI", rd, funct3, rs1, imm=(raw >> 20) & 0x1F)
        return Instruction(raw, "UNKNOWN")

    if opcode == 0b0000011:  # OP_LOAD
        imm = _sign_extend((raw >> 20) & 0xFFF, 12)
        name = _LOADS.get(funct3)
        return Instruction(raw, name or "UNKNOWN", rd, funct3, rs1, imm=imm)

    if opcode == 0b0100011:  # OP_STORE
        imm_hi = (raw >> 25) & 0x7F
        imm_lo = (raw >> 7)  & 0x1F
        imm = _sign_extend((imm_hi << 5) | imm_lo, 12)
        name = _STORES.get(funct3)
        return Instruction(raw, name or "UNKNOWN",
                           rd=0, funct3=funct3, rs1=rs1, rs2=rs2, imm=imm)

    if opcode == 0b1100011:  # OP_BRANCH
        imm12   = (raw >> 31) & 0x1
        imm10_5 = (raw >> 25) & 0x3F
        imm4_1  = (raw >>  8) & 0xF
        imm11   = (raw >>  7) & 0x1
        imm = _sign_extend(
            (imm12 << 12) | (imm11 << 11) | (imm10_5 << 5) | (imm4_1 << 1), 13)
        name = _BRANCHES.get(funct3)
        return Instruction(raw, name or "UNKNOWN",
                           rd=0, funct3=funct3, rs1=rs1, rs2=rs2, imm=imm)

    if opcode == 0b0110111:  # OP_LUI
        return Instruction(raw, "LUI", rd,
                           imm=((raw >> 12) & 0xFFFFF) << 12)

    if opcode == 0b0010111:  # OP_AUIPC
        return Instruction(raw, "AUIPC", rd,
                           imm=((raw >> 12) & 0xFFFFF) << 12)

    if opcode == 0b1101111:  # OP_JAL
        imm20    = (raw >> 31) & 0x1
        imm10_1  = (raw >> 21) & 0x3FF
        imm11    = (raw >> 20) & 0x1
        imm19_12 = (raw >> 12) & 0xFF
        imm = _sign_extend(
            (imm20 << 20) | (imm19_12 << 12) | (imm11 << 11) | (imm10_1 << 1),
            21)
        return Instruction(raw, "JAL", rd, imm=imm)

    if opcode == 0b1100111:  # OP_JALR
        imm = _sign_extend((raw >> 20) & 0xFFF, 12)
        return Instruction(raw, "JALR", rd, funct3, rs1, imm=imm)

    if opcode == 0b0001111:  # FENCE / FENCE.I
        if funct3 == 0b001:
            return Instruction(raw, "FENCE_I")
        return Instruction(raw, "FENCE")

    if opcode == 0b1110011:  # OP_SYSTEM
        if funct3 == 0b000:
            if instr_31_20 == 0x000:
                return Instruction(raw, "ECALL")
            if instr_31_20 == 0x001:
                return Instruction(raw, "EBREAK")
            if instr_31_20 == 0x302:
                return Instruction(raw, "MRET")
            return Instruction(raw, "UNKNOWN")
        # CSR instructions
        csr_addr = instr_31_20
        csr_imm  = (funct3 >> 2) & 1
        csr_op   = funct3 & 0x3
        if csr_imm:
            zimm = (raw >> 15) & 0x1F
            names = {0b01: "CSRRWI", 0b10: "CSRRSI", 0b11: "CSRRCI"}
            return Instruction(raw, names.get(csr_op, "UNKNOWN"),
                               rd, funct3, rs1, imm=zimm, csr_addr=csr_addr)
        names = {0b01: "CSRRW", 0b10: "CSRRS", 0b11: "CSRRC"}
        return Instruction(raw, names.get(csr_op, "UNKNOWN"),
                           rd, funct3, rs1, imm=0, csr_addr=csr_addr)

    return Instruction(raw, "UNKNOWN")
