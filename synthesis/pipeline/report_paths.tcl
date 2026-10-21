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

project_close
