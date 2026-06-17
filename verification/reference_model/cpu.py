"""
CPU state and step() method for the reference model.

The CPU class holds:
  - pc:           32-bit program counter
  - regs[32]:     32 general-purpose registers (regs[0] is always 0)
  - imem:         instruction memory (bytearray, word-addressed via
                  _fetch which masks pc to 4-byte boundary)
  - dmem:         data memory (bytearray, byte-addressable, little-endian)
  - csrs:         CSRFile instance (machine mode)

The step() method:
  1. Fetches the 32-bit instruction at PC.
  2. Decodes it via the decoder.
  3. Dispatches to the handler (which may update regs, mem, csr, pc).
  4. If the handler did not update PC, advances PC by 4.

Traps (ECALL/EBREAK/MRET) are handled by take_trap(), which the
ECALL/EBREAK handlers call. MRET is dispatched to the MRET handler
directly, which calls csrs.trap_exit().

The model is single-step (no notion of clock cycles). For M-extension
instructions (MUL/DIV/REM), the model computes the result in one
step; the DUT takes 1/34 cycles respectively. Model-vs-DUT tests
must step the DUT multiple times for multi-cycle DUT operations.
"""
import struct

from .decoder import decode
from .csr     import CSRFile
from .handlers import HANDLERS


class CPU:
    """RV32IM CPU state, decoupled from any clock/reset concept."""

    DEFAULT_IMEM_SIZE = 16384
    DEFAULT_DMEM_SIZE = 8192

    def __init__(self, imem_size=DEFAULT_IMEM_SIZE, dmem_size=DEFAULT_DMEM_SIZE):
        self.pc = 0
        self.regs = [0] * 32
        self.imem = bytearray(imem_size)
        self.dmem = bytearray(dmem_size)
        self.csrs = CSRFile()

    # ── Reset ──

    def reset(self):
        """Reset to initial state. PC=0, regs=0, mem=0, CSRs at reset values."""
        self.pc = 0
        self.regs = [0] * 32
        # imem and dmem are not cleared: the test may have preloaded them.
        self.csrs.reset()

    # ── Instruction memory access ──

    def _fetch(self, pc):
        """Read a 32-bit instruction from imem at word-aligned pc."""
        word_addr = (pc & 0xFFFFFFFC) % len(self.imem)
        return struct.unpack_from("<I", self.imem, word_addr)[0]

    def store_instruction(self, addr, word):
        """Write a 32-bit instruction to imem at byte address `addr`."""
        word &= 0xFFFFFFFF
        struct.pack_into("<I", self.imem, addr % len(self.imem), word)

    # ── Data memory access (little-endian) ──

    def load_byte(self, addr):
        return self.dmem[addr % len(self.dmem)]

    def load_half(self, addr):
        # Little-endian: low byte at addr, high byte at addr+1
        lo = self.dmem[addr       % len(self.dmem)]
        hi = self.dmem[(addr + 1) % len(self.dmem)]
        return lo | (hi << 8)

    def load_word(self, addr):
        return struct.unpack_from("<I", self.dmem, addr % len(self.dmem))[0]

    def store_byte(self, addr, value):
        self.dmem[addr % len(self.dmem)] = value & 0xFF

    def store_half(self, addr, value):
        self.dmem[addr       % len(self.dmem)] = value & 0xFF
        self.dmem[(addr + 1) % len(self.dmem)] = (value >> 8) & 0xFF

    def store_word(self, addr, value):
        struct.pack_into("<I", self.dmem, addr % len(self.dmem), value & 0xFFFFFFFF)

    # ── Trap handling ──

    def take_trap(self, cause):
        """Trap entry: save pc+4 to mepc, set mcause, jump to mtvec."""
        trap_pc4 = (self.pc + 4) & 0xFFFFFFFF
        self.csrs.trap_enter(trap_pc4, cause)
        self.pc = self.csrs.trap_target

    # ── Step ──

    def step(self):
        """Fetch, decode, execute one instruction.

        If the handler does not update pc, advances pc by 4."""
        pc_before = self.pc
        raw = self._fetch(pc_before)
        instr = decode(raw)
        handler = HANDLERS.get(instr.name)
        if handler is not None:
            handler(self, instr)
        else:
            # Unknown / illegal: treat as NOP (matches the DUT's default
            # case in control_unit.sv, which leaves ru_wr=0 and br_op=NONE).
            # The DUT does NOT trap on illegal encodings.
            self.pc = (pc_before + 4) & 0xFFFFFFFF
            return
        # If the handler didn't change PC, advance by 4.
        if self.pc == pc_before:
            self.pc = (pc_before + 4) & 0xFFFFFFFF
