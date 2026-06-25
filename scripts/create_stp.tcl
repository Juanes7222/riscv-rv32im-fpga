# Creates a SignalTap II .stp file for the given architecture.
# Usage: quartus_sh -t scripts/create_stp.tcl <pipeline|single_cycle>
#
# Run this after the first compilation (without SignalTap) to generate
# the .stp file. Then run 'make build-fpga' to compile with SignalTap.
#
# If this script fails, open SignalTap II GUI, add the three signals
# (u_perf|cycle_count, u_perf|instr_retired, u_perf|program_done_synced)
# manually, configure trigger on program_done_synced == 1, save as
# stp/perf_capture_<arch>.stp, and run build-fpga.
#
# All paths are resolved relative to this script's directory.

load_package ::quartus::stp

# Resolve paths relative to this script's location
set script_dir [file dirname [info script]]
set repo_root   [file normalize [file join $script_dir ".."]]
set stp_dir     [file join $repo_root "stp"]

if {$argc < 1} {
    puts "Usage: quartus_sh -t scripts/create_stp.tcl <pipeline|single_cycle>"
    exit 1
}

set arch [lindex $argv 0]

# Map architecture to top-level entity name
if {$arch eq "pipeline"} {
    set top      "top_pipeline"
    set stp_file [file join $stp_dir "perf_capture_pipeline.stp"]
} elseif {$arch eq "single_cycle"} {
    set top      "top_single_cycle"
    set stp_file [file join $stp_dir "perf_capture_sc.stp"]
} else {
    puts "Error: architecture must be 'pipeline' or 'single_cycle', got '$arch'"
    exit 1
}

# Ensure stp/ directory exists
file mkdir $stp_dir

puts "Creating SignalTap II configuration for ${arch}..."
puts "  Top-level: ${top}"
puts "  STP file:  ${stp_file}"

# ---------------------------------------------------------------------------
# Create STP file with stp_new / stp_add_instance / stp_add_signal.
#
# The TCL API for ::quartus::stp varies between Quartus versions.
# If this block fails, create the .stp file manually via the SignalTap GUI
# with the settings described below.
# ---------------------------------------------------------------------------

# Create or overwrite the STP file
stp_new -file $stp_file

# Add a tap instance
#   - clock: clk (50 MHz system clock)
#   - fifo_size: 1K (minimum for single-capture-on-done)
#   - trigger_position: 1 (capture 1 sample after trigger)
set inst_id [stp_add_instance \
    -name "perf_capture_${arch}" \
    -clock "clk" \
    -fifo_size "1K" \
    -trigger_position 1]

# Add signals to tap.  The hierarchical name must match the compiled design.
stp_add_signal \
    -instance $inst_id \
    -name "${top}|u_perf|cycle_count" \
    -width 64

stp_add_signal \
    -instance $inst_id \
    -name "${top}|u_perf|instr_retired" \
    -width 64

stp_add_signal \
    -instance $inst_id \
    -name "${top}|u_perf|program_done_synced" \
    -width 1

# Set trigger condition: capture when program_done_synced == 1
stp_set_trigger \
    -instance $inst_id \
    -enable 1 \
    -equation "program_done_synced == 1"

# Save the STP file
stp_save

puts ""
puts "Created: ${stp_file}"
puts ""
puts "Next steps:"
puts "  1. Compile with SignalTap:    make build-fpga ARCH=${arch}"
puts "  2. Program FPGA:              make program ARCH=${arch}"
puts "  3. Run capture:               make capture ARCH=${arch}"
puts "  4. Cross-validate:            make cross-validate ARCH=${arch} COCOTB_CSV=<path>"
puts ""

exit 0
