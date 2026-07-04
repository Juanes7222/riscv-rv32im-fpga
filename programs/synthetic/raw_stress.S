// Synthetic benchmark: RAW dependency chain stress.
// Tests forwarding effectiveness in the pipeline.
//
// Loop: 6-instruction ADD chain (each dependent on previous result).
// Forwarding resolves all RAW --> no stalls expected.
//
// Per iteration: 6xadd + 1xaddi + 1xbne = 8 instructions
// Counted (ru_wr=1): 6xadd + 1xaddi = 7
// N = 143 --> 1001 counted instructions

.section .text.init
.globl _start

_start:
    li      x1, 1           // value to propagate through chain
    li      x2, 143         // iteration count

loop:
    add     x3, x1, x0      // RAW: depends on x1
    add     x4, x3, x0      // RAW: depends on x3
    add     x5, x4, x0      // RAW: depends on x4
    add     x6, x5, x0      // RAW: depends on x5
    add     x7, x6, x0      // RAW: depends on x6
    add     x1, x7, x0      // RAW: depends on x7

    addi    x2, x2, -1      // decrement counter
    bne     x2, x0, loop    // not counted (ru_wr=0)

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
