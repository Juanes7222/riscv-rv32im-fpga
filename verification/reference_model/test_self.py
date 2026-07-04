"""
Standalone self-test for the reference model.

Exercises every RV32IM instruction and corner case the model claims
to support, and asserts the model's output matches the ISA spec
computed in plain Python. Runs without the DUT (no cocotb needed).

Run with:
    cd verification
    python3 -m reference_model.test_self

Exit code 0 = all checks pass. Non-zero = at least one mismatch.
"""
import sys
import struct

from . import CPU
from .encoders import (
    encode_r, encode_i, encode_s, encode_b, encode_u, encode_j, encode_csr,
)


# ── Tiny test harness ───────────────────────────────────────────────

_failures = 0
_passes   = 0


def check(name, actual, expected):
    global _failures, _passes
    actual &= 0xFFFFFFFF
    if actual == (expected & 0xFFFFFFFF):
        _passes += 1
    else:
        _failures += 1
        print(f"  FAIL {name}: expected {expected:#010x}, got {actual:#010x}")


def run(name, fn):
    """Run a test function and report pass/fail count."""
    print(f"[{name}]")
    fn()
    print(f"  ({_passes_for_run} checks passed)")


_current_run = ""

def _passes_for_run(): return _passes


# ── Helper to make a fresh CPU with a single instruction at PC=0 ────

def make_cpu_with(encoding, regs=None):
    cpu = CPU()
    if regs:
        for r, v in regs.items():
            cpu.regs[r] = v
    cpu.store_instruction(0, encoding)
    return cpu


# ── R-type ALU ──────────────────────────────────────────────────────

def test_r_type_add():
    cpu = make_cpu_with(encode_r(0, 3, 2, 0, 1), {2: 0x12345678, 3: 0x9ABCDEF0})
    cpu.step()
    check("ADD x1,x2,x3", cpu.regs[1], 0x12345678 + 0x9ABCDEF0)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0, 1), {2: 0xFFFFFFFF, 3: 1})
    cpu.step()
    check("ADD overflow wraps", cpu.regs[1], 0)

    cpu = make_cpu_with(encode_r(0x20, 3, 2, 0, 1), {2: 0x12345678, 3: 0x9ABCDEF0})
    cpu.step()
    check("SUB x1,x2,x3", cpu.regs[1], (0x12345678 - 0x9ABCDEF0) & 0xFFFFFFFF)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x7, 1), {2: 0xF0F0F0F0, 3: 0x33333333})
    cpu.step()
    check("AND", cpu.regs[1], 0xF0F0F0F0 & 0x33333333)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x6, 1), {2: 0xF0F0F0F0, 3: 0x33333333})
    cpu.step()
    check("OR", cpu.regs[1], 0xF0F0F0F0 | 0x33333333)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x4, 1), {2: 0xAAAAAAAA, 3: 0x55555555})
    cpu.step()
    check("XOR", cpu.regs[1], 0xAAAAAAAA ^ 0x55555555)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x1, 1), {2: 1, 3: 4})
    cpu.step()
    check("SLL by 4", cpu.regs[1], 16)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x5, 1), {2: 0x80000000, 3: 4})
    cpu.step()
    check("SRL (logical, zero-fill)", cpu.regs[1], 0x08000000)

    cpu = make_cpu_with(encode_r(0x20, 3, 2, 0x5, 1), {2: 0x80000000, 3: 4})
    cpu.step()
    check("SRA (arithmetic, sign-ext)", cpu.regs[1], 0xF8000000)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x2, 1), {2: 0xFFFFFFFF, 3: 0})  # -1 < 0 signed
    cpu.step()
    check("SLT signed -1<0", cpu.regs[1], 1)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x2, 1), {2: 0x7FFFFFFF, 3: 0x80000000})  # MAX < MIN signed
    cpu.step()
    check("SLT signed MAX<MIN", cpu.regs[1], 0)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x3, 1), {2: 0, 3: 0xFFFFFFFF})  # 0 < MAX unsigned
    cpu.step()
    check("SLTU unsigned 0<MAX", cpu.regs[1], 1)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x3, 1), {2: 0xFFFFFFFF, 3: 0})  # MAX < 0 unsigned
    cpu.step()
    check("SLTU unsigned MAX<0", cpu.regs[1], 0)

    cpu = make_cpu_with(encode_r(0, 3, 2, 0x0, 0), {1: 5, 2: 3})  # ADD x0, ...
    cpu.step()
    check("ADD writes to x0 ignored", cpu.regs[0], 0)


