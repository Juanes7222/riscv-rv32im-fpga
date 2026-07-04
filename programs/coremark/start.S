// CoreMark bare-metal C runtime startup for RV32IM.
// Sets up stack from linker symbol, clears BSS, calls main(),
// then signals completion via tohost.

.section .text.init
.globl _start
.type _start, @function

_start:
    // Stack pointer: __stack_top defined in link.ld at top of DMEM.
    la      sp, __stack_top

    // Clear BSS: __bss_start to __bss_end.
    la      t0, __bss_start
    la      t1, __bss_end
    bgeu    t0, t1, 2f
1:
    sw      zero, 0(t0)
    addi    t0, t0, 4
    bltu    t0, t1, 1b
2:

    // Call main(argc=0, argv=NULL)
    li      a0, 0
    li      a1, 0
    jal     ra, main

    // main() returned: signal benchmark done via tohost = 1
    li      t0, 1
    la      t1, tohost
    sw      t0, 0(t1)

    // Safety: infinite loop
3:
    j       3b
