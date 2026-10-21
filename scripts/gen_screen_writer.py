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

# The live memory tables of the console.  A table is a window over a
# memory: the writer follows the address of the last access and draws the
# words around it, one row at a time.
TABLE_SHADOWS = ('imem', 'dmem')

# What the shadows hold, for the comment of the unused ones.
SHADOW_CONTENT = {
    'imem': 'the program memory',
    'dmem': 'the data memory',
}

# The characters of one row of a table: the byte address, a colon, a
# space and the word.
TABLE_ADDR_DIGITS = 4
TABLE_FILLER = 2      # the colon and the space behind the address

# The width of a word address inside a table.  A table addresses the words
# of its memory, so the address needs a bit for every word of the deepest
# memory of the console.
# shortcut: 14 bits reach 16384 words; a deeper memory needs a wider
# address.
TABLE_WORD_BITS = 14

# The decoding panel: the lines that show the instruction in flight,
# decoded.  The panel is a group of its own: its characters are a mix of
# constant text and values decoded from the instruction, so it computes
# them from the line and the column it draws.
PANEL_LINES = 4
PANEL_CHARS = 24

# The colour of the labels of the panel: the body colour of the console.
PANEL_LABEL_FG = 9

# The values of the panel: their width and their colour.
PANEL_VALUES = {
    'instr':    (8, 8),    # the instruction in flight
    'mnemonic': (6, 15),   # its mnemonic
    'rd':       (2, 13),   # the register numbers
    'rs1':      (2, 13),
    'rs2':      (2, 13),
    'imm':      (8, 12),   # the immediate
}

# The lines of the panel: every line is a list of segments, and a segment
# is a constant label or a value decoded from the instruction in flight.
PANEL_CONTENT = (
    (('text', 'INSTR'), ('text', ' '), ('value', 'instr')),
    (('text', 'MNEM'), ('text', '  '), ('value', 'mnemonic')),
    (('text', 'rd='), ('value', 'rd'), ('text', ' '),
     ('text', 'rs1='), ('value', 'rs1'), ('text', ' '),
     ('text', 'rs2='), ('value', 'rs2')),
    (('text', 'imm='), ('value', 'imm')),
)

# The mnemonic of every instruction the panel decodes.  The table is
# indexed by the opcode and the funct3 of the instruction; the names are
# padded with spaces to the six characters of the field.  A name that
# depends on the funct7 is a pair: the name for funct7[5] = 0 and the name
# for funct7[5] = 1.
#
# The operations that need the funct7 of the instruction live in the
# 'funct7' table of their opcode.  The M extension of this core is OP
# with funct7 = 0000001, as the control unit decodes it; the opcodes of
# the RISC-V manual cannot occur in this core.
MNEMONICS = {
    0b0110011: {
        'funct7': {
            '0000001': {'000': 'MUL', '001': 'MULH', '010': 'MULHSU',
                        '011': 'MULHU', '100': 'DIV', '101': 'DIVU',
                        '110': 'REM', 'default': 'REMU'},
        },
        'funct3': {'000': 'ADD', '001': 'SLL', '010': 'SLT', '011': 'SLTU',
                   '100': 'XOR', '101': ('SRL', 'SRA'), '110': 'OR',
                   'default': 'AND'},
    },
    0b0010011: {
        'funct3': {'000': 'ADDI', '010': 'SLTI', '011': 'SLTIU',
                   '100': 'XORI', '110': 'ORI', '001': 'SLLI',
                   '101': ('SRLI', 'SRAI'), 'default': 'ANDI'},
    },
    0b0100011: {
        'funct3': {'000': 'SB', '001': 'SH', 'default': 'SW'},
    },
    0b0000011: {
        'funct3': {'000': 'LB', '001': 'LH', '100': 'LBU', '101': 'LHU',
                   'default': 'LW'},
    },
    0b1100011: {
        'funct3': {'000': 'BEQ', '001': 'BNE', '100': 'BLT', '101': 'BGE',
                   '110': 'BLTU', 'default': 'BGEU'},
    },
    0b1101111: {'funct3': {'default': 'JAL'}},
    0b1100111: {'funct3': {'default': 'JALR'}},
    0b0110111: {'funct3': {'default': 'LUI'}},
    0b0010111: {'funct3': {'default': 'AUIPC'}},
}


def is_reg_field(name: str) -> bool:
    return re.fullmatch(r'x\d+', name) is not None


def is_text_field(field: dict) -> bool:
    """A rewrite field: a static character with a dynamic attribute.

    It carries no signal, so it has no port and no snapshot entry."""
    return field.get('kind') == 'text'


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