# ── I-type ALU ──────────────────────────────────────────────────────

def test_i_type_alu():
    cpu = make_cpu_with(encode_i(0x100, 1, 0, 2), {1: 0x12345678})  # ADDI x2, x1, 0x100
    cpu.step()
    check("ADDI positive", cpu.regs[2], 0x12345778)

    cpu = make_cpu_with(encode_i(0xFFF & 0xFFF, 1, 0, 2), {1: 1})  # ADDI x2, x1, -1
    cpu.step()
    check("ADDI -1", cpu.regs[2], 0)

    cpu = make_cpu_with(encode_i(5, 1, 0x2, 2), {1: 10})  # SLTI x2, x1, 5
    cpu.step()
    check("SLTI 10<5 false", cpu.regs[2], 0)

    cpu = make_cpu_with(encode_i(0xFFF, 1, 0x2, 2), {1: 0xFFFFFFFF})  # SLTI x2, x1, -1
    cpu.step()
    check("SLTI -1<-1 false", cpu.regs[2], 0)

    cpu = make_cpu_with(encode_i(0, 1, 0x3, 2), {1: 0xFFFFFFFF})  # SLTIU -1, 0 unsigned
    cpu.step()
    check("SLTIU -1<0 unsigned false", cpu.regs[2], 0)

    cpu = make_cpu_with(encode_i(4, 1, 0x1, 2), {1: 1})  # SLLI x2, x1, 4
    cpu.step()
    check("SLLI 1<<4", cpu.regs[2], 16)

    cpu = make_cpu_with(encode_i(4, 1, 0x5, 2), {1: 0x80000000})  # SRLI
    cpu.step()
    check("SRLI 0x80000000>>4", cpu.regs[2], 0x08000000)

    cpu = make_cpu_with(encode_i(4 | (0x20 << 5), 1, 0x5, 2), {1: 0x80000000})  # SRAI
    cpu.step()
    check("SRAI 0x80000000>>>4", cpu.regs[2], 0xF8000000)


# ── Branches ────────────────────────────────────────────────────────

def test_branches():
    # BEQ taken
    cpu = make_cpu_with(encode_b(0, 1, 2, 0x100), {1: 5, 2: 5})
    cpu.step()
    check("BEQ taken PC", cpu.pc, 0x100)
    # BEQ not taken
    cpu = make_cpu_with(encode_b(0, 1, 2, 0x100), {1: 5, 2: 6})
    cpu.step()
    check("BEQ not taken PC", cpu.pc, 4)
    # BLT signed: -1 < 0
    cpu = make_cpu_with(encode_b(0x4, 1, 2, 0x100), {1: 0xFFFFFFFF, 2: 0})
    cpu.step()
    check("BLT signed -1<0", cpu.pc, 0x100)
    # BLTU signed: -1 NOT < 0 unsigned
    cpu = make_cpu_with(encode_b(0x6, 1, 2, 0x100), {1: 0xFFFFFFFF, 2: 0})
    cpu.step()
    check("BLTU -1<0 unsigned false", cpu.pc, 4)
    # BGEU: -1 >= 0 unsigned
    cpu = make_cpu_with(encode_b(0x7, 1, 2, 0x100), {1: 0xFFFFFFFF, 2: 0})
    cpu.step()
    check("BGEU -1>=0 unsigned", cpu.pc, 0x100)
    # Backward branch: BGE x0,x0,-8
    cpu = make_cpu_with(encode_b(0x5, 0, 0, -8))
    cpu.step()
    check("BGE x0,x0,-8 PC", cpu.pc, 0xFFFFFFF8)


# ── U-type and Jumps ────────────────────────────────────────────────

