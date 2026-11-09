// NOPs, a flushed instruction, load-use and division in one retirement window.
.section .text
.globl _start
_start:
    nop
    li t0, 20
    li t1, 4
    div t2, t0, t1
    nop
    la t3, scratch
    sw t2, 0(t3)
    lw t4, 0(t3)
    jal ra, target
    add t5, t4, t2
    beq t5, t0, failed
    beq t5, t5, passed
    li t0, 99
failed:
    li t1, 3
    j finish
passed:
    nop
    li t1, 1
finish:
    la t0, tohost
    sw t1, 0(t0)
1:  j 1b
target:
    addi t4, t4, 1
    ret
.section .data
.align 2
scratch: .word 0

.section .tohost,"aw",@progbits
.align 2
.globl tohost
tohost: .word 0
