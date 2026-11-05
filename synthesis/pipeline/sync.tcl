# Synchronizes an existing Quartus project: RTL source files, pin
# assignments, I/O standards and memory sizes.
# Use this whenever a new .sv file is added to rtl/shared/ or rtl/pipeline/,
# or whenever synthesis/de1soc_pins.tcl changes.
# Usage: quartus_sh -t sync.tcl

load_package flow

# Project configuration
set project_name "rv32im_pipeline"
set rtl_shared   "../../rtl/shared"
set rtl_arch     "../../rtl/pipeline"

# Guard: project must exist before syncing
if {![file exists "$project_name.qpf"]} {
    puts "Error: project $project_name not found."
    puts "Run setup.tcl first to create the project."
    exit 1
}

# Open project, clear existing source assignments, re-add all .sv files
project_open $project_name

remove_all_global_assignments -name SYSTEMVERILOG_FILE

foreach sv_file [glob -nocomplain "$rtl_shared/*.sv"] {
    set_global_assignment -name SYSTEMVERILOG_FILE $sv_file
    puts "  added: $sv_file"
}

foreach sv_file [glob -nocomplain "$rtl_arch/*.sv"] {
    set_global_assignment -name SYSTEMVERILOG_FILE $sv_file
    puts "  added: $sv_file"
}

# Pin assignments, I/O standards and memory sizes are versioned in the
# shared pinout file; re-apply them here so 'make sync' converges the
# project to de1soc_pins.tcl too (by itself it only re-registers .sv files).
source ../de1soc_pins.tcl

project_close

puts ""
puts "Sync complete: $project_name"
puts "Run 'quartus_sh -t build.tcl' to recompile."