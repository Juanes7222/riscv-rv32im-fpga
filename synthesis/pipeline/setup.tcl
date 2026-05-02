# Run once with: quartus_sh -t setup.tcl
# After running, use build.tcl for all subsequent compilations.

load_package flow

# Project configuration
set project_name    "rv32im_pipeline"
set device          "5CSEMA5F31C6"
set family          "Cyclone V"
set top_level       "rv32im_pipeline"  ;

# Paths relative to this script's location (synthesis/pipeline/)
set rtl_shared      "../../rtl/shared"
set rtl_arch        "../../rtl/pipeline"
set constraints_sdc "constraints.sdc"

# Guard: abort if project already exists
if {[file exists "$project_name.qpf"]} {
    puts "Project $project_name already exists. Delete .qpf and .qsf to re-run setup."
    exit 0
}

# Create project
project_new $project_name

set_global_assignment -name FAMILY           $family
set_global_assignment -name DEVICE           $device
set_global_assignment -name TOP_LEVEL_ENTITY $top_level

# Add RTL source files
# Glob picks up all .sv files so new modules are included automatically.
foreach sv_file [glob -nocomplain "$rtl_shared/*.sv"] {
    set_global_assignment -name SYSTEMVERILOG_FILE $sv_file
}

foreach sv_file [glob -nocomplain "$rtl_arch/*.sv"] {
    set_global_assignment -name SYSTEMVERILOG_FILE $sv_file
}

# Timing constraints
set_global_assignment -name SDC_FILE $constraints_sdc

# Synthesis settings
# Identical to single_cycle to satisfy the homogeneous protocol requirement.
# Do not change these settings independently between architectures.
set_global_assignment -name NUM_PARALLEL_PROCESSORS ALL
set_global_assignment -name OPTIMIZATION_MODE        "Balanced"
set_global_assignment -name DSP_BLOCK_BALANCING      "Auto"
set_global_assignment -name AUTO_RAM_RECOGNITION     "On"
set_global_assignment -name OPTIMIZE_POWER_DURING_SYNTHESIS "Off"

project_close

puts ""
puts "Setup complete: $project_name"
puts "Run 'quartus_sh -t build.tcl' to synthesize."