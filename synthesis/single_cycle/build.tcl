# Opens the Quartus project in the current directory and runs a full compile.
# Requires that setup.tcl has been run at least once beforehand.
# Usage: quartus_sh -t build.tcl

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
project_open $project_name

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