/* CoreMark linker script for RV32IM bare-metal.
   Harvard architecture: executable sections --> IMEM, everything else --> DMEM.
   The two memories are separate, with their own address decoders, so the
   data sections no longer have to sit above .text.

   The data window is 0x6000-0x7000: 4 KB, the depth of the single-cycle data
   memory (DMEM_DEPTH = 1024, ADR 047).  Everything the program reads with a
   load has to fit in it, .rodata included: CoreMark's CRC tables live there
   and the benchmark fails its own verification without them.

   The image is packed with no gaps so that the whole writable footprint plus
   the read-only data fits: .tohost 8 B, .rodata 1.4 KB, .data 12 B, .bss
   2 KB (MEM_STATIC keeps the working block there) and the stack, which takes
   whatever is left (~700 B; the call frames measure ~400 B).

   .tohost at 0x6000 is not the RTL default (0x708, the riscv-tests value):
   build the CoreMark bitstream with TOHOST_ADDR=0x6000. */

OUTPUT_ARCH(riscv)
ENTRY(_start)

SECTIONS
{
    /* ---------- IMEM: executable code only ---------- */
    . = 0x00000000;
    .text : {
        *(.text.init)
        *(.text)
        *(.text.*)
    }

    /* ---------- DMEM: base of the 4 KB window ---------- */
    . = 0x00006000;
    .tohost : {
        PROVIDE(tohost = .);
        LONG(0);
        LONG(0);
    }

    /* Read-only data is data: it is loaded from, not executed. */
    . = ALIGN(4);
    .rodata : {
        *(.rodata)
        *(.rodata.*)
        *(.srodata)
        *(.srodata.*)
    }

    . = ALIGN(4);
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

    /* The stack is whatever is left of the window.  If .bss grows past the
       top the size would go negative and the link fails. */
    . = ALIGN(16);
    __stack_bottom = .;
    __stack_size = 0x00007000 - __stack_bottom;
    .stack (NOLOAD) : {
        . += __stack_size;
        PROVIDE(__stack_top = .);
    }

    ASSERT(__stack_top - __stack_bottom >= 0x200,
           "CoreMark: less than 512 bytes of stack left in the 4 KB data window")

    /DISCARD/ : {
        *(.comment)
        *(.riscv.attributes)
        *(.eh_frame)
        *(.eh_frame_hdr)
    }
}
