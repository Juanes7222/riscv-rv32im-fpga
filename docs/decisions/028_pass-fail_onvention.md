# ADR 028 - Pass/Fail Convention: tohost Symbol Monitoring in cocotb

**Status:** Accepted (updated 2026-11-12 to match the implemented testbench;
superseded in part by [ADR 032](032_single_cycle_cpi_one_test_layer.md), which
reads the DUT by hierarchy instead of adding top-level ports)  
**Date:** 2026-05-11  
**Depends on:** ADR 012 (tohost mentioned), ADR 027 (linker script defines tohost)

---

## Context

The `riscv-tests` environment (`env/p/`) signals test completion by writing a
value to the `tohost` symbol:

- **Pass:** writes `1` to `tohost`  
- **Fail:** writes `(TESTNUM << 1) | 1` to `tohost`, where `TESTNUM` is the
  index of the failing assertion (always ≥ 3, so the written value is ≥ 3)

After writing `tohost`, the test enters an infinite loop (`j _done`). The
`tohost` write is performed by the trap handler that the boot code installs
at `mtvec`; the test itself executes `ecall` (see ADR 030). The testbench
monitors the data memory write bus for a write to the `tohost` symbol to
determine pass/fail.

The `tohost` symbol lives inside the `.tohost` section that the linker script
places in the data window (ADR 027). Its byte address depends on the size of
each test's `.text` section, so it changes from one ELF to another (for example
`0x6c0` for `add` with the current script, `0x2c0`-range for shorter tests).
The testbench cannot hardcode it; it must read the ELF symbol table.

---

## Decision

The cocotb testbench reads the `tohost` symbol address from the ELF at
testbench startup using the `pyelftools` library. It then monitors the
synchronous data memory write port each clock cycle. When the address matches
`tohost` and `dmwr` is asserted, the testbench captures the written value and
terminates simulation.

pass <--> captured value == 1
fail <--> captured value != 1 (non-zero means TESTNUM assertion failed)
timeout <--> no write to tohost within MAX_CYCLES


`MAX_CYCLES` is a per-test budget, passed to `monitor_tohost`: 200 000 cycles
for the ALU/branch tests, 500 000 for the division corner cases (ADR 031), and
larger values for CoreMark. The budget is a safety margin, not a measurement.

---

## Normative Specification

### Symbol resolution (Python, executed once per test)

```python
from elftools.elf.elffile import ELFFile

def get_tohost_addr(elf_path: str) -> int:
    with open(elf_path, "rb") as f:
        elf = ELFFile(f)
        symtab = elf.get_section_by_name(".symtab")
        sym = symtab.get_symbol_by_name("tohost")
        return sym.entry["st_value"]  # byte address
```

### Monitoring loop (inside cocotb coroutine)

The data-memory address is a **byte** address (ADR 021), so the comparison is
against `tohost_byte_addr` directly, not against a word index:

```python
for _ in range(max_cycles):
    await RisingEdge(dut.clk)
    if (int(dut.dm_wr.value) == 1 and
        int(dut.dm_addr.value) == tohost_byte_addr):
        result = int(dut.dm_wdata.value)
        if result == 1:
            # PASS
        else:
            # FAIL - testnum = result >> 1
# TIMEOUT if loop exhausted
```

### Signal names (top_single_cycle.sv)

| Signal     | Kind    | Width | Meaning                        |
|------------|---------|-------|--------------------------------|
| `clk`      | in      | 1     | processor clock                |
| `rst_n`    | in      | 1     | active-low reset               |
| `dm_wr`    | signal  | 1     | data memory write enable       |
| `dm_addr`  | signal  | 32    | data memory address (byte)     |
| `dm_wdata` | signal  | 32    | data memory write data         |

`dm_wr` is an internal signal of the top. `dm_addr` and `dm_wdata` are internal
aliases (`alu_sum` and `rs2_data`) marked `synthesis keep`; they are **not**
top-level ports. The cocotb monitor reads them through the Icarus hierarchy
(`dut.dm_addr`, `dut.dm_wdata`), which is the approach ADR 032 fixed. Adding
128 pins to the DE1-SoC pinout for debug signals is not required and was
rejected there.

### Testbench template (per-test)

```python
import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock
from .tohost import get_tohost_addr, monitor_tohost

@cocotb.test()
async def test_rv32i_add(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst_n.value = 0
    await Timer(40, units="ns")
    dut.rst_n.value = 1
    result = await monitor_tohost(dut, ELF_PATH, max_cycles=200_000)
    assert result == "pass", f"FAIL: testnum={result}"
```

---

## Consequences

- `pyelftools` is added as a Python dependency (`pip install pyelftools`).  
- `dm_addr` and `dm_wdata` stay internal and are read by hierarchy; no top-level
  ports are added (ADR 032).  
- The same monitoring coroutine is reused unmodified for the pipeline; only the
  DUT module name changes.  
- Timeout failures are reported as a distinct outcome (not as FAIL) so they are
  identifiable in the test log.