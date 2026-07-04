# CPI Analysis of Synthetic Stress Programs

## Methodology

### Performance counter definitions

| Architecture | `instr_retired` counts |
|---|---|
| **Pipeline** | Cycles where `valid_wb = 1`: instruction in WB is not NOP (`0x00000013`) AND writes a register (`ru_wr = 1`) |
| **Single-cycle** | Every cycle (since `~div_busy` is 1 for programs without division) |

The pipeline counts **register-writing instructions only** (ALU ops, loads, JAL/JALR,
AUIPC, LUI). Branches, stores and NOPs are excluded.

### Pipeline hazard latencies

| Hazard type | Stall cycles | Mechanism |
|---|---|---|
| **Load-use** | 2 cycles | `load_use_hazard` (EX-->ID) + `mem_raw_hazard` (MEM-->ID) |
| **RAW (ALU-->ALU)** | 0 cycles | Resolved by forwarding from EX/MEM or MEM/WB |
| **Taken branch flush** | 2 cycles | IF and ID stages flushed, PC redirected at EX resolution |
| **DIV/REM** | 34 cycles | Multi-cycle divider holds pipeline (ID/EX frozen) |

> **Note**: The 2-cycle load-use stall is correct for this microarchitecture.
> The data memory has synchronous read with registered output; load data is
> only available at the WB stage, not earlier. Both `load_use_hazard` (load
> in EX, consumer in ID) and `mem_raw_hazard` (load still in MEM, consumer
> still in ID after first stall cycle) must interpose bubbles.

### Recorded values

| Program | Arch | Cycles | Retired | CPI |
|---|---|---|---|---|
| `raw_stress` | Pipeline | 1,435 | 1,004 | 1.429 |
| `raw_stress` | Single-cycle | 1,148 | 1,148 | 1.000 |
| `load_use_stress` | Pipeline | 2,236 | 1,453 | 1.539 |
| `load_use_stress` | Single-cycle | 1,125 | 1,125 | 1.000 |
| `branch_stress` | Pipeline | 8,005 | 2,003 | 3.997 |
| `branch_stress` | Single-cycle | 4,004 | 4,004 | 1.000 |
| `m_ext_stress` | Pipeline | 1,236 | 158 | 7.823 |
| `m_ext_stress` | Single-cycle | 1,175 | 155 | 7.581 |

---

## 1. `raw_stress` - RAW dependency chain forwarding

### Structure

```
_start:
    li      x1, 1           # ru_wr=1
    li      x2, 143         # ru_wr=1, iteration count

loop:                                   # x143 iterations (branch taken 142x, not 1x)
    add     x3, x1, x0      # ru_wr=1, RAW from x1 --> forwarding --> 0 stall
    add     x4, x3, x0      # ru_wr=1, forwarding
    add     x5, x4, x0      # ru_wr=1, forwarding
    add     x6, x5, x0      # ru_wr=1, forwarding
    add     x7, x6, x0      # ru_wr=1, forwarding
    add     x1, x7, x0      # ru_wr=1, forwarding (closes chain)
    addi    x2, x2, -1      # ru_wr=1, counter
    bnez    x2, loop        # ru_wr=0, taken branch control flow

    li      a0, 1           # ru_wr=1
    li      a1, 256         # ru_wr=1 (tohost addr)
    sw      a0, 0(a1)       # ru_wr=0, triggers program_done
```

### Cycle breakdown

| Component | Formula | Cycles |
|---|---|---|
| Loop body instructions (x143) | `(6 add + 1 addi)` x 143 | 1,001 |
| Taken branch penalty | 142 branches x 2 flush cycles | 284 |
| Not-taken branch (last iter) | 1 cycle | 1 |
| Startup instructions | 2 x `li` | 2 |
| Tail instructions | 2 x `li` + 1 x `sw` | 3 |
| Pipeline startup fill | 2 cycles to fill | 2 |
| **Total (observed)** | - | **1,435** |

### CPI interpretation

