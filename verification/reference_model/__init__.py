"""
Python reference model for the RV32IM ISA.

This package provides a functional model of the RV32IM CPU that can
be used to verify the SystemVerilog DUTs in this project. The model
matches the DUT's behavior exactly (including a few known non-standard
choices in the DUT, like mepc = pc+4 on trap entry — see csr.py).

Main components:
  - CPU:           CPU state and step() method.
  - decode:        32-bit raw → Instruction.
  - HANDLERS:      dict of instruction name → handler function.
  - encoders:      R/I/S/B/U/J-type encoders.
  - CSRFile:       machine-mode CSR file.

The model is single-step (one Python call per instruction). For
multi-cycle DUT operations (M-extension division), the model-vs-DUT
test is responsible for stepping the DUT multiple times per model step.

Usage:

    from reference_model import CPU
    from reference_model.encoders import encode_r, encode_i

    cpu = CPU()
    cpu.regs[2] = 0x12345678
    cpu.regs[3] = 0x9ABCDEF0
    cpu.store_instruction(0, encode_r(0, 3, 2, 0, 1))  # ADD x1, x2, x3
    cpu.step()
    assert cpu.regs[1] == (0x12345678 + 0x9ABCDEF0) & 0xFFFFFFFF
"""
from .cpu      import CPU
from .decoder  import Instruction, decode
from .encoders import (
    encode_r, encode_i, encode_s, encode_b, encode_u, encode_j, encode_csr,
)
from .csr      import CSRFile
from .handlers import HANDLERS

__all__ = [
    "CPU", "Instruction", "decode", "HANDLERS", "CSRFile",
    "encode_r", "encode_i", "encode_s", "encode_b", "encode_u", "encode_j",
    "encode_csr",
]
