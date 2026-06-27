# Minimal RISC-V validation program.
# Executes a sequence of instructions with known behavior, then signals
# completion by writing 1 to tohost.
#
# Expected behavior:
#   1. x1 = 0x1234
#   2. x2 = 0x5678
#   3. x3 = x1 + x2 = 0x68AC
#   4. x4 = lw from memory (DMEM must be initialized)
#   5. BEQ taken once (tests branch prediction/flushing)
#   6. tohost = 1 (benchmark done)

.section .text.init
.global _start

_start:
    # Initialize stack pointer
    la sp, _stack_top

    # Basic ALU operations
    li   x1, 0x1234          # x1 = 0x1234
    li   x2, 0x5678          # x2 = 0x5678
    add  x3, x1, x2          # x3 = 0x68AC  (expected)

    # Memory store and load
    li   x5, 0xBEEF          # data to store
    la   x6, _dmem_start     # DMEM base address
    sw   x5, 0(x6)           # mem[0] = 0xBEEF
    lw   x7, 0(x6)           # x7 = 0xBEEF (load-use hazard)

    # Branch (taken once, tests flush)
    li   x10, 1
    li   x11, 1
    beq  x10, x11, _taken    # should be taken
    li   x12, 0xDEAD         # should not execute

_taken:
    li   x12, 0xCAFE         # x12 = 0xCAFE (executed after branch)

    # Jump and link
    jal  x13, _target
    li   x14, 0xBAD          # should not execute

_target:
    li   x14, 0xC0DE         # x14 = 0xC0DE

    # ALU immediate
    addi x15, x14, 1         # x15 = 0xC0DF

    # Logical operations
    and  x16, x1, x2         # x16 = 0x1234 & 0x5678 = 0x1230
    or   x17, x1, x2         # x17 = 0x1234 | 0x5678 = 0x567C
    xor  x18, x1, x2         # x18 = 0x1234 ^ 0x5678 = 0x444C

    # Branch not taken
    li   x20, 1
    li   x21, 2
    beq  x20, x21, _should_not  # should NOT be taken
    li   x22, 0xACE          # x22 = 0xACE (executed)

_should_not:
    li   x22, 0xBAD          # should not execute

    # Write tohost = 1 to signal benchmark completion
    # Using the same address as riscv-tests (0x708) for compatibility
    li   a0, 1
    la   a1, tohost
    sw   a0, 0(a1)

    # Infinite loop after completion
_loop:
    j _loop

.section .tohost, "aw", @progbits
.align 4
tohost:     .word 0
fromhost:   .word 0

.section .dmempool, "aw", @progbits
.align 4
_dmem_start:
.space 256

# Stack grows downward from _stack_top
.section .stack, "aw", @progbits
.align 4
_stack_bottom:
.space 256
_stack_top:
