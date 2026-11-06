# Prints the worst setup paths of the processor clock.
#
# The script works on the project of the directory it is run from, so the
# same file serves both architectures:
#   cd synthesis/pipeline && quartus_sta -t report_paths.tcl
#
# Quartus 25.1 needs the timing netlist to be created before the SDC file
# is read, and get_timing_paths does not accept a clock filter any more:
# the paths are selected with -to [get_clocks clk] instead.

load_package report

set qpf [lindex [glob -nocomplain *.qpf] 0]
if {$qpf eq ""} {
    puts "Error: no .qpf file found in the current directory."
    exit 1
}
set project [file rootname $qpf]
project_open $project -current_revision

create_timing_netlist
read_sdc
update_timing_netlist

report_timing -setup -npaths 10 -detail summary

# Half-cycle transfers. The single-cycle data memory captures its read address
# on the falling edge (ADR 048), so these paths have half the period available
# and are the ones that fix its Fmax; in the pipeline they are empty because
# both memories read on the rising edge.
set cpu_clocks [get_clocks -nowarn {clk *cpu_pll*divclk*}]
puts "=== RISE -> FALL ==="
report_timing -setup -rise_from $cpu_clocks -fall_to $cpu_clocks \
    -npaths 3 -detail summary
puts "=== FALL -> RISE ==="
report_timing -setup -fall_from $cpu_clocks -rise_to $cpu_clocks \
    -npaths 3 -detail summary

project_close
