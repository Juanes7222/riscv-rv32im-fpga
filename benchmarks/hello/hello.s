.section .text
.globl _start

_start:
    li   x1, 0xDEAD
    li   x2, 0xBEEF
    add  x3, x1, x2
    sw   x3, 0(x0)
halt:
    j    halt