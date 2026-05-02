# Run once with: quartus_sh -t setup.tcl
# After running, use build.tcl for all subsequent compilations.

load_package flow

# Project configuration
set project_name    "rv32im_single_cycle"
set device          "5CSEMA5F31C6"
set family          "Cyclone V"
set top_level       "top_single_cycle"  

# Paths relative to this script's location (synthesis/single_cycle/)
set rtl_shared      "../../rtl/shared"
set rtl_arch        "../../rtl/single_cycle"
set constraints_sdc "constraints.sdc"

# Guard: abort if project already exists
if {[file exists "$project_name.qpf"]} {
    puts "Project $project_name already exists. Delete .qpf and .qsf to re-run setup."
    exit 0
}

# Create project
project_new $project_name

set_global_assignment -name FAMILY          $family
set_global_assignment -name DEVICE          $device
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


# Use all available CPU cores for faster compilation
set_global_assignment -name NUM_PARALLEL_PROCESSORS ALL

# Balanced optimization: area and speed trade-off appropriate for comparison
set_global_assignment -name OPTIMIZATION_MODE "Balanced"

# Let Quartus infer DSP blocks for multipliers (required for M extension)
set_global_assignment -name DSP_BLOCK_BALANCING "Auto"

# Ensure M10K inference for memories; RTL should use ramstyle attribute
# but this setting reinforces automatic inference
set_global_assignment -name AUTO_RAM_RECOGNITION "On"

# Power optimization off to avoid affecting timing comparison
set_global_assignment -name OPTIMIZE_POWER_DURING_SYNTHESIS "Off"

# ---------------------------------------------------------------------------
# Pin assignments for DE1-SoC
# Clock input on KEY[0] is not used here; pin assignments go in a separate
# .qsf fragment when the physical pinout is finalized.
# ---------------------------------------------------------------------------

project_close

puts ""
puts "Setup complete: $project_name"
puts "Run 'quartus_sh -t build.tcl' to synthesize."