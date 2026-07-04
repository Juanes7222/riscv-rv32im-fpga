/* CoreMark linker script for RV32IM bare-metal.
   Harvard architecture: .text --> IMEM, .data/.tohost --> DMEM.
   The linker sees a flat address space; we assign unique addresses to all
   sections.  .text at 0x0, tohost at 0x5000 (well above .text end for ~9 KB
   CoreMark), data at 0x6000, stack at top of 32 KB DMEM (0x8000). */

OUTPUT_ARCH(riscv)
ENTRY(_start)

SECTIONS
{
    /* ---------- IMEM ---------- */
    . = 0x00000000;
    .text : {
        *(.text.init)
        *(.text)
        *(.text.*)
    }

    . = ALIGN(4);
    .rodata : {
        *(.rodata)
        *(.rodata.*)
        *(.srodata)
        *(.srodata.*)
    }

    /* ---------- DMEM: tohost at 0x5000 ---------- */
    . = 0x00005000;
    .tohost : {
        PROVIDE(tohost = .);
        LONG(0);
        LONG(0);
    }

    /* ---------- DMEM: data at 0x6000 ---------- */
    . = 0x00006000;
    .data : {
        __data_start = .;
        *(.data)
        *(.data.*)
        *(.sdata)
        *(.sdata.*)
        __data_end = .;
    }

    . = ALIGN(4);
    .bss : {
        __bss_start = .;
        *(.bss)
        *(.bss.*)
        *(.sbss)
        *(.sbss.*)
        *(COMMON)
        __bss_end = .;
    }

    /* Stack: 4 KB at top of DMEM (grows down from just below 0x8000). */
    . = 0x00007000;
    .stack : {
        . += 4096;
        . = ALIGN(16);
        PROVIDE(__stack_top = .);  /* = 0x8000 */
    }

    /DISCARD/ : {
        *(.comment)
        *(.riscv.attributes)
        *(.eh_frame)
        *(.eh_frame_hdr)
    }
}
