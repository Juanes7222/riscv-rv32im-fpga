"""
RISC-V RV32IM instruction encoders.

Convenience functions for building 32-bit instruction encodings from
register/imm operands. Used by both the reference model self-tests
and cocotb tests that load instructions into the DUT's instruction
memory.

All functions return a 32-bit unsigned integer.
"""


def encode_r(funct7, rs2, rs1, funct3, rd):
    """R-type (OP_REG = 0b0110011). Used for R-type ALU and M extension."""
    return ((funct7 & 0x7F) << 25) | ((rs2 & 0x1F) << 20) \
         | ((rs1 & 0x1F) << 15) | ((funct3 & 0x7) << 12) \
         | ((rd  & 0x1F) <<  7) | 0b0110011


def encode_i(imm12, rs1, funct3, rd, opcode=0b0010011):
    """I-type (default OP_IMM = 0b0010011; also OP_LOAD = 0b0000011, OP_JALR = 0b1100111).

    The 12-bit immediate is stored as-is (no shifting). Sign extension
    happens at execution time inside the model / DUT."""
    imm12 &= 0xFFF
    return (imm12 << 20) | ((rs1 & 0x1F) << 15) | ((funct3 & 0x7) << 12) \
         | ((rd & 0x1F) << 7) | opcode


def encode_s(imm12, rs2, rs1, funct3):
    """S-type (OP_STORE = 0b0100011). The 12-bit immediate is split:
    imm[11:5] goes in bits 31:25, imm[4:0] goes in bits 11:7."""
    imm12 &= 0xFFF
    return (((imm12 >> 5) & 0x7F) << 25) | ((rs2 & 0x1F) << 20) \
         | ((rs1 & 0x1F) << 15) | ((funct3 & 0x7) << 12) \
         | ((imm12 & 0x1F) << 7) | 0b0100011


def encode_b(funct3, rs1, rs2, imm):
    """B-type (OP_BRANCH = 0b1100011). imm is a 13-bit signed byte offset
    (bit 0 is implicitly 0). Range: -4096 to +4094 in steps of 2.

    Bit layout: bit 31 = imm[12] (sign), bits 30:25 = imm[10:5],
    bit 7 = imm[11], bits 11:8 = imm[4:1]."""
    imm12   = (imm >> 12) & 0x1
    imm11   = (imm >> 11) & 0x1
    imm10_5 = (imm >> 5)  & 0x3F
    imm4_1  = (imm >> 1)  & 0xF
    return (imm12 << 31) | (imm10_5 << 25) | ((rs2 & 0x1F) << 20) \
         | ((rs1 & 0x1F) << 15) | ((funct3 & 0x7) << 12) \
         | (imm4_1 << 8) | (imm11 << 7) | 0b1100011


def encode_u(imm20, rd, opcode):
    """U-type (OP_LUI = 0b0110111 or OP_AUIPC = 0b0010111). imm20 occupies
    bits 31:12 of the encoding; the low 12 bits are zero in the result."""
    imm20 &= 0xFFFFF
    return (imm20 << 12) | ((rd & 0x1F) << 7) | opcode


def encode_j(imm, rd):
    """J-type (OP_JAL = 0b1101111). imm is a 21-bit signed byte offset
    (bit 0 is implicitly 0). Range: -1048576 to +1048574 in steps of 2.

    Bit layout: bit 31 = imm[20] (sign), bits 30:21 = imm[10:1],
    bit 20 = imm[11], bits 19:12 = imm[19:12]."""
    imm20    = (imm >> 20) & 0x1
    imm10_1  = (imm >> 1)  & 0x3FF
    imm11    = (imm >> 11) & 0x1
    imm19_12 = (imm >> 12) & 0xFF
    return (imm20 << 31) | (imm10_1 << 21) | (imm11 << 20) \
         | (imm19_12 << 12) | ((rd & 0x1F) << 7) | 0b1101111


def encode_csr(csr_addr, rs1, funct3, rd):
    """Encode a CSR instruction (OP_SYSTEM = 0b1110011, funct3 != 0).

    funct3: 001=CSRRW, 010=CSRRS, 011=CSRRC, 101=CSRRWI, 110=CSRRSI, 111=CSRRCI.
    For immediate forms (CSRRWI/CSRRSI/CSRRCI), pass the zimm as `rs1`."""
    return ((csr_addr & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) \
         | ((funct3 & 0x7) << 12) | ((rd & 0x1F) << 7) | 0b1110011
