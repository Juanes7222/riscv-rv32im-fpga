# ADR 056 - WB-to-ID forwarding and MEM-RAW restricted to loads

**Status:** Accepted
**Date:** 2026-11-12
**Supersedes:** ADR 040 (MEM-RAW/WB-RAW stalls) and ADR 041 (producer three-plus
cycles ahead). Those two were marked "superseded by commit `06260fc`", which the
index does not accept as a supersession; this ADR is the formal replacement.
**Depends on:** ADR 037 (bubble), ADR 039 (pipeline bug fixes), ADR 043
(load-use on a branch), ADR 053 (redirect priority and valid retirement)

---

## Context

ADR 040 and ADR 041 document a forwarding race in the five-stage pipeline. The
register file is read in ID and written at the end of WB, so a producer in MEM or
WB is invisible to a consumer in ID in the same cycle. The original fix stalled
the pipeline (WB-RAW and MEM-RAW), which serialised long dependency chains and,
in the pattern of `riscv-tests`' trap vector, deadlocked: each stalled copy kept
triggering the stall against the copy behind it.

That fix was replaced by the change recorded here. ADR 040 and 041 describe the
problem correctly but their decision is no longer the implementation, and they
pointed at a commit instead of an ADR. This ADR is the decision of record.

## Decision

### 1. No WB-RAW stall. WB-to-ID forwarding instead.

When the producer is in WB in the same cycle in which the consumer is decoded,
the value is taken directly from the WB stage and captured into ID/EX:

```systemverilog
// rtl/pipeline/top_pipeline.sv
always_comb begin
    id_rs1_data_wb_fwd = (wb_ru_wr && (wb_rd_addr != 5'b0) && (wb_rd_addr == id_rs1_addr))
                          ? wb_rd_data : id_rs1_data;
    id_rs2_data_wb_fwd = (wb_ru_wr && (wb_rd_addr != 5'b0) && (wb_rd_addr == id_rs2_addr))
                          ? wb_rd_data : id_rs2_data;
end
```

The register file keeps writing on the clock edge; the forwarding only bypasses
the read, which is what makes the same-cycle dependency legal. `x0` is excluded
by the `wb_rd_addr != 0` term, so a write to x0 can never be forwarded.

### 2. MEM-RAW stalls only for loads.

A producer in MEM only needs a stall if its result is not available until the end
of MEM, which is true for a load (`WB_MEM`) and false for an ALU operation
(`WB_EX`, already forwarded out of EX/MEM). The detector therefore asserts
`mem_raw_hazard` only when the instruction in MEM is a load:

```systemverilog
// rtl/pipeline/hazard_detection.sv
mem_raw_hazard = mem_ru_wr &&
                 (mem_ru_data_wr_src == WB_MEM) &&   // load: data arrives at the end of MEM
                 (mem_rd_addr != 5'b0) &&
                 ((mem_rd_addr == id_rs1_addr) || (mem_rd_addr == id_rs2_addr));
```

This is the change that removes the deadlock of ADR 041: an arithmetic
instruction in MEM no longer stalls the consumer in ID, so the stalled copy and
its successor cannot ping-pong forever.

### 3. The stall output is the OR of the remaining causes.

`stall = load_use_hazard || mem_raw_hazard || div_busy` (ADR 043 adds the
load-use-on-branch flush; ADR 053 makes `pipe_stall = (stall && !flush) ||
step_hold_effective`). The WB-RAW term is gone.

## Consequences

- Dependency chains of arithmetic instructions no longer stall: a producer in WB
  and a consumer in ID execute back to back.
- Only a load followed immediately by its consumer costs a bubble (load-use), and
  a load whose consumer is one stage further also costs one (MEM-RAW), which is
  the minimum for a memory whose data arrives at the end of MEM.
- The trap vector pattern of ADR 041 (CSR read followed by three comparisons)
  runs without deadlock, which is what made the riscv-tests pass on the pipeline.
- `hazard_detection.sv` no longer has a WB-RAW input path; the
  `wb_rd_addr`/`wb_rd_data` signals feed the ID forwarding muxes instead.
- The pipeline's CPI includes one bubble per load-use pair; this is the expected
  cost and is visible in `test_pipeline_cpi`.
- ADR 040 and ADR 041 stay in the tree as the record of the problem; they must
  not be used as the description of the implementation.