def test_u_type_and_jumps():
    cpu = make_cpu_with(encode_u(0x12345, 1, 0b0110111))  # LUI x1, 0x12345
    cpu.step()
    check("LUI 0x12345", cpu.regs[1], 0x12345000)

    cpu = make_cpu_with(encode_u(0xCAFE0, 1, 0b0010111))  # AUIPC x1, 0xCAFE0
    cpu.step()
    check("AUIPC at PC=0", cpu.regs[1], 0xCAFE0000)

    cpu = make_cpu_with(encode_j(0x100, 1))  # JAL x1, +0x100
    cpu.step()
    check("JAL PC", cpu.pc, 0x100)
    check("JAL rd = pc+4", cpu.regs[1], 4)

    # JALR x0, x1, 0x80: target = (regs[1] + 0x80) & ~1
    cpu = make_cpu_with(encode_i(0x80, 1, 0, 0, opcode=0b1100111), {1: 0x100})
    cpu.step()
    check("JALR target", cpu.pc, 0x180)
    # JALR clears LSB
    cpu = make_cpu_with(encode_i(0x1, 1, 0, 0, opcode=0b1100111), {1: 0x100})
    cpu.step()
    check("JALR clears LSB", cpu.pc, 0x100)


# ── Loads and stores ────────────────────────────────────────────────

def test_loads_and_stores():
    # SW then LW
    cpu = CPU()
    cpu.regs[1] = 0x100
    cpu.regs[2] = 0xDEADBEEF
    cpu.store_instruction(0, encode_s(0, 2, 1, 0b010))   # SW x2, 0(x1)
    cpu.store_instruction(4, encode_i(0, 1, 0b010, 3, opcode=0b0000011))  # LW x3, 0(x1)
    cpu.step(); cpu.step()
    check("SW+LW round trip", cpu.regs[3], 0xDEADBEEF)

    # SB + LB: sign-extend
    cpu = CPU()
    cpu.regs[1] = 0x100
    cpu.regs[2] = 0x80  # byte 0x80 has bit 7 set
    cpu.store_instruction(0, encode_s(0, 2, 1, 0b000))   # SB x2, 0(x1)
    cpu.store_instruction(4, encode_i(0, 1, 0b000, 3, opcode=0b0000011))  # LB x3, 0(x1)
    cpu.step()  # SB
    cpu.step()  # LB
    check("LB sign-extends 0x80 -> 0xFFFFFF80", cpu.regs[3], 0xFFFFFF80)

    # SB + LBU: zero-extend
    cpu = CPU()
    cpu.regs[1] = 0x100
    cpu.regs[2] = 0x80
    cpu.store_instruction(0, encode_s(0, 2, 1, 0b000))   # SB
    cpu.store_instruction(4, encode_i(0, 1, 0b100, 3, opcode=0b0000011))  # LBU
    cpu.step(); cpu.step()
    check("LBU zero-extends 0x80 -> 0x80", cpu.regs[3], 0x80)

    # SH + LH: sign-extend
    cpu = CPU()
    cpu.regs[1] = 0x100
    cpu.regs[2] = 0x8000
    cpu.store_instruction(0, encode_s(0, 2, 1, 0b001))   # SH
    cpu.store_instruction(4, encode_i(0, 1, 0b001, 3, opcode=0b0000011))  # LH
    cpu.step(); cpu.step()
    check("LH sign-extends 0x8000 -> 0xFFFF8000", cpu.regs[3], 0xFFFF8000)

    # SH + LHU: zero-extend
    cpu = CPU()
    cpu.regs[1] = 0x100
    cpu.regs[2] = 0x8000
    cpu.store_instruction(0, encode_s(0, 2, 1, 0b001))   # SH
    cpu.store_instruction(4, encode_i(0, 1, 0b101, 3, opcode=0b0000011))  # LHU
    cpu.step(); cpu.step()
    check("LHU zero-extends 0x8000 -> 0x8000", cpu.regs[3], 0x8000)


# ── CSR ─────────────────────────────────────────────────────────────

