# Compiles with SignalTap II enabled for FPGA validation.
# Usage: quartus_sh -t scripts/build_fpga.tcl <pipeline|single_cycle> [seed]
#
# Adds SignalTap II to the compilation, runs full compile,
# then removes the SignalTap assignments to keep the .qsf clean
# (they are not needed for replica runs or normal development).
#
# All paths are resolved relative to this script's directory.

load_package flow

# Resolve paths relative to this script's location
set script_dir [file dirname [info script]]
set repo_root   [file normalize [file join $script_dir ".."]]

if {$argc < 1} {
    puts "Usage: quartus_sh -t build_fpga.tcl <pipeline|single_cycle> \[seed\]"
    exit 1
}

set arch [lindex $argv 0]

if {$arch eq "pipeline"} {
    set project_dir [file join $repo_root "synthesis" "pipeline"]
    set project_name "rv32im_pipeline"
    set stp_file    [file join $repo_root "stp" "perf_capture_pipeline.stp"]
} elseif {$arch eq "single_cycle"} {
    set project_dir [file join $repo_root "synthesis" "single_cycle"]
    set project_name "rv32im_single_cycle"
    set stp_file    [file join $repo_root "stp" "perf_capture_sc.stp"]
} else {
    puts "Error: architecture must be 'pipeline' or 'single_cycle', got '$arch'"
    exit 1
}

# Change to project directory so .qpf is found
cd $project_dir

# Check that the .stp file exists
if {![file exists $stp_file]} {
    puts "Error: SignalTap II file not found: $stp_file"
    puts "Run 'quartus_sh -t scripts/create_stp.tcl ${arch}' first to generate it,"
    puts "or create stp/perf_capture_${arch}.stp manually in the SignalTap II GUI."
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
puts "Next step: quartus_stp -t scripts/run_capture.tcl ${arch}"
puts ""

exit 0
