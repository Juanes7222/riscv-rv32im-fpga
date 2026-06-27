// Synthetic benchmark: load-use hazard stress.
// Tests load-use stall penalty in the pipeline.
//
// Structure: write test data to DMEM, then loop with load→use sequences.
// Each iteration: 4×lw + 4×addi + 1×addi(decrement) + 1×bne
// Load-use hazard: lw value used by next instruction → 1 stall cycle
//
// Per iteration counted (ru_wr=1): 4×lw + 4×addi + 1×addi = 9
// N = 111 → 999 counted instructions + ~111 stall cycles

.section .text.init
.globl _start

_start:
    // Initialize DMEM with test data (not counted: sw has ru_wr=0)
    li      x1, 0xDEADBEEF
    sw      x1, 0x200(x0)
    li      x2, 0xCAFEBABE
    sw      x2, 0x204(x0)
    li      x3, 0x12345678
    sw      x3, 0x208(x0)
    li      x4, 0x87654321
    sw      x4, 0x20C(x0)

    li      x5, 111         // iteration count

loop:
    lw      x10, 0x200(x0)  // load → stall if followed by RAW
    addi    x11, x10, 1     // load-use: 1 stall in pipeline

    lw      x12, 0x204(x0)  // load
    addi    x13, x12, 1     // load-use: 1 stall

    lw      x14, 0x208(x0)  // load
    addi    x15, x14, 1     // load-use: 1 stall

    lw      x16, 0x20C(x0)  // load
    addi    x17, x16, 1     // load-use: 1 stall

    addi    x5, x5, -1      // decrement counter
    bne     x5, x0, loop    // not counted (ru_wr=0)

    // tohost = 1
    li      a0, 1
    la      a1, tohost
    sw      a0, 0(a1)

loop_end:
    j loop_end

.section .tohost
.align 4
tohost:   .word 0
fromhost: .word 0
