# Runs a SignalTap II capture and exports results to CSV.
# Usage: quartus_stp -t run_capture.tcl <pipeline|single_cycle> [output_dir]
#
# Prerequisites:
#   1. The .sof must be compiled with SignalTap enabled and the .stp file
#      included in the project (use build_fpga.tcl).
#   2. The DE1-SoC must be connected via JTAG (USB Blaster).
#   3. The test program must be loaded into IMEM.
#
# All paths are resolved relative to this script's directory.

package require ::quartus::stp

# Resolve paths relative to this script's location
set script_dir [file dirname [info script]]
set repo_root   [file normalize [file join $script_dir ".."]]

if {$argc < 1} {
    puts "Usage: quartus_stp -t run_capture.tcl <pipeline|single_cycle> \[output_dir\]"
    exit 1
}

set arch       [lindex $argv 0]
set output_dir [lindex $argv 1 [file join $repo_root "results"]]

# Locate the .sof file: search synthesis/<arch>/output_files/
set synthesis_dir [file join $repo_root "synthesis" $arch]
set sof_pattern  "${synthesis_dir}/output_files/rv32im_${arch}*.sof"
set sofs [glob -nocomplain $sof_pattern]

if {[llength $sofs] == 0} {
    puts "Error: no .sof found matching ${sof_pattern}"
    puts "Compile first with SignalTap: quartus_sh -t scripts/build_fpga.tcl ${arch}"
    exit 1
}

# Use the most recent .sof
set sof [lindex [lsort -decreasing $sofs] 0]
puts "Using: ${sof}"

# Ensure output directory exists
file mkdir $output_dir
set csv_file [file join $output_dir "capture_${arch}.csv"]

# ---------------------------------------------------------------------------
# Step 1: Program the FPGA via JTAG
# ---------------------------------------------------------------------------
puts ""
puts "Programming FPGA..."
puts "  quartus_pgm -c 1 -m jtag -o p;${sof}"

if {[catch {exec quartus_pgm -c 1 -m jtag -o "p;${sof}"} prog_result]} {
    puts "Warning: quartus_pgm failed: ${prog_result}"
    puts "Check that the USB Blaster is connected and the DE1-SoC is powered on."
    puts "Continuing to STP capture anyway..."
} else {
    puts "Programming successful."
}

# ---------------------------------------------------------------------------
# Step 2: Find and open the SignalTap .stp file
# ---------------------------------------------------------------------------
puts ""
puts "Opening SignalTap II via JTAG..."

set stp_file [file join $repo_root "stp" "perf_capture_${arch}.stp"]

if {![file exists $stp_file]} {
    puts "Error: no .stp file found at ${stp_file}"
    puts "Run 'quartus_sh -t scripts/create_stp.tcl ${arch}' first,"
    puts "or create the .stp file manually in the SignalTap II GUI."
    exit 1
}

puts "Using STP: ${stp_file}"

# Open STP file
if {[catch {stp_open -file $stp_file} open_result]} {
    puts "Error: failed to open STP file: ${open_result}"
    exit 1
}

# ---------------------------------------------------------------------------
# Step 3: Run the capture and wait for trigger
# ---------------------------------------------------------------------------
set instance_name "perf_capture_${arch}"
puts ""
puts "Starting STP run..."
puts "  Instance: ${instance_name}"
puts "  Trigger:  program_done_synced == 1"
puts "  Output:   ${csv_file}"
puts "  Waiting for benchmark to complete..."

# Run the capture (non-blocking)
stp_run -instance $instance_name

# Poll for trigger status (timeout after 10 seconds)
set timeout_ms 10000
set poll_interval_ms 100
set elapsed_ms 0
set triggered 0

while {$elapsed_ms < $timeout_ms} {
    after $poll_interval_ms
    set elapsed_ms [expr {$elapsed_ms + $poll_interval_ms}]

    set status [stp_get_status -instance $instance_name]

    # Status values: "Running", "Triggered", "Stopped", "Idle"
    if {[string match "*Triggered*" $status] || [string match "*Stopped*" $status]} {
        set triggered 1
        break
    }

    puts -nonewline "."
    flush stdout
}

puts ""

if {!$triggered} {
    puts "Warning: trigger not received within ${timeout_ms}ms."
    puts "  Possible causes:"
    puts "  - Test program did not write to tohost (TOHOST_ADDR mismatch?)"
    puts "  - Processor is stuck in reset (KEY[0] released?)"
    puts "  - Clock not running"
    puts "  - SignalTap instance name mismatch (expected: ${instance_name})"
    puts "  Exporting available data..."
}

# ---------------------------------------------------------------------------
# Step 4: Export captured data to CSV
# ---------------------------------------------------------------------------
puts ""
puts "Exporting to CSV: ${csv_file}"

if {[catch {stp_export -instance $instance_name -file $csv_file -format CSV} export_result]} {
    puts "Error: failed to export: ${export_result}"
    stp_close
    exit 1
}

puts "Export successful."

# Close STP connection
stp_close

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
puts "  python scripts/parse_stp_csv.py ${csv_file} --output-dir ${output_dir}"
puts ""

exit 0
