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

    /* Tohost at 0x708, the same address the riscv-tests use, so one FPGA
       build (TOHOST_ADDR = 0x708) detects the end of every benchmark.
       Check with: riscv-none-elf-nm <elf> | grep tohost */
    . = 0x00000708;
    .tohost : {
        *(.tohost)
    }

    /DISCARD/ : {
        *(.comment)
        *(.riscv.attributes)
    }
}
