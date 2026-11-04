# Compiles with SignalTap II enabled for FPGA validation.
# Usage: cd synthesis/<arch> && quartus_sh -t ../../scripts/build_fpga.tcl <arch> [seed]
#
# Adds SignalTap II to the compilation, runs full compile,
# then removes the SignalTap assignments to keep the .qsf clean
# (they are not needed for replica runs or normal development).
#
# Runs from the project directory like build.tcl and create_stp.tcl: Quartus
# is a Windows binary and cannot chdir into the //wsl.localhost UNC path that
# [file normalize] returns for this repository.

load_package flow

if {$argc < 1} {
    puts "Usage: quartus_sh -t build_fpga.tcl <pipeline|single_cycle> \[seed\]"
    exit 1
}

set arch [lindex $argv 0]

if {$arch eq "pipeline"} {
    set project_name "rv32im_pipeline"
    set stp_file    [file join ".." ".." "stp" "perf_capture_pipeline.stp"]
} elseif {$arch eq "single_cycle"} {
    set project_name "rv32im_single_cycle"
    set stp_file    [file join ".." ".." "stp" "perf_capture_sc.stp"]
} else {
    puts "Error: architecture must be 'pipeline' or 'single_cycle', got '$arch'"
    exit 1
}

# The project must be the current directory (.qpf lookup below is relative).
if {![file exists "${project_name}.qpf"]} {
    puts "Error: no ${project_name}.qpf in [pwd]."
    puts "Run this script from synthesis/${arch}."
    exit 1
}

# Check that the .stp file exists
if {![file exists $stp_file]} {
    puts "Error: SignalTap II file not found: $stp_file"
    puts "Run 'make build-fpga ARCH=${arch}' first to generate it,"
    puts "or create it manually in the SignalTap II GUI."
    exit 1
}

puts ""
puts "============================================"
puts " Building ${arch} with SignalTap II"
puts " STP file: ${stp_file}"
puts "============================================"
puts ""

# Open project
project_open $project_name -force

set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files

# Same parameter as build.tcl: the programme's tohost symbol must match, and
# the Makefile exports TOHOST_ADDR (0x6000 for CoreMark, ADR 047).  It goes to
# the netlist in decimal: Quartus does not parse the 0x form of an Untyped
# parameter and "0x6000" silently became 0 (ADR 051).
set tohost_addr 0x00000708
if {[info exists ::env(TOHOST_ADDR)]} {
    set tohost_addr $::env(TOHOST_ADDR)
}
set_parameter -name TOHOST_ADDR [expr {$tohost_addr}]

# Apply SignalTap assignments
set_global_assignment -name ENABLE_SIGNALTAP ON
set_global_assignment -name SIGNALTAP_FILE $stp_file

puts "SignalTap II enabled: ${stp_file}"

# Optional seed argument
if {$argc > 1} {
    set seed [lindex $argv 1]
    puts "Setting SEED = $seed"
    set_global_assignment -name SEED $seed
}

# Compile
puts ""
puts "Starting compilation..."
set start_time [clock seconds]
execute_flow -compile
set elapsed [expr {[clock seconds] - $start_time}]
set minutes [expr {$elapsed / 60}]
set seconds [expr {$elapsed % 60}]

puts ""
puts "Compilation complete in ${minutes}m ${seconds}s"

# ---------------------------------------------------------------------------
# Remove SignalTap assignments to keep .qsf clean.
# These assignments prevent compilation without the .stp file and are not
# needed for replica/routing runs (Fmax collection).
# ---------------------------------------------------------------------------
remove_all_global_assignments -name SIGNALTAP_FILE
remove_all_global_assignments -name ENABLE_SIGNALTAP

puts ""
puts "SignalTap II assignments removed from .qsf"

project_close

puts ""
puts "=== Output ==="
puts "  SOF: output_files/${project_name}.sof"
puts "  (embedded SignalTap II data)"
puts ""
puts "Next step: make capture ARCH=${arch}"
puts ""

exit 0
