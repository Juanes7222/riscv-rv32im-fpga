# ADR 028 — Pass/Fail Convention: tohost Symbol Monitoring in cocotb

**Status:** Accepted  
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

The `tohost` symbol address is fixed by the linker script (ADR 027). Its byte
address equals `_end - 4`, but the exact value depends on the size of each
test's `.text` section. The testbench cannot hardcode this address; it must
read it from the ELF symbol table.

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


`MAX_CYCLES` is set to `200_000` cycles. This is sufficient for the longest
riscv-tests binary (division corner cases) at the worst-case simulated
frequency, with a 10× safety margin.

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

```python
tohost_word_addr = tohost_byte_addr >> 2  # word-addressed DMEM (ADR 021)

for _ in range(MAX_CYCLES):
    await RisingEdge(dut.clk)
    if (dut.dmwr.value == 1 and
        dut.dm_addr.value == tohost_word_addr):
        result = int(dut.dm_wdata.value)
        if result == 1:
            # PASS
        else:
            # FAIL — testnum = result >> 1
# TIMEOUT if loop exhausted
```

### Signal names (top_single_cycle.sv interface)

| Signal     | Direction | Width | Meaning                        |
|------------|-----------|-------|--------------------------------|
| `clk`      | in        | 1     | processor clock                |
| `rstn`     | in        | 1     | active-low reset               |
| `dmwr`     | out       | 1     | data memory write enable       |
| `dm_addr`  | out       | 32    | data memory address (byte)     |
| `dm_wdata` | out       | 32    | data memory write data         |

> **Note:** if `top_single_cycle.sv` does not currently expose `dm_addr` and
> `dm_wdata` as top-level output ports, they must be added. This is the only
> RTL change required before cocotb verification can begin. It does not affect
> synthesis (Quartus will leave unconnected outputs unrouted without error).

### Testbench template (per-test)

```python
import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock
from .tohost import get_tohost_addr, monitor_tohost

@cocotb.test()
async def test_rv32i_add(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rstn.value = 0
    await Timer(40, units="ns")
    dut.rstn.value = 1
    result = await monitor_tohost(dut, ELF_PATH, MAX_CYCLES=200_000)
    assert result == "pass", f"FAIL: testnum={result}"
```

---

## Consequences

- `pyelftools` is added as a Python dependency (`pip install pyelftools`).  
- `top_single_cycle.sv` must expose `dm_addr` and `dm_wdata` as outputs (one
  RTL change, zero synthesis impact).  
- The same monitoring coroutine is reused unmodified for the pipeline; only the
  DUT module name changes.  
- Timeout failures are reported as a distinct outcome (not as FAIL) so they are
  identifiable in the test log.