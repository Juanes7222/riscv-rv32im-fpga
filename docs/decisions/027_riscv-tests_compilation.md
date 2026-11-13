# ADR 027 - riscv-tests compilation for reset vector 0x00000000

**Status:** Accepted (rewritten 2026-11-12: the overrides live in
`verification/riscv-tests-build/`, not inside the submodule)
**Date:** 2026-05-11
**Depends on:** ADR 012 (reset vector), ADR 013 (memory sizes), ADR 014 (.mem
format), ADR 030 (CSR/trap), ADR 033 (rv32mi), ADR 047 (data window)

---

## Context

The `riscv-tests` suite ships with a linker script that places `.text.init` at
`0x80000000`, targeting Linux-capable cores with an MMU. This processor resets
to `0x00000000` (ADR 012) and has no MMU, so the suite needs a different linker
script. It also needs a different memory split: the instruction image must fit
`IMEM_DEPTH = 4096` words and the data image the 4 KB data window (ADR 047).

The suite is a Git submodule at `verification/riscv-tests/`. Its own
`.gitignore` excludes `/Makefile`, and a parent repository cannot commit files
inside a submodule path, so a build harness placed there is untracked and a
fresh clone cannot reproduce the compilation. The first version of this ADR
specified exactly that layout (`verification/riscv-tests/Makefile` and
`verification/riscv-tests/link.ld`); the Makefile was a local, ignored file and
`link.ld` did not exist, so the compilation was not reproducible from the
repository.

The trap conventions the tests exercise (`ecall` → handler at `mtvec` → write to
`tohost`) are implemented by the CSR file and the trap path of ADR 030.

## Decision

The project-local build harness lives **outside** the submodule, in a tracked
directory:

```
verification/riscv-tests-build/
├── Makefile
└── link.ld
```

and the root `Makefile` exposes it as `make riscv-tests`.

### Linker script (`verification/riscv-tests-build/link.ld`)

```ld
OUTPUT_ARCH(riscv)
ENTRY(_start)

SECTIONS
{
    . = 0x00000000;                    /* reset vector (ADR 012) */
    .text.init : { *(.text.init) }
    .text      : { *(.text*) }

    . = ALIGN(16);
    .tohost : { *(.tohost) }
    .rodata : { *(.rodata*) }
    .data   : { *(.data*) }
    .bss    : { *(.bss*) *(COMMON) }

    . = ALIGN(8);
    _end = .;
}
```

Executable sections go to the instruction image; every other allocated section
goes to the data image, whose lowest address is 0, so `elf_to_mem_split.py`
produces an IMEM image and a DMEM image with base 0 (ADR 014/047). `tohost` lives
in its own section, so its address is whatever the preceding `.text` size
dictates (for example `0x6c0` for `add`); the testbench reads it from the ELF
symbol table (ADR 028) and the hardware gets it through `TOHOST_ADDR` (ADR 051).

### Compilation

```bash
riscv-none-elf-gcc \
    -march=rv32im_zicsr_zicntr \
    -mabi=ilp32 -static -nostdlib \
    -T verification/riscv-tests-build/link.ld \
    -I verification/riscv-tests/isa/macros/scalar \
    -I verification/riscv-tests/env/p \
    verification/riscv-tests/isa/rv32ui/<test>.S \
    -o build/riscv-tests/rv32ui/<test>.elf
```

`-march` is `rv32im_zicsr_zicntr`, not plain `rv32im`: the RV32MI tests use CSR
instructions and `instret`/`zicntr` (ADR 030, 033).

### Targets

The Makefile builds all three suites and writes the ELFs to
`build/riscv-tests/{rv32ui,rv32um,rv32mi}/`:

| Target | Tests |
|---|---|
| `rv32i` | 37 (the RV32I base list below) |
| `rv32m` | 8 (`div`, `divu`, `mul`, `mulh`, `mulhsu`, `mulhu`, `rem`, `remu`) |
| `rv32mi` | 15 (`breakpoint csr illegal ma_addr ma_fetch mcsr scall sbreak shamt lh-misaligned lw-misaligned sh-misaligned sw-misaligned zicntr instret_overflow`; `pmpaddr` omitted, no PMP) |
| `all` | the three above (default) |
| `clean` | removes the three build directories |

The toolchain is expected as `riscv-none-elf-gcc` on `PATH`; CI and the
development machines install it under `/opt/riscv/bin`.

## Consequences

- The build is reproducible from the repository: both files are tracked, and a
  fresh clone only needs the submodule plus the toolchain.
- No file inside the submodule is modified; the submodule stays pinned.
- A new test is added to `TESTS_RV32I` / `TESTS_RV32M` / `TESTS_RV32MI` in
  `verification/riscv-tests-build/Makefile`; no linker script or RTL change.
- `build/riscv-tests/` is not committed; binaries are regenerated per machine.
- The `.mem` split is done by `scripts/elf_to_mem_split.py` (ADR 014), not by
  `objcopy` alone, because the two images are separated by section.
- `make riscv-tests` is a prerequisite of the cocotb suites that consume the
  ELFs; the test modules fail with a clear message when an ELF is missing.
