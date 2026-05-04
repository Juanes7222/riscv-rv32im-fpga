# Synchronizes RTL source files in an existing Quartus project.
# Use this whenever a new .sv file is added to rtl/shared/ or rtl/single_cycle/.
# Usage: quartus_sh -t sync.tcl

load_package flow

# Project configuration
set project_name "rv32im_single_cycle"
set rtl_shared   "../../rtl/shared"
set rtl_arch     "../../rtl/single_cycle"

# Guard: project must exist before syncing
if {![file exists "$project_name.qpf"]} {
    puts "Error: project $project_name not found."
    puts "Run setup.tcl first to create the project."
    exit 1
}

# Open project, clear existing source assignments, re-add all .sv files
project_open $project_name

# Remove all previously registered SystemVerilog files to avoid duplicates
# after renames or deletions.
remove_all_global_assignments -name SYSTEMVERILOG_FILE

# Re-register shared modules
foreach sv_file [glob -nocomplain "$rtl_shared/*.sv"] {
    set_global_assignment -name SYSTEMVERILOG_FILE $sv_file
    puts "  added: $sv_file"
}

# Re-register architecture-specific modules
foreach sv_file [glob -nocomplain "$rtl_arch/*.sv"] {
    set_global_assignment -name SYSTEMVERILOG_FILE $sv_file
    puts "  added: $sv_file"
}

project_close

puts ""
puts "Sync complete: $project_name"
puts "Run 'quartus_sh -t build.tcl' to recompile."