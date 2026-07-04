// Synthetic benchmark: branch penalty stress.
// Tests branch flush penalty in the pipeline.
//
// Structure: dense taken branches where each branch is followed by
// counted instructions.
//
// Per taken branch: 1xbeq(taken) + 2xnop(flushed) + 1xaddi + 1xbne(not taken)
// Counted (ru_wr=1): 1xaddi per branch (branches not counted)
// But bne not taken still has ru_wr=0.
//
// Better approach: loop with an ALU instruction between branches.
// Per iteration: beq(taken) + addi(counted) + bne(loop, not taken)
// = 2 flushes per iteration in pipeline (beq forward, bne backward)
// Counted per iteration: 1xaddi
//
// N = 1000 --> 1000 counted instructions, ~2000 flush cycles

.section .text.init
.globl _start

_start:
    li      x1, 1000        // iteration count
    li      x2, 1           // constant for addi

loop:
    beq     x0, x0, target  // always taken --> flush (2 cycles pipeline)
    nop
    nop

target:
    addi    x3, x3, 1       // counted instruction (ru_wr=1)
    addi    x1, x1, -1      // decrement counter
    bne     x1, x0, loop    // taken N-1 times --> flush on taken

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