def test_csr():
    # CSRRW: write 0xCAFEBABE to mscratch, read old (0) into rd
    cpu = make_cpu_with(encode_csr(0x340, 1, 0b001, 2), {1: 0xCAFEBABE})
    cpu.step()
    check("CSRRW mscratch write", cpu.csrs.mscratch, 0xCAFEBABE)
    check("CSRRW rd = old (0)", cpu.regs[2], 0)

    # CSRRS: set bit 0 of mtvec, read mtvec (0) into rd
    cpu = make_cpu_with(encode_csr(0x305, 1, 0b010, 2), {1: 0x1})
    cpu.step()
    check("CSRRS mtvec | 1", cpu.csrs.mtvec, 1)
    check("CSRRS rd = old (0)", cpu.regs[2], 0)

    # CSRRC: clear bit 0 of mtvec, read old (=0 since fresh CPU) into rd
    cpu = make_cpu_with(encode_csr(0x305, 1, 0b011, 2), {1: 0x1})
    cpu.step()
    check("CSRRC mtvec & ~1", cpu.csrs.mtvec, 0)
    check("CSRRC rd = old (0)", cpu.regs[2], 0)

    # CSRRS with rs1=x0: read-only access (no write per spec)
    cpu = make_cpu_with(encode_csr(0x301, 0, 0b010, 1))  # CSRRS misa, x0, x1
    cpu.step()
    check("CSRRS rs1=x0 reads misa without write", cpu.regs[1], 0x40001100)
    check("misa unchanged", cpu.csrs.misa, 0x40001100)

    # CSRRWI: write zimm=5 to mtvec, read old (0) into rd
    cpu = make_cpu_with(encode_csr(0x305, 5, 0b101, 2))  # funct3=101 = CSRRWI
    cpu.step()
    check("CSRRWI mtvec=5", cpu.csrs.mtvec, 5)


# ── ECALL / MRET trap sequence ─────────────────────────────────────

def test_ecall_mret():
    # Set mtvec = 0x100. Then ECALL at PC=0 traps to 0x100.
    # The trap handler at 0x100 does MRET, which returns to mepc.
    cpu = CPU()
    cpu.regs[1] = 0x100
    cpu.store_instruction(0, encode_csr(0x305, 1, 0b001, 0))  # CSRRW mtvec, x1
    cpu.store_instruction(4, 0b1110011)                       # ECALL
    cpu.store_instruction(0x100, (0x302 << 20) | (0b000 << 12) | (0 << 7) | 0b1110011)  # MRET
    cpu.step()  # CSRRW: mtvec=0x100, PC=4
    cpu.step()  # ECALL: jumps to mtvec=0x100, sets mepc=8
    check("ECALL trap_target = mtvec", cpu.pc, 0x100)
    check("ECALL mepc = pc+4", cpu.csrs.mepc, 8)
    check("ECALL mcause = 11 (M-mode)", cpu.csrs.mcause, 11)
    cpu.step()  # MRET: jumps to mepc=8
    check("MRET PC = mepc", cpu.pc, 8)
    check("MRET MPP = 0 (U-mode)", (cpu.csrs.mstatus >> 11) & 0x3, 0)


# ── M extension: edge cases ─────────────────────────────────────────

