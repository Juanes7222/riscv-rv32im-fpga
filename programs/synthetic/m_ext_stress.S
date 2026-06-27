// Synthetic benchmark: M-extension stress (multiply and divide).
// Tests multi-cycle instruction CPI.
//
// Structure: loop with DIV (34 cycles) + MUL (1 cycle).
// Pipeline stalls during DIV but not during MUL.
//
// Per iteration: 1×div + 1×mul + 1×addi + 1×bne = 4 instructions
// Counted: 1×div + 1×mul + 1×addi = 3
// N = 30 → 90 counted instructions
// Pipeline cycles: 30 × (34 div stall + 1 mul + 1 addi + 1 bne) >> 30 × 37
// But bne is also stalled during div, so cycles = 30 × (34 div + 1 mul + 2 post-mul)
// = 30 × 37 = 1110 cycles for 90 counted = CPI ≈ 12.3

.section .text.init
.globl _start

_start:
    li      x1, 7           // dividend
    li      x2, 3           // divisor
    li      x3, 30          // iteration count

loop:
    div     x10, x1, x2     // 34 cycles (pipeline stalls)
    mul     x11, x10, x2    // 1 cycle, depends on div result

    addi    x1, x1, 1       // new dividend
    addi    x3, x3, -1      // decrement counter
    bne     x3, x0, loop    // not counted (ru_wr=0)

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
