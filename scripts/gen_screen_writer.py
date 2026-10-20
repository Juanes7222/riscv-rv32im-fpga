#!/usr/bin/env python3
"""
gen_screen_writer.py - Auto-generates screen_writer SystemVerilog from
fields.json produced by gen_screen_mif.py.

The generated module uses character-level round-robin writes:
each clock cycle updates exactly ONE character cell.  Total refresh
= sum(widths) cycles.  At 50 MHz, even 200 chars x 20 ns = 4 us,
which is ~4000x faster than a VGA frame (16.7 ms).

Every displayed value is first captured into a snapshot register bank.
The bank is loaded once per sweep, so all characters of a sweep -- and
therefore every field on screen -- describe a single machine state.
Sampling the live signals per character would assemble a multi-digit
field from as many different instants as it has characters.

The characters are produced by two round-robin groups that alternate:
the processor fields and the register table.  A single group with all the
characters would need a multiplexer with hundreds of inputs, and its delay
does not fit in the 13.5 ns period of the 74.25 MHz pixel clock.
"""

import argparse
import json
import re
import sys
from collections import Counter
from typing import List, Set, Tuple
from pathlib import Path

# The register table is not fed by 32 separate ports: the whole register file
# crosses as one packed bus, x0 in [31:0] ... x31 in [1023:992].
REG_BUS = 'reg_values'
REG_COUNT = 32
REG_BUS_WIDTH = REG_COUNT * 32

# Maximum number of characters of one round-robin group.  The character
# multiplexer of a group is the critical path of the pixel clock domain, and
# its delay grows with the number of sources it selects from, so the groups
# are kept small.
MAX_GROUP_CHARS = 128

# The instruction register of every pipeline stage, and the prefix of the
# wire that tells whether the stage holds a real instruction.
STAGE_INSTRUCTIONS = (
    ('if', 'if_instruction'),
    ('id', 'id_instruction'),
    ('ex', 'ex_instruction'),
    ('mem', 'mem_instruction'),
    ('wb', 'wb_instruction'),
)

# The canonical bubble of the pipeline: it occupies a stage without doing
# anything, so it does not light the stage up.
BUBBLE_INSTRUCTION = 0x00000013

# The opcodes of the instructions that access the data memory.
LOAD_OPCODE = 0b0000011
STORE_OPCODE = 0b0100011


def is_reg_field(name: str) -> bool:
    return re.fullmatch(r'x\d+', name) is not None


def reg_index(name: str) -> int:
    return int(name[1:])


def attr_expression(f: dict, snapshots: Set[str], local_wires: Set[str]) -> str:
    """The attribute expression of a field.

    A constant when the field has no hot signal, a 2:1 mux on the snapshot
    of that signal otherwise.  The signal is read from the snapshot bank, so
    the colour describes the value that is on screen.  The character
    multiplexer is not affected."""
    attr = f['attr']
    fg, bg = attr['fg'], attr['bg']
    hot = f.get('hot')
    if not hot:
        return f"8'h{bg << 4 | fg:02X}"
    signal = hot['signal']
    if signal in snapshots:
        source = f"snap_{signal}"
    elif signal in local_wires:
        source = signal
    else:
        raise ValueError(
            f"Field '{f['name']}' names the hot signal '{signal}', which this "
            'design neither samples nor derives.'
        )
    return (f"({source} ? "
            f"8'h{hot['bg'] << 4 | hot['fg']:02X} : "
            f"8'h{bg << 4 | fg:02X})")


def format_wires(specs: List[Tuple[str, List[str]]]) -> List[str]:
    """Format a block of wire declarations with the assignment signs aligned.

    Every specification is a name and the parts of its expression; the last
    part is closed with a semicolon."""
    if not specs:
        return []
    width = max(len(name) for name, _ in specs)
    lines = []
    for name, expr in specs:
        head = f"    wire {name.ljust(width)} = "
        indent = ' ' * (len(head) + 1)
        parts = list(expr)
        parts[-1] += ';'
        lines.append(head + parts[0])
        lines.extend(indent + part for part in parts[1:])
    return lines


