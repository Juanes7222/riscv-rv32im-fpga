# Programs the DE1-SoC FPGA with the compiled bitstream.
# Requires a successful build.tcl run beforehand.
# Usage: quartus_sh -t program.tcl

# Board configuration
# Adjust cable name if your system identifies the DE1-SoC differently.
# Run 'quartus_pgm -l' to list available cables.
set cable  "DE-SoC"
set device "2"

# Detect project name from .qpf in current directory (same as build.tcl)
set qpf_files [glob -nocomplain "*.qpf"]

if {[llength $qpf_files] == 0} {
    puts "Error: no .qpf file found in current directory."
    puts "Run setup.tcl first to create the project."
    exit 1
}

set project_name [file rootname [lindex $qpf_files 0]]
set sof_file     "output_files/${project_name}.sof"

# Guard: SOF must exist before attempting to program
if {![file exists $sof_file]} {
    puts "Error: SOF file not found at $sof_file"
    puts "Run build.tcl first to compile the project."
    exit 1
}

# Program
puts "Programming $project_name onto DE1-SoC..."
puts "  Cable : $cable"
puts "  Device: $device"
puts "  SOF   : $sof_file"
puts ""

if {[catch {
    exec quartus_pgm -c $cable -m JTAG -o "P;${sof_file}@${device}" 2>@1
} output]} {
    puts "Error during programming:"
    puts $output
    exit 1
}

puts "FPGA successfully programmed."