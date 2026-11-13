/* riscv-tests linker script for the rv32im-pc DE1-SoC processor (ADR 027).
 *
 * The reset vector is 0x00000000 (ADR 012).  Executable sections go to the
 * instruction image; every other allocated section goes to the data image,
 * which must fit in the 4 KB data window (ADR 047).  The project-local build
 * harness lives in verification/riscv-tests-build/ so the parent repository
 * can track it (the submodule ignores /Makefile and the parent cannot commit
 * inside a submodule path).
 */

OUTPUT_ARCH(riscv)
ENTRY(_start)

SECTIONS
{
    /* Instruction image, at the reset vector. */
    . = 0x00000000;
    .text.init : { *(.text.init) }
    .text      : { *(.text*) }

    /* Data image.  The lowest data address is 0, so the ELF-to-.mem splitter
       uses base 0 for this program and the whole image fits the 4 KB window. */
    . = ALIGN(16);
    .tohost : { *(.tohost) }
    .rodata : { *(.rodata*) }
    .data   : { *(.data*) }
    .bss    : { *(.bss*) *(COMMON) }

    . = ALIGN(8);
    _end = .;
}