def group_attribute(gfields: list, snapshots: Set[str], local_wires: Set[str]) -> str:
    """The attribute of a group whose fields share one attribute.

    The register table is written one row at a time, so the writer cannot
    select an attribute per row: every row has to carry the same one."""
    expressions = {attr_expression(f, snapshots, local_wires) for f in gfields}
    if len(expressions) != 1:
        raise ValueError('The register rows must share one attribute.')
    return expressions.pop()


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


def derived_wires(snapshots: Set[str], live_access: bool = False) -> List[List[Tuple[str, List[str]]]]:
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
    if live_access:
        # The live memory access: the live table follows the address of the
        # access, so the address and the access have to come from the same
        # instant, and the snapshot bank cannot deliver that.
        memory.append(('mem_access_live', [
            f"({mem_instr}[6:0] == 7'b{LOAD_OPCODE:07b}) ||",
            f"({mem_instr}[6:0] == 7'b{STORE_OPCODE:07b})",
        ]))
        memory.append(('mem_store_live', [
            f"({mem_instr}[6:0] == 7'b{STORE_OPCODE:07b})",
        ]))

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

    # Every character of a field shares its attribute.  The map is keyed by
    # the address of the slot: a signal may feed more than one slot, and the
    # slots of one name do not have to share their attribute.
    attrs = {f['start_address']: attr_expression(f, snapshots, local_wires)
             for f in gfields}

    chars = []
    for f in gfields:
        width = f['width']
        fmt = f['fmt']
        bits = f['signal_bits']
        for pos in range(width):
            if is_text_field(f):
                chars.append((f, pos, 0, 'text'))
            elif fmt == 'hex':
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
        if is_text_field(f):
            # A rewrite field writes the character of the template with a
            # dynamic attribute.
            data_expr = f"8'h{ord(f['text'][pos]):02X}"
        else:
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
            f"wr_data = {data_expr}; wr_attr = {attrs[f['start_address']]}; end"
        )

    # Snapshot entries of this group: (register name, source signal)
    if gname == 'REGS':
        snap = [(REG_BUS, REG_BUS)]
    else:
        seen = []
        for f in gfields:
            if (not is_reg_field(f['name']) and not is_text_field(f)
                    and f['name'] not in seen):
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


def build_table_group(table: dict, screen_width: int) -> dict:
    """Build the description of the group of a live memory table.

    The table is not an ordinary field group: its character multiplexer
    would have one input per character.  Instead the group computes the
    character from the row and the column it draws, so the multiplexer has
    one input per column.

    The table samples the live signals at its sweep boundary: the address
    of an access and the fact that it happened have to come from the same
    instant, and the shared snapshot bank loads every group at its own
    boundary."""
    name = table['name']
    rows = table['rows']
    row_bytes = table['row_bytes']
    addcol = table['addr_col'] - table['col']
    datacol = table['data_col'] - table['col']
    chars = rows * row_bytes
    return {
        'name': f'TBL_{name.upper()}',
        'lower': f'tbl_{name}',
        'rows': rows,
        'row_bytes': row_bytes,
        'row0': table['row'] * screen_width + table['col'],
        'stride': screen_width,
        'addcol': addcol,
        'datacol': datacol,
        'data_digits': row_bytes - addcol - TABLE_ADDR_DIGITS - TABLE_FILLER,
        'n': chars,
        'ctr_w': (chars - 1).bit_length(),
        'shadow': table['shadow'],
        'follow': table['follow_signal'],
        'only_access': bool(table.get('only_on_access')),
        'depth_param': table['depth_param'],
        'fields': [],
        'params': '',
        'cases': '',
        'snap': [],
        'is_table': True,
    }