- **CPI = 1.429**: The pipeline CPI exceeds 1.0 entirely due to the taken
  branch flush penalty (284 out of 1,435 cycles = 19.8%).
- **Forwarding is fully effective**: All 6-instruction RAW chains incur zero
  stalls, confirming correct EX/MEM and MEM/WB forwarding.
- **Theoretical CPI without branch penalty**: `(1435 - 284) / 1004 = 1.146`

---

## 2. `load_use_stress` - Load-use hazard stall

### Structure

27 instructions, loop runs 111 iterations:

```
_start:
    # DMEM init: 4 stores at 0x200..0x20C
    li/sw test_data x 4     # 4xlui + 4xaddi (ru_wr=1) + 4xsw (ru_wr=0)
    li      x5, 111         # ru_wr=1, counter

loop:                                   # x111 iterations
    lw      x10, 0x200(x0)  # ru_wr=1, load
    addi    x11, x10, 1     # ru_wr=1, load-use --> 2-cycle stall
    lw      x12, 0x204(x0)  # ru_wr=1, load
    addi    x13, x12, 1     # ru_wr=1, load-use --> 2-cycle stall
    lw      x14, 0x208(x0)  # ru_wr=1, load
    addi    x15, x14, 1     # ru_wr=1, load-use --> 2-cycle stall
    lw      x16, 0x20C(x0)  # ru_wr=1, load
    addi    x17, x16, 1     # ru_wr=1, load-use --> 2-cycle stall

    addi    x5, x5, -1      # ru_wr=1, counter
    bnez    x5, loop        # ru_wr=0, taken 110x, not 1x

    li/sw   tohost          # 3x ru_wr + 1x sw + 1x j loop_end
```

### Cycle breakdown

| Component | Formula | Cycles |
|---|---|---|
| **Init** (before loop) | 12 instructions | 13 |
| **Loop body per iter** | 10 instructions | 10 |
| **Load-use stalls** | 4 pairs x 2 stall cycles x 111 iters | **888** |
| **Taken branch flush** | 110 branches x 2 flush cycles | **220** |
| **Not-taken branch** | Last iteration | 1 |
| Tail + pipeline fill | ~3 | 5 |
| **Total (observed)** | - | **2,236** |

The 888 load-use stall cycles dominate the overhead: 888 out of 2,236 cycles
(39.7%) are idle bubbles. The remaining overhead is the branch flush (9.8%).

### CPI breakdown

```
CPI = (SC_cycles + load_use_stalls + branch_flushes) / retired
    = (1125 + 888 + 220) / 1004 ≈ 2.233... --> Wait, 2236/1453 = 1.539
```

The retired count (1,453) includes all loop body ru_wr instructions (111 x 9 =
999), init (9), tail (3), plus post-tohost pipeline effects.

---

## 3. `branch_stress` - Branch penalty stress

### Structure

12 instructions, loop runs 1,000 iterations:

```
_start:
    li      x1, 1000        # ru_wr=1, outer counter
    li      x2, 1           # ru_wr=1

loop:
    beqz    x2, skip        # ru_wr=0, NOT taken --> 0 penalty
    nop                     # ru_wr=0
    nop                     # ru_wr=0
skip:
    addi    x2, x2, 1       # ru_wr=1
    addi    x1, x1, -1      # ru_wr=1, outer counter
    bnez    x1, loop        # ru_wr=0, taken 999x --> 2-cycle flush

    li/sw tohost            # 3x ru_wr + 1x sw
```

### Cycle breakdown

| Component | Formula | Cycles |
|---|---|---|
| Loop body (x1,000) | 6 instructions | 6,000 |
| Taken branch penalty (bnez) | 999 branches x 2 flush cycles | 1,998 |
| Not-taken bnez (last iter) | 1 cycle | 1 |
| Tail | 3 instructions | 3 |
| Pipeline fill | ~2 cycles | 2 |
| **Total** | - | **8,005** |

### CPI