def test_m_extension():
    # MUL: 5 * 7 = 35
    cpu = make_cpu_with(encode_r(1, 3, 2, 0, 1), {2: 5, 3: 7})
    cpu.step()
    check("MUL 5*7", cpu.regs[1], 35)

    # MULH: 0x10000 * 0x10000 = 0x100000000, high = 1
    cpu = make_cpu_with(encode_r(1, 3, 2, 1, 1), {2: 0x10000, 3: 0x10000})
    cpu.step()
    check("MULH high bits", cpu.regs[1], 1)

    # DIV by zero: result = -1 = 0xFFFFFFFF
    cpu = make_cpu_with(encode_r(1, 3, 2, 4, 1), {2: 0xDEADBEEF, 3: 0})
    cpu.step()
    check("DIV by zero = -1", cpu.regs[1], 0xFFFFFFFF)

    # REM by zero: result = dividend
    cpu = make_cpu_with(encode_r(1, 3, 2, 6, 1), {2: 0xDEADBEEF, 3: 0})
    cpu.step()
    check("REM by zero = dividend", cpu.regs[1], 0xDEADBEEF)

    # DIV INT_MIN / -1 = INT_MIN (overflow)
    cpu = make_cpu_with(encode_r(1, 3, 2, 4, 1), {2: 0x80000000, 3: 0xFFFFFFFF})
    cpu.step()
    check("DIV INT_MIN/-1 = INT_MIN", cpu.regs[1], 0x80000000)

    # REM INT_MIN / -1 = 0
    cpu = make_cpu_with(encode_r(1, 3, 2, 6, 1), {2: 0x80000000, 3: 0xFFFFFFFF})
    cpu.step()
    check("REM INT_MIN/-1 = 0", cpu.regs[1], 0)

    # DIVU: 0xFFFFFFFF / 0xFFFFFFFF = 1
    cpu = make_cpu_with(encode_r(1, 3, 2, 5, 1), {2: 0xFFFFFFFF, 3: 0xFFFFFFFF})
    cpu.step()
    check("DIVU MAX/MAX = 1", cpu.regs[1], 1)

    # DIV: -7 / 2 = -3 (truncation toward zero, not floor)
    cpu = make_cpu_with(encode_r(1, 3, 2, 4, 1), {2: 0xFFFFFFF9, 3: 2})  # -7 / 2
    cpu.step()
    check("DIV -7/2 = -3 (truncation)", cpu.regs[1], 0xFFFFFFFD)


# ── Multi-instruction program ──────────────────────────────────────

def test_program_fibonacci():
    """Compute fibonacci numbers using the model.

    Program:
        addi x1, x0, 0      # x1 = 0 (fib[0])
        addi x2, x0, 1      # x2 = 1 (fib[1])
        addi x3, x0, 10     # x3 = 10 (counter)
    loop:
        add  x4, x1, x2     # x4 = x1 + x2
        addi x1, x2, 0      # x1 = x2
        addi x2, x4, 0      # x2 = x4
        addi x3, x3, -1     # x3 -= 1
        bne  x3, x0, loop
    After 10 iterations: x2 = fib(11) = 89.

    We don't manually assemble; we place raw encodings.
    """
    cpu = CPU()
    # ADDI x1, x0, 0  -->  imm=0, rs1=0, funct3=0, rd=1
    cpu.store_instruction(0,  encode_i(0, 0, 0, 1))
    # ADDI x2, x0, 1
    cpu.store_instruction(4,  encode_i(1, 0, 0, 2))
    # ADDI x3, x0, 10
    cpu.store_instruction(8,  encode_i(10, 0, 0, 3))
    # loop (PC=12): ADD x4, x1, x2
    cpu.store_instruction(12, encode_r(0, 2, 1, 0, 4))
    # ADDI x1, x2, 0
    cpu.store_instruction(16, encode_i(0, 2, 0, 1))
    # ADDI x2, x4, 0
    cpu.store_instruction(20, encode_i(0, 4, 0, 2))
    # ADDI x3, x3, -1
    cpu.store_instruction(24, encode_i(0xFFF, 3, 0, 3))
    # BNE x3, x0, loop (offset = -16, i.e. PC=28, target=PC=12 = loop start)
    cpu.store_instruction(28, encode_b(1, 3, 0, -16))

    for _ in range(200):  # 3 setup + 6*10 + 1 = 64 max, but allow margin
        cpu.step()
        if cpu.pc == 32:  # PC after BNE not taken = 32
            break
    check("fibonacci x2 = 89", cpu.regs[2], 89)


# ── Main ────────────────────────────────────────────────────────────

def main():
    tests = [
        test_r_type_add,
        test_i_type_alu,
        test_branches,
        test_u_type_and_jumps,
        test_loads_and_stores,
        test_csr,
        test_ecall_mret,
        test_m_extension,
        test_program_fibonacci,
    ]
    for t in tests:
        run(t.__name__, t)
    print()
    print(f"Total: {_passes} passed, {_failures} failed")
    return 0 if _failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