def table_blocks(t: dict) -> dict:
    """The generated blocks of a live memory table.

    The table owns its state: the window base and the marked row are
    sampled at the sweep boundary, so every row of a sweep describes the
    same window."""
    upper = t['name']
    lower = t['lower']
    shadow = t['shadow']
    follow = t['follow']
    depth = t['depth_param']
    w = TABLE_WORD_BITS

    # A table that follows an access keeps the address of the last one;
    # a table that follows a running value keeps that value.
    if t['only_access']:
        access = 'mem_access_live'
        write = 'mem_store_live'
        keeps = 'the last access'
        hit_comment = """    // The word the access touches.  The memory masks the index to its
    // depth, so an access beyond the memory lands in a lower word: the
    // table has to mark the word the hardware really used."""
    else:
        access = "1'b1"
        write = "1'b0"
        keeps = 'the running value'
        hit_comment = """    // The word the followed signal points at.  The memory masks the
    // index to its depth, so an address beyond the memory lands in a
    // lower word: the table has to mark the word the hardware used."""

    decls = f"""    // Live memory table: {shadow}
    localparam int {upper}_ROWS = {t['rows']};
    localparam logic [12:0] {upper}_ROW0 = 13'd{t['row0']};
    localparam logic [12:0] {upper}_STRIDE = 13'd{t['stride']};
    localparam logic [3:0] {upper}_ADDCOL = 4'd{t['addcol']};
    localparam logic [3:0] {upper}_DATACOL = 4'd{t['datacol']};
    localparam logic [12:0] {upper}_MIDDLE = {upper}_ROWS / 2;
    localparam logic [{w-1}:0] {upper}_MAX_BASE = {depth} - {t['rows']};
    localparam logic [{w-1}:0] {upper}_WORD_MASK = {depth} - 1;

    logic [5:0]  {lower}_row;          // the row of the table being drawn
    logic [3:0]  {lower}_col;          // the character of the row being drawn
    logic [31:0] {lower}_word;         // the word of the row, from the shadow
    logic [{w-1}:0] {lower}_base;         // the word address of the first row
    logic [{w-1}:0] {lower}_addr;         // the word address of the row drawn
    logic [{w-1}:0] {lower}_marked;       // the word address of the marked row
    logic [{w-1}:0] {lower}_access_base;  // the base of the last access
    logic [{w-1}:0] {lower}_access_word;  // the word address of the last access
    logic        {lower}_access_write; // the last access was a write
    logic        {lower}_access_valid; // an access has happened
    logic        {lower}_marked_write; // the marked row is a write
    logic        {lower}_marked_valid; // the marked row is an access"""

    resets = '\n'.join(
        f"            {lower}_{name} <= {value};"
        for name, value in (('row', "'0"), ('col', "'0"), ('base', "'0"),
                            ('addr', "'0"), ('marked', "'0"),
                            ('marked_write', "1'b0"), ('marked_valid', "1'b0"))
    )
    # The read address of the shadow starts at word 0.
    resets += f"\n            {shadow}_rd_addr <= '0;"

    wires = f"""{hit_comment}
    wire [{w-1}:0] {lower}_hit_word = ({follow} >> 2) & {upper}_WORD_MASK;
    // The window base: the word sits in the middle of the table.
    wire [{w-1}:0] {lower}_new_base = ({lower}_hit_word > {upper}_MIDDLE)
                                    ? ({lower}_hit_word - {upper}_MIDDLE) : {w}'d0;
    wire [{w-1}:0] {lower}_clamped = ({lower}_new_base > {upper}_MAX_BASE)
                                  ? {upper}_MAX_BASE : {lower}_new_base;
    // The marked row of the table.
    wire {lower}_is_marked = {lower}_marked_valid
                             && ({lower}_addr == {lower}_marked);"""

    state = f"""    // The table follows {keeps}.  The window and the marked row are
    // sampled at the sweep boundary, so every row of a sweep shows the
    // same window.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            {lower}_word <= '0;
            {lower}_access_base <= '0;
            {lower}_access_word <= '0;
            {lower}_access_write <= 1'b0;
            {lower}_access_valid <= 1'b0;
        end else begin
            {lower}_word <= {shadow}_rd_data;
            if ({access}) begin
                {lower}_access_base <= {lower}_clamped;
                {lower}_access_word <= {lower}_hit_word;
                {lower}_access_write <= {write};
                {lower}_access_valid <= 1'b1;
            end
        end
    end"""

    fsm = f"""                GRP_{upper}: begin
                    ctr_{lower} <= (ctr_{lower} == N_{upper} - 1) ? '0 : ctr_{lower} + 1'b1;
                    if (ctr_{lower} == N_{upper} - 1) begin
                        // A new sweep: the window follows {keeps}.
                        {lower}_row <= 6'd0;
                        {lower}_col <= 4'd0;
                        {lower}_base <= {lower}_access_base;
                        {lower}_addr <= {lower}_access_base;
                        {lower}_marked <= {lower}_access_word;
                        {lower}_marked_write <= {lower}_access_write;
                        {lower}_marked_valid <= {lower}_access_valid;
                        {shadow}_rd_addr <= {lower}_access_base * 4;
                    end else if ({lower}_col == 4'd{t['row_bytes'] - 1}) begin
                        {lower}_col <= 4'd0;
                        {lower}_row <= {lower}_row + 6'd1;
                        {lower}_addr <= {lower}_base + {{{w-6}'d0, {lower}_row}} + {w}'d1;
                        {shadow}_rd_addr <= ({lower}_base + {{{w-6}'d0, {lower}_row}} + {w}'d1) * 4;
                    end else begin
                        {lower}_col <= {lower}_col + 4'd1;
                    end
                end"""

    if t['only_access']:
        attr = f"""                wr_attr = {lower}_is_marked
                          ? ({lower}_marked_write ? 8'h38 : 8'h28) : 8'h09;"""
    else:
        # The marked row is not an access: it wears the background of an
        # active stage box, so it reads as "this is where we are".
        attr = f"                wr_attr = {lower}_is_marked ? 8'h18 : 8'h09;"

    case = f"""            GRP_{upper}: begin
                wr_en   = 1'b1;
                wr_addr = {upper}_ROW0 + {{7'd0, {lower}_row}} * {upper}_STRIDE
                          + {{10'd0, {lower}_col}};
                if ({lower}_col < {upper}_ADDCOL + 4'd{TABLE_ADDR_DIGITS})
                    wr_data = hex_digit({{{lower}_addr, 2'b00}},
                                        {TABLE_ADDR_DIGITS - 1} - ({lower}_col - {upper}_ADDCOL));
                else if ({lower}_col == {upper}_ADDCOL + 4'd{TABLE_ADDR_DIGITS})
                    wr_data = 8'h3A;   // ':'
                else if ({lower}_col == {upper}_DATACOL - 4'd1)
                    wr_data = 8'h20;   // ' '
                else
                    wr_data = hex_digit({lower}_word,
                                        {t['data_digits'] - 1} - ({lower}_col - {upper}_DATACOL));
                // The marked row carries a '>'.
                if ({lower}_col == {upper}_ADDCOL && {lower}_is_marked)
                    wr_data = 8'h3E;   // '>'
{attr}
            end"""

    return {'decls': decls, 'wires': wires, 'state': state, 'resets': resets,
            'fsm': fsm, 'case': case}


