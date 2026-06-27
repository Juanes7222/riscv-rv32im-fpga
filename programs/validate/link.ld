OUTPUT_ARCH(riscv)
ENTRY(_start)

/* Match FPGA synthesis defaults: IMEM_DEPTH=2048 (8KB), DMEM_DEPTH=512 (2KB).
   cocotb overrides to 16384/8192 via env vars but the linker must target
   the smaller FPGA size so .mem files are compatible with both. */
MEMORY
{
    imem (rx)  : ORIGIN = 0x00000000, LENGTH = 8K
    dmem (rw)  : ORIGIN = 0x01000000, LENGTH = 2K
}

SECTIONS
{
    .text : {
        *(.text.init)
        *(.text)
    } > imem

    .rodata : {
        *(.rodata)
    } > imem

    .tohost : ALIGN(4) {
        *(.tohost)
    } > dmem

    .dmempool : ALIGN(4) {
        _dmem_start = .;
        *(.dmempool)
    } > dmem

    /* 256-byte stack fits easily in 2KB DMEM */
    .stack : ALIGN(16) {
        _stack_bottom = .;
        . += 256;
        _stack_top = .;
    } > dmem

    /DISCARD/ : {
        *(.comment)
        *(.riscv.attributes)
    }
}
