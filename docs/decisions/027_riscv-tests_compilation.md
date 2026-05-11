# ADR 027 — riscv-tests Compilation for Reset Vector 0x00000000

**Status:** Accepted  
**Date:** 2026-05-11  
**Depends on:** ADR 012 (reset vector), ADR 013 (memory sizes), ADR 014 (.mem format)

---

## Context

The `riscv-tests` suite (github.com/riscv/riscv-tests) ships with a default
linker script that places `.text.init` at `0x80000000`, targeting Linux-capable
cores with an MMU. This project's processor resets to `0x00000000` (ADR 012)
and has no MMU. Running riscv-tests without modifications would produce binaries
that begin at an address the instruction memory cannot serve, causing immediate
mis-fetch.

The suite provides individual assembly test files (`rv32ui/`, `rv32um/`) and a
shared `env/p/` environment (bare-metal, no virtual memory) that already
contains the framework macros (`RVTEST_RV32U`, `TESTNUM`, `RVTEST_PASS`,
`RVTEST_FAIL`). The `env/p/` environment writes a result code to a symbol named
`tohost` and then loops forever. The processor does not need to implement
`ecall`; the testbench monitors the write address on the data bus.

The only change required is the base address in the linker script.

---

## Decision

The riscv-tests suite is cloned as a Git submodule at
`verification/riscv-tests/`. A single custom linker script,
`verification/riscv-tests/link.ld`, overrides the default base address:

```ld
OUTPUT_ARCH(riscv)
ENTRY(_start)

SECTIONS {
    . = 0x00000000;          /* matches reset vector (ADR 012) */
    .text.init : { *(.text.init) }
    .text      : { *(.text*) }
    . = ALIGN(4);
    .data      : { *(.data*) }
    .bss       : { *(.bss*) }
    . = ALIGN(4);
    tohost = .;              /* testbench monitors writes to this address */
    . += 4;
    _end = .;
}
```

Each test is compiled with:

```bash
riscv-none-elf-gcc \
    -march=rv32im \
    -mabi=ilp32 \
    -static \
    -nostdlib \
    -T verification/riscv-tests/link.ld \
    -I verification/riscv-tests/isa/macros/scalar \
    -I verification/riscv-tests/env/p \
    verification/riscv-tests/isa/rv32ui/<test>.S \
    -o build/riscv-tests/<test>.elf
```

For extension-M tests, replace `rv32ui` with `rv32um`.

A `Makefile` at `verification/riscv-tests/Makefile` automates this for all
tests in the RV32I and RV32M suites and writes ELFs to `build/riscv-tests/`.

---

## Normative Specification

### Tests compiled (RV32I — rv32ui)

`add`, `addi`, `and`, `andi`, `auipc`, `beq`, `bge`, `bgeu`, `blt`, `bltu`,
`bne`, `jal`, `jalr`, `lb`, `lbu`, `lh`, `lhu`, `lui`, `lw`, `or`, `ori`,
`sb`, `sh`, `sll`, `slli`, `slt`, `slti`, `sltiu`, `sltu`, `sra`, `srai`,
`srl`, `srli`, `sub`, `sw`, `xor`, `xori`

### Tests compiled (RV32M — rv32um)

`div`, `divu`, `mul`, `mulh`, `mulhsu`, `mulhu`, `rem`, `remu`

### Output

All ELFs land in `build/riscv-tests/{rv32ui,rv32um}/`. The `.mem` conversion
(ADR 014) is invoked per-test by the cocotb Makefile in `verification/cocotb/common/`.

### Constraints

- The linker script is committed at `verification/riscv-tests/link.ld`.  
- The `riscv-tests` submodule is pinned to a specific commit hash — it is never
  updated silently.  
- No modifications are made to any file inside the submodule itself. All
  project-specific overrides live outside the submodule directory.

---

## Consequences

- Any new test added to the suite requires only adding it to the Makefile
  `TESTS_RV32I` or `TESTS_RV32M` variable; no RTL or linker script change.  
- The `build/riscv-tests/` directory is not committed (`.gitignore`); binaries
  are regenerated from source on each machine.  
- The same ELF-to-.mem pipeline from ADR 014 is reused without modification.