def panel_segments() -> List[List[dict]]:
    """The segments of every line of the panel: their columns and their kind.

    A segment is a constant label or a value; the width of a value comes
    from its kind."""
    lines = []
    for line in PANEL_CONTENT:
        segments = []
        col = 0
        for kind, content in line:
            width = len(content) if kind == 'text' else PANEL_VALUES[content][0]
            segments.append({'kind': kind, 'content': content, 'col': col,
                             'width': width})
            col += width
        lines.append(segments)
    return lines


def label_name(text: str) -> str:
    """The name of the constant that holds a label of the panel."""
    return 'PANEL_TXT_' + re.sub(r'[^0-9A-Z]', '', text.upper())


def panel_value_expression(kind: str, start: int, width: int) -> str:
    """The expression of the characters of a value of the panel.

    The register numbers are decimal, the instruction word and the
    immediate are hex, and the mnemonic is the packed string the decoder
    delivers."""
    last = start + width - 1
    if kind == 'instr':
        return f'hex_digit(dec_instr, {last} - col)'
    if kind == 'imm':
        return f'hex_digit(dec_imm, {last} - col)'
    if kind == 'mnemonic':
        return f"8'((dec_mnemonic >> (8*({last} - col))) & 8'hFF)"
    if kind in ('rd', 'rs1', 'rs2'):
        return f'dec_digit(dec_{kind}, col - {start})'
    raise ValueError(f"Unknown value of the panel: '{kind}'.")


def panel_char_function(lines: List[List[dict]]) -> str:
    """The function that returns the character of a cell of the panel.

    The multiplexer of the panel has one input per segment of a line and
    not one per character: the labels are constant text and the values are
    decoded from the instruction in flight."""
    cases = []
    for index, segments in enumerate(lines):
        branches = []
        for segment in segments:
            start = segment['col']
            end = start + segment['width']
            if segment['kind'] == 'text':
                text = segment['content']
                if len(set(text)) == 1:
                    # A run of the same character: a space between the
                    # values of a line.
                    expr = f"8'h{ord(text[0]):02X}"
                else:
                    name = label_name(text)
                    expr = (f"8'(({name} >> (8*({end - 1} - col))) "
                            f"& 8'hFF)")
            else:
                expr = panel_value_expression(segment['content'], start,
                                              segment['width'])
            branches.append((end, expr))
        body = []
        for position, (end, expr) in enumerate(branches):
            keyword = 'if' if position == 0 else 'else if'
            body.append(f'                    {keyword} (col < {end})')
            body.append(f'                        panel_char = {expr};')
        body.append('                    else')
        body.append("                        panel_char = 8'h20;  // ' '")
        cases.append(f'                {index}: begin\n' +
                     '\n'.join(body) + '\n                end')
    return f"""    // The character of a cell of the panel: the labels are constant text,
    // the values are decoded from the instruction in flight.
    function automatic [7:0] panel_char(input int unsigned line,
                                        input int unsigned col);
        begin
            case (line)
{chr(10).join(cases)}
                default: panel_char = 8'h20;  // ' '
            endcase
        end
    endfunction"""