def derived_wires(snapshots: Set[str]) -> List[List[Tuple[str, List[str]]]]:
    """The derived wires of this design, as blocks of declarations.

    Only the signals whose snapshot exists in this design are emitted, so a
    writer never references a signal it does not have."""
    stages: List[Tuple[str, List[str]]] = []
    bubble = f"32'h{BUBBLE_INSTRUCTION:08X}"
    for stage, instr in STAGE_INSTRUCTIONS:
        if instr in snapshots:
            stages.append((f'stage_{stage}_active', [
                f"(snap_{instr} != 32'h00000000) &&",
                f"(snap_{instr} != {bubble})",
            ]))
    if not stages and 'instruction' in snapshots:
        # The single-cycle design has no pipeline: the instruction in flight
        # is the one of the only stage.
        stages.append(('stage_active', [
            "(snap_instruction != 32'h00000000) &&",
            f"(snap_instruction != {bubble})",
        ]))

    memory: List[Tuple[str, List[str]]] = []
    mem_instr = 'mem_instruction' if 'mem_instruction' in snapshots else 'instruction'
    if mem_instr in snapshots:
        memory.append(('mem_access', [
            f"(snap_{mem_instr}[6:0] == 7'b{LOAD_OPCODE:07b}) ||",
            f"(snap_{mem_instr}[6:0] == 7'b{STORE_OPCODE:07b})",
        ]))
    if 'dm_wr' in snapshots:
        memory.append(('mem_write_access', ['snap_dm_wr']))
    if any(name == 'mem_access' for name, _ in memory) and \
            any(name == 'mem_write_access' for name, _ in memory):
        memory.append(('mem_read_access', ['mem_access && !mem_write_access']))

    return [block for block in (stages, memory) if block]


def build_group(gname: str, gfields: list, snapshots: Set[str],
                local_wires: Set[str]) -> dict:
    """Build the character list, the address map and the case block of a group."""
    # A signal may feed more than one slot; the address constants then need
    # distinct names.
    name_count = Counter(f['name'] for f in gfields)

    def addr_ident(f: dict) -> str:
        name = f['name'].upper()
        if name_count[f['name']] > 1:
            return f"ADDR_{name}_{f['start_address']}"
        return f"ADDR_{name}"

    # Every character of a field shares its attribute.
    attrs = {f['name']: attr_expression(f, snapshots, local_wires) for f in gfields}

    chars = []
    for f in gfields:
        width = f['width']
        fmt = f['fmt']
        bits = f['signal_bits']
        for pos in range(width):
            if fmt == 'hex':
                nibble = width - 1 - pos
                chars.append((f, pos, nibble, 'hex'))
            else:
                bit = width - 1 - pos
                chars.append((f, pos, bit, 'bin'))

    params = '\n'.join(
        f"    localparam logic [12:0] {addr_ident(f)} = 13'd{f['start_address']};"
        for f in gfields
    )

    cases = []
    for i, (f, pos, idx, fmt) in enumerate(chars):
        name = f['name']
        bits = f['signal_bits']
        addr = f"{addr_ident(f)} + 13'd{pos}"
        if is_reg_field(name):
            src = f"snap_{REG_BUS}[{32 * reg_index(name)} +: 32]"
        else:
            src = f"snap_{name}"
        if fmt == 'hex':
            # For signals narrower than the display width, pad with '0' on the left
            # idx is the nibble from MSB to LSB
            if bits > (idx * 4):
                data_expr = f"hex_digit({src}, {idx})"
            else:
                data_expr = "8'h30"  # '0'
        else:
            if idx < bits:
                data_expr = f"bin_digit({src}, {idx})"
            else:
                data_expr = "8'h30"  # '0'

        cases.append(
            f"            {i}: begin wr_en = 1'b1; wr_addr = {addr}; "
            f"wr_data = {data_expr}; wr_attr = {attrs[name]}; end"
        )

    # Snapshot entries of this group: (register name, source signal)
    if gname == 'REGS':
        snap = [(REG_BUS, REG_BUS)]
    else:
        seen = []
        for f in gfields:
            if not is_reg_field(f['name']) and f['name'] not in seen:
                seen.append(f['name'])
        snap = [(n, n) for n in seen]

    return {
        'name': gname,
        'fields': gfields,
        'params': params,
        'cases': '\n'.join(cases),
        'n': len(chars),
        'ctr_w': (len(chars) - 1).bit_length() if len(chars) > 1 else 1,
        'snap': snap,
    }


def chunk_fields(gfields: list, max_chars: int) -> List[list]:
    """Split the fields into groups of at most max_chars characters.

    A field is never split: all its characters belong to the same group, so
    the group can be swept independently."""
    chunks = []
    current = []
    total = 0
    for f in gfields:
        if current and total + f['width'] > max_chars:
            chunks.append(current)
            current = []
            total = 0
        current.append(f)
        total += f['width']
    if current:
        chunks.append(current)
    return chunks


