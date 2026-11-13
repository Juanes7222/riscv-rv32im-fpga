# ADR 057 - Pipeline frontend without an IF/ID register: one-cycle branch penalty

**Status:** Accepted
**Date:** 2026-11-12
**Changes:** the frontend contract of ADR 038, 039, 040 and 043 (they assume an
explicit `if_id_register`). Those documents stay as the record of their own
decisions; this ADR is the description of the frontend they now run on.
**Depends on:** ADR 006 (JALR LSB masking), ADR 037 (bubble), ADR 046 (registered
IMEM read), ADR 053 (redirect priority), ADR 056 (WB-to-ID forwarding)

---

## Context

The first pipeline version had a dedicated `rtl/pipeline/if_id_register.sv`
between the instruction memory and the ID stage. The registered read of the
single-cycle instruction memory (ADR 046) showed that the memory's own output
register already is the IF/ID boundary: the word read with the address of PC+4 at
the end of cycle N is available in cycle N+1, which is exactly the instruction ID
must decode. A second register behind it only adds a cycle to every fetch.

The module is still in `rtl/pipeline/` and still listed in the pipeline
`Makefile`, but `top_pipeline.sv` does not instantiate it. The frontend described
here is the one that runs.

## Decision

### 1. The IF/ID boundary is the IMEM output register.

```systemverilog
// rtl/pipeline/instruction_memory_pipe.sv
always_ff @(posedge clk)
    if (fetch_en) mem_q <= mem[next_pc[ADDR_BITS+1:2]];
assign instruction = oob_q ? 32'h00000013 : mem_q;

// rtl/pipeline/top_pipeline.sv
always_ff @(posedge clk) begin
    if (rst) begin
        fetch_valid <= 1'b0;
        id_pc       <= '0;
    end else if (!pipe_stall) begin
        fetch_valid <= 1'b1;
        id_pc       <= imem_addr;
    end
end

assign id_instruction = fetch_valid ? if_instruction : 32'h00000013;
```

`id_pc` is registered with the same address that was presented to the memory, so
`id_pc` and `if_instruction` always describe the same word. There is no
`if_id_register` between them.

### 2. A taken branch costs one cycle, not two.

The redirect is computed in EX (ADR 038's policy is unchanged) and drives
`next_if_pc` in the same cycle, so the address presented to the memory on the
next clock is already the target. The only wasted work is the wrong-path word
that sat in ID when the branch resolved: one flush, one bubble. This is the
figure `top_pipeline.sv` documents and `docs/architecture/pipeline.md` records as
"CPI = 2 (one flush penalty)".

`if_id_register`'s two-cycle penalty — still described in ADR 038's consequences
— belonged to the version with the extra register and no longer applies.

### 3. Out-of-range fetches become the canonical bubble.

The memories return `32'h00000013` for an address outside the array, and
`id_instruction` is forced to the same word while `fetch_valid` is low. Both
paths use the bubble of ADR 037, so a flush or a reset can never inject an
instruction that writes state.

### 4. Why the unused module stays in the tree.

`if_id_register.sv` is retained (and still compiled by the pipeline Makefile) as
the reference implementation of the removed stage. Deleting it would also change
the project file list of a branch that is under measurement; that cleanup is
deferred. It must not be re-instantiated without reopening this ADR.

## Consequences

- One less pipeline register in the fetch path: a taken branch costs 1 cycle
  instead of 2, and the loop CPI of the pipeline improves by that bubble.
- The IF/ID validity is `fetch_valid`, not a register's `valid` bit. Everything
  that used to read `if_id_register.valid` reads `fetch_valid` (ADR 053's valid
  chain starts at `id_valid = fetch_valid`).
- `docs/architecture/pipeline.md` describes the stage list without the extra
  register.
- ADR 038, 039, 040 and 043 describe the pipeline as if `if_id_register` existed;
  read them together with this ADR.
- The pipeline Makefile still lists `if_id_register.sv` in `VERILOG_SOURCES`.
  Compiling an unused module is harmless; the file must not be dropped from the
  list while it is the reference implementation.