def panel_attr_function(lines: List[List[dict]]) -> str:
    """The function that returns the attribute of a cell of the panel.

    The labels wear the body colour, every value the colour of its kind."""
    cases = []
    for index, segments in enumerate(lines):
        colours: dict = {}
        for segment in segments:
            if segment['kind'] != 'value':
                continue
            fg = PANEL_VALUES[segment['content']][1]
            colours.setdefault(fg, []).append(segment)
        expr = f"8'h{PANEL_LABEL_FG:02X}"
        for fg, group in reversed(list(colours.items())):
            conditions = ' || '.join(
                f"(col >= {s['col']} && col < {s['col'] + s['width']})"
                for s in group
            )
            expr = f"{conditions} ? 8'h{fg:02X} : {expr}"
        cases.append(f'                {index}: panel_attr = {expr};')
    return f"""    // The attribute of a cell of the panel: the labels wear the body
    // colour, every value the colour of its kind.
    function automatic [7:0] panel_attr(input int unsigned line,
                                        input int unsigned col);
        begin
            case (line)
{chr(10).join(cases)}
                default: panel_attr = 8'h{PANEL_LABEL_FG:02X};
            endcase
        end
    endfunction"""


def mnemonic_expression(name) -> str:
    """The expression of a mnemonic.

    A name is a string, or a pair: the name for funct7[5] = 0 and the
    name for funct7[5] = 1."""
    if isinstance(name, tuple):
        return f'dec_funct7[5] ? "{name[1]:<6}" : "{name[0]:<6}"'
    return f'"{name:<6}"'


def mnemonic_funct3_case(funct3s: dict, indent: int) -> str:
    """The case over the funct3 that gives the mnemonic."""
    pad = ' ' * indent
    if list(funct3s) == ['default']:
        return (f'{pad}dec_mnemonic = '
                f"{mnemonic_expression(funct3s['default'])};\n")
    items = []
    for funct3, name in funct3s.items():
        if funct3 == 'default':
            items.append(f'{pad}    default: '
                         f'dec_mnemonic = {mnemonic_expression(name)};')
        else:
            items.append(f"{pad}    3'b{funct3}: "
                         f'dec_mnemonic = {mnemonic_expression(name)};')
    return (f'{pad}case (dec_funct3)\n' + '\n'.join(items) + '\n' +
            f'{pad}endcase\n')


def mnemonic_opcode_body(table: dict) -> str:
    """The body of the case of one opcode.

    The operations that need the funct7 of the instruction are decoded
    first; the rest of the opcode only needs the funct3."""
    funct7_table = table.get('funct7')
    if funct7_table is None:
        return mnemonic_funct3_case(table['funct3'], 16)
    body = ''
    for index, (funct7, funct3s) in enumerate(funct7_table.items()):
        keyword = 'if' if index == 0 else 'end else if'
        body += (f'                {keyword} '
                 f"(dec_funct7 == 7'b{funct7}) begin\n" +
                 mnemonic_funct3_case(funct3s, 20))
    body += '                end else begin\n'
    body += mnemonic_funct3_case(table['funct3'], 20)
    body += '                end\n'
    return body


def panel_mnemonic_case() -> str:
    """The case that decodes the mnemonic of the instruction in flight."""
    cases = []
    for opcode, table in MNEMONICS.items():
        cases.append(f"            7'b{opcode:07b}: begin\n" +
                     mnemonic_opcode_body(table) + '            end')
    return '\n'.join(cases)


def build_panel_group(panel: dict, screen_width: int) -> dict:
    """Build the description of the group of the decoding panel.

    The panel is not an ordinary field group: its characters come from
    the line and the column it draws, so the multiplexer of the group has
    one input per segment of a line and not one per character."""
    if panel['width'] < PANEL_CHARS:
        raise ValueError(
            f"The decoding panel is {panel['width']} characters wide, but "
            f'its lines are {PANEL_CHARS} characters long.'
        )
    if panel['lines'] != PANEL_LINES:
        raise ValueError(
            f"The decoding panel has {panel['lines']} lines, but the "
            f'generator draws {PANEL_LINES}.'
        )
    return {
        'name': 'PANEL',
        'n': PANEL_LINES * PANEL_CHARS,
        'fields': [],
        'params': '',
        'cases': '',
        'snap': [],
        'is_panel': True,
        'row0': panel['row'] * screen_width + panel['col'],
    }


