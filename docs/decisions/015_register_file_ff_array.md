# ADR 014 — Register File: FF Array Implementation

**Status:** Accepted  
**Date:** 2026-05-02

## Context

The register file requires three simultaneous ports: two asynchronous read
ports (rs1, rs2) and one synchronous write port (rd). On Cyclone V, embedded
memory (M10K) blocks support at most two ports in true dual-port configuration,
neither of which naturally provides three independent ports with asynchronous
read semantics. A register file implementation must choose between a flip-flop
array and a multi-block M10K arrangement.

## Decision

The register file is implemented as a **flip-flop array**:

```systemverilog
logic [31:0] regs [0:31];
```

Read ports are implemented as combinational `assign` statements outside any
`always` block. The write port is implemented in a dedicated `always_ff` block.
The two blocks share no combinational paths, which guarantees read-before-write
semantics regardless of Quartus synthesis settings.

## Rationale

**1. Three-port requirement rules out single M10K blocks.**  
A single M10K block in true dual-port mode supports two ports, each
configurable as read or write. Supporting two simultaneous reads and one
simultaneous write requires either two M10K blocks written in parallel (one
per read port) or a three-port custom configuration not available natively in
Cyclone V primitives. The added complexity provides no benefit for a 32-word
memory.

**2. Resource cost is negligible.**  
32 registers × 32 bits = 1024 flip-flops. The Cyclone V 5CSEMA5F31C6 has
approximately 41 000 logic registers. The register file consumes roughly 2.5%
of available flip-flops, well within budget for both microarchitectures
simultaneously.

**3. Asynchronous read is natural for FF arrays.**  
Combinational read from a flip-flop array infers correctly and without special
configuration in Quartus. M10K asynchronous read requires explicit megafunction
configuration and consumes more routing resources than an equivalent FF array
at this depth.

**4. Read-before-write is unambiguous.**  
Separating the read logic (`assign` statements) from the write logic
(`always_ff`) ensures that Quartus never infers a read-during-write behavior
other than read-before-write. If both were described in the same `always`
block, the synthesizer could infer new-data or don't-care semantics depending
on the description style and tool version.

## Implementation Contract

```systemverilog
// Read ports — purely combinational, outside any always block
assign rs1_data = (rs1_addr == 5'b0) ? 32'b0 : regs[rs1_addr];
assign rs2_data = (rs2_addr == 5'b0) ? 32'b0 : regs[rs2_addr];

// Write port — synchronous, x0 protected by gate on write address
always_ff @(posedge clk) begin
    if (!rst_n) begin
        for (int i = 1; i < 32; i++) regs[i] <= 32'b0;
        // regs[0] is never written; its value is irrelevant (read always returns 0)
    end else if (wr_en && rd_addr != 5'b0) begin
        regs[rd_addr] <= rd_data;
    end
end
```

**x0 protection is implemented at the write gate**, not at the read output.
Writing to `rd_addr == 0` is silently discarded. This means `regs[0]` never
holds a non-zero value (after reset), which is the formally correct
interpretation of the RISC-V specification: x0 is a constant-zero register,
not a writable register with a zero-forcing output.

## Consequences

- `register_file.sv` uses no M10K blocks. All 1024 storage bits are mapped
  to logic registers (FFs) by Quartus.
- Read outputs `rs1_data` and `rs2_data` are valid combinationally within the
  same clock cycle that `rs1_addr` and `rs2_addr` are presented. There is no
  clock edge required.
- Read-before-write: if `rs1_addr == rd_addr` and `wr_en == 1` in the same
  cycle, `rs1_data` reflects the value of `regs[rd_addr]` before the write.
  The new value is visible on the next cycle. The forwarding unit in the
  pipelined implementation resolves all same-cycle RAW hazards.
- The `for` loop in the reset branch synthesizes to 31 parallel FF reset
  connections. Quartus handles this correctly; it does not infer sequential
  behavior from a synthesizable `for` loop inside `always_ff`.
- `regs[0]` is included in the array declaration for address uniformity but
  is never driven after reset. Its synthesized value is permanently 0.
