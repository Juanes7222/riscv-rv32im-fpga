# Usage: quartus_sta -t report_physical_timing.tcl <project-dir> <report-dir>
# This reads a fitted project; it never compiles or programs the FPGA.
if {$argc != 2} { error "Expected absolute project and report directories" }
set project_directory [lindex $argv 0]
set report_directory [lindex $argv 1]
cd $project_directory
set projects [glob -nocomplain *.qpf]
if {[llength $projects] != 1} { error "Expected exactly one Quartus project" }
project_open [file rootname [lindex $projects 0]] -current_revision
file mkdir $report_directory
create_timing_netlist -model slow -temperature 85 -voltage 1100
read_sdc
update_timing_netlist
set dac_ports [get_ports {vga_r[*] vga_g[*] vga_b[*] vga_blank_n}]
set sync_ports [get_ports {vga_hsync vga_vsync}]
if {[get_collection_size $dac_ports] != 25} { error "Expected 25 DAC data/control ports" }
if {[get_collection_size $sync_ports] != 2} { error "Expected two monitor sync ports" }
set dac_clock [get_clocks vga_dac_clock]
if {[get_collection_size $dac_clock] != 1} { error "Missing forwarded DAC clock" }
report_clocks -file [file join $report_directory clocks.rpt]
report_sdc -ignored -file [file join $report_directory constraints.rpt]
report_ucp -file [file join $report_directory unconstrained.rpt]
report_metastability -nchains 30 -file [file join $report_directory metastability.rpt]
report_clock_transfers -file [file join $report_directory transfers.rpt]

set summary [open [file join $report_directory summary.tsv] w]
puts $summary "corner\tanalysis\tresult"
foreach model {slow fast} {
    foreach temperature {85 0} {
        set_operating_conditions -model $model -temperature $temperature -voltage 1100
        update_timing_netlist
        set corner "${model}_${temperature}C"
        foreach analysis {setup hold recovery removal} {
            set result [report_timing -$analysis -npaths 10 -detail full_path \
                -file [file join $report_directory "${corner}_${analysis}.rpt"]]
            puts $summary "$corner\t$analysis\t$result"
        }
        set result [report_timing -setup \
            -from [get_registers {*u_capture|payload_hold*}] \
            -to [get_registers {*u_capture|data_out*}] \
            -npaths 10 -detail full_path \
            -file [file join $report_directory "${corner}_payload.rpt"]]
        puts $summary "$corner\tpayload_setup\t$result"
        foreach analysis {setup hold} {
            set result [report_timing -$analysis -to $dac_ports \
                -npaths 50 -detail full_path \
                -file [file join $report_directory "${corner}_dac_${analysis}.rpt"]]
            puts $summary "$corner\tdac_$analysis\t$result"
            set result [report_timing -$analysis -to $sync_ports \
                -npaths 10 -detail full_path \
                -file [file join $report_directory "${corner}_sync_${analysis}.rpt"]]
            puts $summary "$corner\tsync_$analysis\t$result"
        }
        set result [report_min_pulse_width -nworst 10 \
            -file [file join $report_directory "${corner}_pulse_width.rpt"]]
        puts $summary "$corner\tpulse_width\t$result"
    }
}
close $summary
delete_timing_netlist
project_close
puts "PHYSICAL_TIMING_REPORT_COMPLETE"