def panel_blocks(group: dict, screen_width: int, snapshot: str) -> dict:
    """The generated blocks of the decoding panel.

    The panel owns its state: the line and the column it draws, and the
    instruction it decodes.  The instruction is captured at the sweep
    boundary, because the word and its decode have to describe the same
    instruction, and the field groups reload the shared snapshot bank
    while the panel is drawn."""
    lines = panel_segments()

    labels = []
    for segments in lines:
        for segment in segments:
            text = segment['content']
            if segment['kind'] != 'text' or len(set(text)) == 1:
                continue
            if text not in labels:
                labels.append(text)
    label_decls = '\n'.join(
        f'    // "{text}"\n'
        f"    localparam logic [{8 * len(text) - 1}:0] {label_name(text)} = "
        f'"{text}";'
        for text in labels
    )

    decls = f"""    // The decoding panel: the instruction in flight, decoded.
    localparam int PANEL_LINES = {PANEL_LINES};
    localparam int PANEL_CHARS = {PANEL_CHARS};
    localparam logic [12:0] PANEL_ROW0 = 13'd{group['row0']};
    localparam logic [12:0] PANEL_STRIDE = 13'd{screen_width};

    logic [1:0]  panel_line;         // the line of the panel being drawn
    logic [4:0]  panel_col;          // the column of the line being drawn
    logic [31:0] panel_instruction;  // the instruction the panel decodes

    // The labels of the panel: constant text.
{label_decls}"""

    wires = f"""    // Instruction decode of the instruction in flight.
    wire [31:0] dec_instr  = panel_instruction;
    wire [6:0]  dec_opcode = panel_instruction[6:0];
    wire [2:0]  dec_funct3 = panel_instruction[14:12];
    wire [6:0]  dec_funct7 = panel_instruction[31:25];
    wire [4:0]  dec_rd     = panel_instruction[11:7];
    wire [4:0]  dec_rs1    = panel_instruction[19:15];
    wire [4:0]  dec_rs2    = panel_instruction[24:20];
    wire [11:0] dec_imm_i  = panel_instruction[31:20];
    wire [11:0] dec_imm_s  = {{panel_instruction[31:25], panel_instruction[11:7]}};
    wire [12:0] dec_imm_b  = {{panel_instruction[31], panel_instruction[7],
                               panel_instruction[30:25], panel_instruction[11:8], 1'b0}};
    wire [19:0] dec_imm_u  = panel_instruction[31:12];
    wire [20:0] dec_imm_j  = {{panel_instruction[31], panel_instruction[19:12],
                               panel_instruction[20], panel_instruction[30:21], 1'b0}};

    // 0 = R, 1 = I, 2 = S, 3 = B, 4 = U, 5 = J
    logic [2:0] dec_format;
    always_comb begin
        case (dec_opcode)
            7'b0110011:                            dec_format = 3'd0;  // OP
            7'b0010011, 7'b0000011,
            7'b1100111, 7'b1110011:                dec_format = 3'd1;  // OP-IMM, LOAD, JALR, SYSTEM
            7'b0100011:                            dec_format = 3'd2;  // STORE
            7'b1100011:                            dec_format = 3'd3;  // BRANCH
            7'b0110111, 7'b0010111:                dec_format = 3'd4;  // LUI, AUIPC
            7'b1101111:                            dec_format = 3'd5;  // JAL
            default:                               dec_format = 3'd0;
        endcase
    end

    // The mnemonic of the instruction in flight.
    logic [47:0] dec_mnemonic;
    always_comb begin
        case (dec_opcode)
{panel_mnemonic_case()}
            default:    dec_mnemonic = "      ";
        endcase
    end

    // The immediate of the decoded format, zero extended.
    wire [31:0] dec_imm = (dec_format == 3'd1) ? {{20'd0, dec_imm_i}} :
                          (dec_format == 3'd2) ? {{20'd0, dec_imm_s}} :
                          (dec_format == 3'd3) ? {{19'd0, dec_imm_b}} :
                          (dec_format == 3'd4) ? {{12'd0, dec_imm_u}} :
                          (dec_format == 3'd5) ? {{11'd0, dec_imm_j}} : 32'd0;

    // The decimal digit of a register number: the tens first.
    function automatic [7:0] dec_digit(input logic [4:0] value, input int pos);
        logic [5:0] tens;
        begin
            tens = (value >= 10) + (value >= 20) + (value >= 30);
            if (pos == 0)
                dec_digit = 8'd48 + tens;
            else
                dec_digit = 8'd48 + (value - 10 * tens);
        end
    endfunction

{panel_char_function(lines)}

{panel_attr_function(lines)}
"""

    resets = """            panel_line <= '0;
            panel_col <= '0;
            panel_instruction <= '0;"""

    fsm = f"""                GRP_PANEL: begin
                    if (panel_col == PANEL_CHARS - 1) begin
                        panel_col <= 5'd0;
                        panel_line <= panel_line + 2'd1;
                        // The next sweep decodes the instruction the bank
                        // holds now: the word and its decode have to
                        // describe the same instruction.
                        if (panel_line == PANEL_LINES - 1)
                            panel_instruction <= {snapshot};
                    end else begin
                        panel_col <= panel_col + 5'd1;
                    end
                end"""

    case = """            GRP_PANEL: begin
                wr_en   = 1'b1;
                wr_addr = PANEL_ROW0 + {10'd0, panel_line} * PANEL_STRIDE
                          + {8'd0, panel_col};
                wr_data = panel_char(panel_line, panel_col);
                wr_attr = panel_attr(panel_line, panel_col);
            end"""

    return {'decls': decls, 'wires': wires, 'resets': resets, 'fsm': fsm,
            'case': case}