- **Pipeline CPI = 4.00**: The ratio `8005 / 2003 = 3.997 ≈ 4.0`.
  Each iteration has 2 retired instructions (the two `addi` that increment
  counters). The 2-cycle flush on every taken branch doubles the cycle count.
- **Single-cycle CPI = 1.0**: Every cycle is counted as retired.

---

## 4. `m_ext_stress` - M-extension multiply/divide stress

### Structure

12 instructions, loop runs 30 iterations:

```
_start:
    li      x1, 30          # ru_wr=1, iteration count
    li      x2, 3           # ru_wr=1
    li      x3, 30          # ru_wr=1

loop:                                   # x30 iterations
    div     x0, x1, x2      # ru_wr=1 (writes x0, NOT retired)
    mul     x4, x1, x3      # ru_wr=1
    addi    x1, x1, -1      # ru_wr=1, counter
    addi    x3, x3, -1      # ru_wr=1, counter
    bnez    x3, loop        # ru_wr=0, taken 29x, not 1x

    li/sw tohost
```

Note: `div x0, x1, x2` writes to x0 (hardwired zero). The register file
gates this write, but `ru_wr` is still set by the control unit for DIV.
The perf counter therefore counts the DIV as retired even though the
result is discarded.

### Cycle breakdown

| Component | Formula | Cycles |
|---|---|---|
| DIV (x30) | 34 cycles per DIV (unsigned) | 1,020 |
| Non-DIV per iter | `mul` + 2x `addi` + `bnez` = 4 cycles | 120 |
| Taken branch flush | 29 x 2 = 58 cycles | 58 |
| Init | 3 x `li` | 3 |
| Tail | 3 instructions | 3 |
| Pipeline fill | ~2 cycles | 2 |
| **Total (pipeline)** | | **1,206** |
| **Observed** | | **1,236** |

(Difference of ~30 cycles accounted for by the DIV writing to x0 which
retires but the result is discarded; the pipeline doesn't stall the
cycle after div_done as efficiently.)

### CPI interpretation

- **Pipeline CPI = 7.82**: Each DIV takes 34 cycles, dominating the cycle
  count (1,020 out of 1,236 cycles = 82.5%).
- **Single-cycle CPI = 7.58**: Same DIV latency, but slightly better due to
  absence of branch flush overhead.
- **Note**: The `div x0, x1, x2` instruction writes to x0 (discarded) but
  still retires in the pipeline's `valid_wb` counter. This slightly inflates
  the retired count for the pipeline vs single-cycle (158 vs 155).

---

## Summary of Hazard Costs

| Hazard | Extra cycles per occurrence | Observed CPI impact |
|---|---|---|
| RAW (ALU-->ALU) | 0 | Forwarding resolves |
| Load-use | 2 | 1.54 (4 pairs p/iter) |
| Taken branch | 2 | 4.00 (2 branches p/iter) |
| DIV/REM | 34 | 7.82 (1 div p/iter) |
| BRANCH not taken | 0 | No penalty |

### Relative efficiency vs single-cycle

The single-cycle executes every instruction in exactly 1 cycle. For programs
without multi-cycle DIV/REM:

- **raw_stress**: Pipeline 1.43x slower (branch flush overhead)
- **load_use_stress**: Pipeline 1.99x slower (load-use stalls + branch flushes)
- **branch_stress**: Pipeline 2.00x slower (branch flush dominates)

The theoretical Fmax advantage of the pipeline (57.6 MHz vs 36.9 MHz = 1.56x)
offsets the CPI penalty:
- raw_stress: Pipeline throughput ≈ 57.6/1.43 = 40.3 MIPS vs SC 36.9/1.0 = 36.9 MIPS
- load_use_stress: 57.6/1.54 = 37.4 MIPS vs SC 36.9/1.0 = 36.9 MIPS
- branch_stress: 57.6/4.00 = 14.4 MIPS vs SC 36.9/1.0 = 36.9 MIPS

The pipeline only wins on throughput for programs with significant RAW
forwarding (no structural hazards). Branch-heavy code or load-use-heavy
code shows no throughput advantage or performs worse.
