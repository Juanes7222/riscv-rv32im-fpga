OUTPUT_ARCH(riscv)
ENTRY(_start)

SECTIONS
{
    /* All sections contiguous so the linker creates a single PT_LOAD segment.
       The tohost address is exported so the FPGA build can set TOHOST_ADDR. */
    . = 0x00000000;
    .text : {
        *(.text.init)
        *(.text)
    }

    . = ALIGN(4);
    .rodata : {
        *(.rodata)
    }

    /* Data at 0x200 (DMEM word 0x80), away from tohost. */
    . = 0x00000200;
    .data : {
        *(.data)
    }

    /* Tohost at 0x100 (DMEM word 0x40). The exact address varies by program
       size; check with: riscv-none-elf-objdump -t <elf> | grep tohost
       The FPGA build must set TOHOST_ADDR to match this address. */
    . = 0x00000100;
    .tohost : {
        *(.tohost)
    }

    /DISCARD/ : {
        *(.comment)
        *(.riscv.attributes)
    }
}