def generate_rtl(data: dict, mode: str) -> str:
    """Produce the SystemVerilog source for the screen writer."""
    fields = data['fields']
    screen_width = data.get('screen_width', 160)

    # The memory tables are static content of the framebuffer.
    def is_table_field(f: dict) -> bool:
        return (f['name'].startswith('data_memory_') or
                f['name'].startswith('prog._memory_'))

    proc_fields = [f for f in fields
                   if not is_reg_field(f['name']) and not is_table_field(f)]
    reg_fields = [f for f in fields if is_reg_field(f['name'])]

    # Input port list: the union of the groups.  A rewrite field carries no
    # signal, so it has no port.
    signal_fields = [f for f in proc_fields if not is_text_field(f)]
    port_names = sorted(set(f['name'] for f in signal_fields))
    port_widths = {f['name']: f['signal_bits'] for f in signal_fields}
    if reg_fields:
        port_names.append(REG_BUS)
        port_widths[REG_BUS] = REG_BUS_WIDTH
    snapshots = set(port_names)

    # The live memory tables are groups of their own: their characters come
    # from the row and the column the group draws.
    table_groups = [build_table_group(t, screen_width)
                    for t in data.get('tables', [])]
    # A table may follow a live signal or the snapshot of one.
    followable = snapshots | {f'snap_{name}' for name in snapshots}
    for t in table_groups:
        if t['follow'] not in followable:
            raise ValueError(
                f"The table '{t['lower']}' follows the signal '{t['follow']}', "
                'which this design neither samples nor derives.'
            )
        t['blocks'] = table_blocks(t)

    # The derived wires the attribute expressions may reference.
    wires = derived_wires(snapshots, bool(table_groups))
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
    # The live tables are exempt from the size limit: their multiplexer has
    # one input per column, not one per character.
    groups.extend(table_groups)

    # The decoding panel is a group of its own: it mixes the constant text
    # of its labels with the values decoded from the instruction in flight.
    panel = data.get('panel')
    if panel:
        instruction = panel['instruction_signal']
        if instruction not in snapshots:
            raise ValueError(
                f"The decoding panel decodes the signal '{instruction}', "
                'which this design neither samples nor derives.'
            )
        panel_group = build_panel_group(panel, screen_width)
        panel_group['blocks'] = panel_blocks(panel_group, screen_width,
                                             f'snap_{instruction}')
        groups.append(panel_group)

    input_ports = '\n'.join(
        f"    input logic [{port_widths[n]-1}:0] {n},"
        for n in port_names
    )

    # The ports of the memory shadows the tables read.  The address is a
    # byte address, like the one of the shadow.
    memory_ports = (
        "    // Live memory windows (VGA clock domain)\n"
        "    output logic [31:0] imem_rd_addr,\n"
        "    input  logic [31:0] imem_rd_data,\n"
        "    output logic [31:0] dmem_rd_addr,\n"
        "    input  logic [31:0] dmem_rd_data,"
    )

    # A shadow without a table reads word 0.
    live_shadows = {t['shadow'] for t in table_groups}
    shadow_ties = []
    for shadow in TABLE_SHADOWS:
        if shadow not in live_shadows:
            shadow_ties.append(
                f"    // No table reads {SHADOW_CONTENT[shadow]} yet: the shadow reads\n"
                f"    // word 0.\n"
                f"    assign {shadow}_rd_addr = 32'h0;\n\n"
            )
    shadow_ties = ''.join(shadow_ties)

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

        if g.get('is_panel'):
            # The panel computes its characters from the line and the column
            # it draws, and it owns its state.
            counter_decls.append(f"    localparam int N_{gname} = {g['n']};")
            counter_fsm.append(g['blocks']['fsm'])
            case_blocks.append(g['blocks']['case'])
            continue

        counter_decls.append(
            f"    localparam int N_{gname} = {g['n']};\n"
            f"    localparam int CTR_{gname}_W = {g['ctr_w']};\n"
            f"    logic [CTR_{gname}_W-1:0] ctr_{lower};"
        )

        load = '\n'.join(
            f"                    snap_{src} <= {src};"
            for _, src in g['snap']
        )
        # A group of rewrite fields samples no signal, so it loads nothing.
        load_block = ''
        if load:
            load_block = (
                "                    // Load the bank at the end of a sweep, so the next sweep\n"
                "                    // renders every character from the same captured instant.\n"
                f"                    if (ctr_{lower} == N_{gname} - 1) begin\n"
                f"{load}\n"
                "                    end\n"
            )

        if g.get('is_table'):
            # The table computes its characters from the row and the column
            # it draws, and it owns its state.
            counter_fsm.append(g['blocks']['fsm'])
            case_blocks.append(g['blocks']['case'])
        elif gname == 'REGS':
            reg_group = g
            counter_fsm.append(f"""                GRP_{gname}: begin
                    ctr_{lower} <= (ctr_{lower} == N_{gname} - 1) ? '0 : ctr_{lower} + 1'b1;
{load_block}                    // Stage 1: select the register row of this character.
                    reg_value <= snap_{REG_BUS}[32*ctr_{lower}[7:3] +: 32];
                    reg_addr  <= REG_ADDR[13*ctr_{lower}[7:3] +: 13];
                    reg_col   <= ctr_{lower}[2:0];
                end""")
            case_blocks.append(f"""            GRP_{gname}: begin
                // Stage 2: the character inside the row selected by stage 1.
                wr_en   = 1'b1;
                wr_addr = reg_addr + {{10'd0, reg_col}};
                wr_data = hex_digit(reg_value, 7 - reg_col);
                wr_attr = {group_attribute(g['fields'], snapshots, local_wires)};
            end""")
        else:
            counter_fsm.append(f"""                GRP_{gname}: begin
                    ctr_{lower} <= (ctr_{lower} == N_{gname} - 1) ? '0 : ctr_{lower} + 1'b1;
{load_block}                end""")
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
        f"            ctr_{g['name'].lower()} <= '0;"
        for g in groups if not g.get('is_panel')
    )

    derived = '\n'.join('\n'.join(format_wires(block)) for block in wires)
    derived_block = f"{derived}\n" if derived else ''

    table_decls = '\n'.join(t['blocks']['decls'] for t in table_groups)
    table_wires = '\n'.join(t['blocks']['wires'] for t in table_groups)
    table_state = '\n'.join(t['blocks']['state'] for t in table_groups)
    table_resets = '\n'.join(t['blocks']['resets'] for t in table_groups)

    panel_decls = ''
    panel_wires = ''
    panel_resets = ''
    for g in groups:
        if g.get('is_panel'):
            panel_decls = g['blocks']['decls']
            panel_wires = g['blocks']['wires']
            panel_resets = g['blocks']['resets']

    sv = f'''// screen_writer_{mode} - auto-generated by gen_screen_writer.py
// Character-level round-robin, {total_chars} characters split in {n_groups}
// alternating groups.  Displayed values come from a snapshot bank loaded
// once per sweep.

module screen_writer_{mode} #(
    // The depth of the data memory the live table reads; the window of
    // the table clamps to its last rows.
    parameter int DMEM_DEPTH = 512,
    // The depth of the program memory the live program table reads.
    parameter int IMEM_DEPTH = 2048
) (
    input logic        clk,
    input logic        rst_n,

    // Processor signals (all values to be displayed)
{input_ports}

{memory_ports}

    // Video memory port (write-only, processor clock domain)
    output logic        vmem_wr_en,
    output logic [12:0] vmem_wr_addr,
    output logic [15:0] vmem_wr_data
);

    // Field address map (from fields.json)
{chr(10).join(g['params'] for g in groups if g['params'])}

    // The groups rotate: one group is written per cycle.
{chr(10).join(group_consts)}

    localparam int N_GROUPS = {n_groups};
    localparam int GRP_W    = {grp_w};
    localparam int N_CHARS  = {total_chars};

{chr(10).join(counter_decls)}

{table_decls}

{panel_decls}

{table_wires}

{shadow_ties}    logic [GRP_W-1:0] grp_ctr;

    // Register table, stage 1: the row of the character being written.
    localparam logic [{REG_COUNT * 13 - 1}:0] REG_ADDR = {{{reg_addr_array}}};
    logic [31:0] reg_value;
    logic [12:0] reg_addr;
    logic [2:0]  reg_col;

    // Snapshot bank - the whole screen is rendered from one instant
{snap_decls}

    // Derived signals used by the attribute expressions; a signal may come
    // from a snapshot of another group, so it can lag one sweep behind.
{derived_block}
{panel_wires}
{table_state}
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
{table_resets}
{panel_resets}
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

    rtl = generate_rtl(data, args.mode)

    Path(args.out_rtl).write_text(rtl)
    print(f'Generated {args.out_rtl} with {len(data["fields"])} fields')
    return 0


if __name__ == '__main__':
    sys.exit(main())
