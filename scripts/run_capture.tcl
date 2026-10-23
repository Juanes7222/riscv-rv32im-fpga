# Runs a SignalTap II capture and exports results to CSV.
#
# Usage:
#   quartus_stp -t scripts/run_capture.tcl <pipeline|single_cycle> [output_dir]
#
# Prerequisites:
#   1. The .sof must be compiled with SignalTap enabled and the .stp file
#      included in the project (use make build-fpga ARCH=<arch>).
#   2. The DE1-SoC must be connected via JTAG (USB Blaster).
#   3. The test program must be loaded into IMEM (make flash or the VGA console
#      will show stale data).
#
# The capture triggers on program_done_synced == 1 (the instant the benchmark
# writes to tohost) and exports cycle_count, instr_retired and
# program_done_synced to CSV.  With sample_depth=1K and trigger_position=1,
# the CSV contains the frozen counter values after the benchmark completes.

package require ::quartus::stp

# Resolve paths relative to this script's location
set script_dir [file dirname [info script]]
set repo_root   [file normalize [file join $script_dir ".."]]

if {$argc < 1} {
    puts "Usage: quartus_stp -t run_capture.tcl <pipeline|single_cycle> [output_dir]"
    exit 1
}

set arch       [lindex $argv 0]
if {[llength $argv] > 1} {
    set output_dir [lindex $argv 1]
} else {
    set output_dir [file join $repo_root "results"]
}

# Map architecture to project, top-level and instance names
if {$arch eq "pipeline"} {
    set project_name  "rv32im_pipeline"
    set top_level     "top_pipeline"
    set instance_name "perf_capture_pipeline"
    set stp_file      [file join $repo_root "stp" "perf_capture_pipeline.stp"]
} elseif {$arch eq "single_cycle"} {
    set project_name  "rv32im_single_cycle"
    set top_level     "top_single_cycle"
    set instance_name "perf_capture_sc"
    set stp_file      [file join $repo_root "stp" "perf_capture_sc.stp"]
} else {
    puts "Error: architecture must be 'pipeline' or 'single_cycle', got '$arch'"
    exit 1
}

set synthesis_dir [file join $repo_root "synthesis" $arch]
set sof_pattern   "${synthesis_dir}/output_files/${project_name}.sof"
set sofs          [glob -nocomplain $sof_pattern]

if {[llength $sofs] == 0} {
    puts "Error: no .sof found matching ${sof_pattern}"
    puts "Compile first with SignalTap: make build-fpga ARCH=${arch}"
    exit 1
}

# Use the most recent .sof
set sof [lindex [lsort -decreasing $sofs] 0]
puts "Using SOF: ${sof}"

# Ensure output directory exists
file mkdir $output_dir
set csv_file [file join $output_dir "capture_${arch}.csv"]

# ---------------------------------------------------------------------------
# Step 1: Program the FPGA via JTAG
# ---------------------------------------------------------------------------
# The DE1-SoC JTAG chain is USB-Blaster -> MAX10 -> Cyclone V, so the FPGA is
# device 2 in the chain.  Programming device 1 configures the MAX10 and fails.
puts ""
puts "Programming FPGA (device 2 in JTAG chain)..."
set pgm_cmd "quartus_pgm -c \"DE-SoC\" -m JTAG -o \"P;${sof}@2\""
puts "  ${pgm_cmd}"

if {[catch {exec {*}$pgm_cmd} pgm_result]} {
    puts "Warning: quartus_pgm failed: ${pgm_result}"
    puts "Check that the USB Blaster is connected and the DE1-SoC is powered on."
    puts "Continuing to STP capture anyway..."
} else {
    puts "Programming successful."
}

# ---------------------------------------------------------------------------
# Step 2: Open the SignalTap II session
# ---------------------------------------------------------------------------
puts ""
puts "Opening SignalTap II session..."
puts "  STP file: ${stp_file}"

if {![file exists $stp_file]} {
    puts "Error: no .stp file found at ${stp_file}"
    puts "Run 'quartus_sh -t scripts/create_stp.tcl ${arch}' first."
    exit 1
}

if {[catch {open_session -name $stp_file} open_result]} {
    puts "Error: failed to open STP session: ${open_result}"
    exit 1
}
puts "Session opened."

# ---------------------------------------------------------------------------
# Step 3: Run the capture
# ---------------------------------------------------------------------------
# `run` is blocking: it starts the acquisition, waits for the trigger
# (program_done_synced == 1) and returns when the capture buffer is full.
puts ""
puts "Starting SignalTap capture..."
puts "  Instance : ${instance_name}"
puts "  Trigger  : ${top_level}|u_perf|program_done_synced == 1"
puts "  Output   : ${csv_file}"
puts "  Waiting for benchmark to write to tohost..."

if {[catch {run -instance $instance_name} run_result]} {
    puts "Error: capture run failed: ${run_result}"
    close_session
    exit 1
}
puts "Capture complete."

# ---------------------------------------------------------------------------
# Step 4: Export captured data to CSV
# ---------------------------------------------------------------------------
puts "Exporting to CSV: ${csv_file}"

if {[catch {export_data_log -instance $instance_name -format CSV -output_file $csv_file} export_result]} {
    puts "Error: failed to export: ${export_result}"
    close_session
    exit 1
}
puts "Export successful."

# ---------------------------------------------------------------------------
# Step 5: Close session
# ---------------------------------------------------------------------------
close_session
puts "Session closed."

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
puts ""
puts "=== Capture Summary ==="
puts "  Architecture: ${arch}"
puts "  SOF:          ${sof}"
puts "  Output:       ${csv_file}"
puts ""
puts "Next step: parse the CSV with:"
puts "  python3 scripts/parse_stp_csv.py ${csv_file} --output-dir ${output_dir}"
puts ""

exit 0
