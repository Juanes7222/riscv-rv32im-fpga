# Opens the Quartus project in the current directory and runs a full compile.
# Requires that setup.tcl has been run at least once beforehand.
# Usage: quartus_sh -t build.tcl [seed]
#   seed: optional integer seed for the fitter (enables unique P&R per replica)

load_package flow

# Detect project file in current directory
set qpf_files [glob -nocomplain "*.qpf"]

if {[llength $qpf_files] == 0} {
    puts "Error: no .qpf file found in current directory."
    puts "Run setup.tcl first to create the project."
    exit 1
}

if {[llength $qpf_files] > 1} {
    puts "Error: multiple .qpf files found. Only one project per directory is supported."
    exit 1
}

set project_name [file rootname [lindex $qpf_files 0]]

# Compile
puts ""
puts "Opening project: $project_name"
project_open $project_name -force

set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files

# The tohost address must match the program's tohost symbol.  The Makefile
# exports TOHOST_ADDR (0x708 by default, 0x6000 for CoreMark, ADR 047), so a
# rebuild for another program does not need a new project.
set tohost_addr 0x00000708
if {[info exists ::env(TOHOST_ADDR)]} {
    set tohost_addr $::env(TOHOST_ADDR)
}
set_parameter -name TOHOST_ADDR $tohost_addr

# The campaign measures the architecture, not whatever the tool can do in a
# reduced-effort pass: Auto Fit skips optimizations and costs Fmax (ADR 048).
set_global_assignment -name FITTER_EFFORT "STANDARD FIT"

# Optional seed argument for unique P&R per replica
if {$argc > 0} {
    set seed [lindex $argv 0]
    puts "Setting SEED = $seed"
    set_global_assignment -name SEED $seed
}

puts "Starting compilation..."
set start_time [clock seconds]

execute_flow -compile

set elapsed [expr {[clock seconds] - $start_time}]
set minutes [expr {$elapsed / 60}]
set seconds [expr {$elapsed % 60}]

project_close

# Report timing summary
puts ""
puts "Compilation complete in ${minutes}m ${seconds}s"
puts ""

set sta_rpt "output_files/${project_name}.sta.rpt"

if {[file exists $sta_rpt]} {
    puts "--- Fmax Summary ---"
    set f [open $sta_rpt r]
    set in_fmax_section 0
    while {[gets $f line] >= 0} {
        if {[string match "*Fmax Summary*" $line]} {
            set in_fmax_section 1
        }
        if {$in_fmax_section} {
            puts $line
            incr in_fmax_section
            if {$in_fmax_section > 7} break
        }
    }
    close $f
} else {
    puts "Timing report not found at $sta_rpt"
}