def generate_rtl(fields: list, mode: str) -> str:
    """Produce the SystemVerilog source for the screen writer."""

    # The memory tables are static content of the framebuffer.
    def is_table_field(f: dict) -> bool:
        return (f['name'].startswith('data_memory_') or
                f['name'].startswith('prog._memory_'))

    proc_fields = [f for f in fields
                   if not is_reg_field(f['name']) and not is_table_field(f)]
    reg_fields = [f for f in fields if is_reg_field(f['name'])]

    # Input port list: the union of the groups
    port_names = sorted(set(f['name'] for f in proc_fields))
    port_widths = {f['name']: f['signal_bits'] for f in proc_fields}
    if reg_fields:
        port_names.append(REG_BUS)
        port_widths[REG_BUS] = REG_BUS_WIDTH
    snapshots = set(port_names)

    # The derived wires the attribute expressions may reference.
    wires = derived_wires(snapshots)
    local_wires = {name for block in wires for name, _ in block}

    # One group per set of fields, each group small enough for its character
    # multiplexer to fit in the pixel clock period.  The register table is a
    # group of its own: it is written in two pipeline stages, see below.
    groups = []
    for i, chunk in enumerate(chunk_fields(proc_fields, MAX_GROUP_CHARS)):
        g = build_group(f'PROC{i}' if i else 'PROC', chunk, snapshots, local_wires)
        if g['n'] > 0:
            groups.append(g)
    if reg_fields:
        groups.append(build_group('REGS', reg_fields, snapshots, local_wires))

    input_ports = '\n'.join(
        f"    input logic [{port_widths[n]-1}:0] {n},"
        for n in port_names
    )

    # Snapshot register bank: one register per sampled signal
    snap_decls = '\n'.join(
        f"    logic [{port_widths[n]-1}:0] snap_{n};"
        for n in port_names
    )
    snap_reset = '\n'.join(
        f"            snap_{n} <= '0;"
        for n in port_names
    )

    # Per group: index constant, counter, case block, snapshot load.
    # The register group is special: its 256 characters are written in two
    # pipeline stages, because a multiplexer over 256 sources is too deep for
    # the pixel clock.  Stage 1 selects the register row, stage 2 the
    # character inside the row.
    group_consts = []
    counter_decls = []
    counter_fsm = []
    case_blocks = []
    total_chars = 0
    reg_group = None

    for idx, g in enumerate(groups):
        gname = g['name']
        lower = gname.lower()
        total_chars += g['n']

        group_consts.append(f"    localparam int GRP_{gname} = {idx};")
        counter_decls.append(
            f"    localparam int N_{gname} = {g['n']};\n"
            f"    localparam int CTR_{gname}_W = {g['ctr_w']};\n"
            f"    logic [CTR_{gname}_W-1:0] ctr_{lower};"
        )

        load = '\n'.join(
            f"                    snap_{src} <= {src};"
            for _, src in g['snap']
        )

        if gname == 'REGS':
            reg_group = g
            counter_fsm.append(f"""                GRP_{gname}: begin
                    ctr_{lower} <= (ctr_{lower} == N_{gname} - 1) ? '0 : ctr_{lower} + 1'b1;
                    // Load the bank at the end of a sweep, so the next sweep
                    // renders every character from the same captured instant.
                    if (ctr_{lower} == N_{gname} - 1) begin
{load}
                    end
                    // Stage 1: select the register row of this character.
                    reg_value <= snap_{REG_BUS}[32*ctr_{lower}[7:3] +: 32];
                    reg_addr  <= REG_ADDR[13*ctr_{lower}[7:3] +: 13];
                    reg_col   <= ctr_{lower}[2:0];
                end""")
            case_blocks.append(f"""            GRP_{gname}: begin
                // Stage 2: the character inside the row selected by stage 1.
                wr_en   = 1'b1;
                wr_addr = reg_addr + {{10'd0, reg_col}};
                wr_data = hex_digit(reg_value, 7 - reg_col);
            end""")
        else:
            counter_fsm.append(f"""                GRP_{gname}: begin
                    ctr_{lower} <= (ctr_{lower} == N_{gname} - 1) ? '0 : ctr_{lower} + 1'b1;
                    // Load the bank at the end of a sweep, so the next sweep
                    // renders every character from the same captured instant.
                    if (ctr_{lower} == N_{gname} - 1) begin
{load}
                    end
                end""")
            case_blocks.append(f"""            GRP_{gname}: begin
                unique case (ctr_{lower})
{g['cases']}
                    default: ;  // no write
                endcase
            end""")

    # Register table: base address of every row, packed so that the row can
    # be selected with a variable part-select.
    reg_addr_list = []
    for f in sorted(reg_fields, key=lambda f: reg_index(f['name'])):
        reg_addr_list.append(f"13'd{f['start_address']}")
    reg_addr_array = ', '.join(reversed(reg_addr_list))

    n_groups = len(groups)
    grp_w = max(1, (n_groups - 1).bit_length())
    ctr_resets = '\n'.join(
        f"            ctr_{g['name'].lower()} <= '0;" for g in groups
    )

    derived = '\n'.join('\n'.join(format_wires(block)) for block in wires)
    derived_block = f"{derived}\n" if derived else ''

    sv = f'''// screen_writer_{mode} - auto-generated by gen_screen_writer.py
// Character-level round-robin, {total_chars} characters split in {n_groups}
// alternating groups.  Displayed values come from a snapshot bank loaded
// once per sweep.

module screen_writer_{mode} (
    input logic        clk,
    input logic        rst_n,

    // Processor signals (all values to be displayed)
{input_ports}

    // Video memory port (write-only, processor clock domain)
    output logic        vmem_wr_en,
    output logic [12:0] vmem_wr_addr,
    output logic [15:0] vmem_wr_data
);

    // Field address map (from fields.json)
{chr(10).join(g['params'] for g in groups)}

    // The groups rotate: one group is written per cycle.
{chr(10).join(group_consts)}

    localparam int N_GROUPS = {n_groups};
    localparam int GRP_W    = {grp_w};
    localparam int N_CHARS  = {total_chars};

{chr(10).join(counter_decls)}

    logic [GRP_W-1:0] grp_ctr;

    // Register table, stage 1: the row of the character being written.
    localparam logic [{REG_COUNT * 13 - 1}:0] REG_ADDR = {{{reg_addr_array}}};
    logic [31:0] reg_value;
    logic [12:0] reg_addr;
    logic [2:0]  reg_col;

    // Snapshot bank - the whole screen is rendered from one instant
{snap_decls}

    // Derived signals used by the attribute expressions.
{derived_block}
    // Helper functions: value --> ASCII
    function automatic [7:0] hex_digit (
        input logic [63:0] value,
        input int          nibble
    );
        logic [63:0] shifted;
        logic [3:0]  d;
        shifted = value >> (nibble * 4);
        d = shifted[3:0];
        hex_digit = (d < 4'd10) ? (8'd48 + d) : (8'd55 + d);  // '0'-'9', 'A'-'F'
    endfunction

    function automatic [7:0] bin_digit (
        input logic [63:0] value,
        input int          bit_idx
    );
        logic [63:0] shifted;
        shifted = value >> bit_idx;
        bin_digit = 8'd48 + shifted[0];  // '0' or '1'
    endfunction

    // Round-robin FSM - one char per cycle, groups alternate
    logic        wr_en;
    logic [12:0] wr_addr;
    logic [7:0]  wr_data;
    logic [7:0]  wr_attr;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            grp_ctr <= '0;
            reg_value <= '0;
            reg_addr  <= '0;
            reg_col   <= '0;
{snap_reset}
{ctr_resets}
        end else begin
            grp_ctr <= (grp_ctr == N_GROUPS - 1) ? '0 : grp_ctr + 1'b1;
            case (grp_ctr)
{chr(10).join(counter_fsm)}
                default: ;  // no write
            endcase
        end
    end

    always_comb begin
        // Default: no write
        wr_en   = 1'b0;
        wr_addr = '0;
        wr_data = 8'h20;  // space
        wr_attr = 8'h09;  // body colour

        case (grp_ctr)
{chr(10).join(case_blocks)}
            default: ;  // no write
        endcase
    end

    assign vmem_wr_en   = wr_en;
    assign vmem_wr_addr = wr_addr;
    assign vmem_wr_data = {{wr_attr, wr_data}};

endmodule
'''
    return sv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fields-json', required=True)
    ap.add_argument('--out-rtl', required=True)
    ap.add_argument('--mode', required=True, choices=['single_cycle', 'pipeline'])
    args = ap.parse_args()

    with open(args.fields_json) as fp:
        data = json.load(fp)

    rtl = generate_rtl(data['fields'], args.mode)

    Path(args.out_rtl).write_text(rtl)
    print(f'Generated {args.out_rtl} with {len(data["fields"])} fields')
    return 0


if __name__ == '__main__':
    sys.exit(main())
