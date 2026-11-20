# Usage: quartus_sta -t report_vga_sensitivity.tcl <project-dir> <report-dir>
# Re-analyse a fixed placement; never export the hypothetical board loads.
if {$argc != 2} { error "Expected project and report directories" }
set project_directory [lindex $argv 0]
set report_directory [lindex $argv 1]
file mkdir $report_directory
cd $project_directory
set projects [glob -nocomplain *.qpf]
if {[llength $projects] != 1} { error "Expected exactly one Quartus project" }
set project_name [file rootname [lindex $projects 0]]
set data_names {vga_blank_n}
foreach channel {r g b} {
    for {set bit 0} {$bit < 8} {incr bit} {
        lappend data_names [format {vga_%s[%d]} $channel $bit]
    }
}
set scenarios {{project project project} {c10_c10 10 10} {c10_c20 10 20}
               {c20_c10 20 10} {c20_c20 20 20}}
set skews {0.0 0.5 1.0 2.0 2.5 3.0}
set results [open [file join $report_directory sensitivity.csv] w]
puts $results "scenario,data_load_pf,clock_load_pf,skew_ns,model,temperature_c,setup_paths,setup_slack_ns,hold_paths,hold_slack_ns"
set baseline [open [file join $report_directory baseline.csv] w]
puts $baseline "model,temperature_c,analysis,paths,slack_ns"
puts "SENSITIVITY_TOOL $::quartus(version)"
try {
    foreach scenario $scenarios {
        lassign $scenario label data_load clock_load
        project_open $project_name -current_revision
        if {$label ne "project"} {
            # Far capacitance is specified in farads; 'p' denotes picofarads.
            # OUTPUT_PIN_LOAD is ignored by the Cyclone V timing model.
            foreach port $data_names {
                set_instance_assignment -name BOARD_MODEL_FAR_C ${data_load}p -to $port
            }
            set_instance_assignment -name BOARD_MODEL_FAR_C ${clock_load}p -to vga_clock
        }
        create_timing_netlist -force_dat -model slow -temperature 85 -voltage 1100
        read_sdc
        update_timing_netlist
        set dac_ports [get_ports {vga_r[*] vga_g[*] vga_b[*] vga_blank_n}]
        if {[get_collection_size $dac_ports] != 25} { error "Expected 25 DAC ports" }
        if {[get_collection_size [get_clocks vga_dac_clock]] != 1} {
            error "Missing forwarded DAC clock"
        }
        if {$label eq "project"} {
            report_clocks -file [file join $report_directory clocks.rpt]
            report_sdc -ignored -file [file join $report_directory ignored.rpt]
            report_ucp -file [file join $report_directory unconstrained.rpt]
            set config [open [file join $report_directory board_model.txt] w]
            foreach name {BOARD_MODEL_FAR_C BOARD_MODEL_NEAR_C BOARD_MODEL_TLINE_L
                          BOARD_MODEL_TLINE_C BOARD_MODEL_TLINE_R
                          OUTPUT_IO_TIMING_ENDPOINT OUTPUT_PIN_LOAD} {
                set assignments [get_all_instance_assignments -name $name]
                puts $config "$name: [get_collection_size $assignments] explicit assignments"
                foreach_in_collection assignment $assignments {
                    puts $config "  [lindex $assignment 2] = [lindex $assignment 4]"
                }
            }
            puts $config "Unassigned fields use device/project defaults; they are not measured PCB parameters."
            close $config
        }
        foreach model {slow fast} {
            foreach temperature {85 0} {
                set_operating_conditions -model $model -temperature $temperature -voltage 1100
                foreach skew $skews {
                    remove_output_delay $dac_ports
                    set_output_delay -clock vga_dac_clock -max [expr {0.2 + $skew}] $dac_ports
                    set_output_delay -clock vga_dac_clock -min [expr {-(1.5 + $skew)}] $dac_ports
                    update_timing_netlist
                    set prefix "${label}_${model}_${temperature}C_skew${skew}"
                    set detail summary
                    if {$skew == 0.5} { set detail full_path }
                    set setup [report_timing -setup -to $dac_ports -npaths 25 -nworst 1 \
                        -detail $detail -file [file join $report_directory "${prefix}_setup.rpt"]]
                    set hold [report_timing -hold -to $dac_ports -npaths 25 -nworst 1 \
                        -detail $detail -file [file join $report_directory "${prefix}_hold.rpt"]]
                    puts $results "$label,$data_load,$clock_load,$skew,$model,$temperature,[join $setup ,],[join $hold ,]"
                    if {$label eq "project" && $skew == 0.5} {
                        foreach analysis {setup hold recovery removal} {
                            set result [report_timing -$analysis -npaths 10 -detail full_path \
                                -file [file join $report_directory "baseline_${model}_${temperature}C_${analysis}.rpt"]]
                            puts $baseline "$model,$temperature,$analysis,[join $result ,]"
                        }
                        set result [report_min_pulse_width -nworst 10 \
                            -file [file join $report_directory "baseline_${model}_${temperature}C_pulse.rpt"]]
                        puts $baseline "$model,$temperature,pulse_width,[join $result ,]"
                    }
                }
            }
        }
        delete_timing_netlist
        project_close -dont_export_assignments
    }
} finally {
    close $results
    close $baseline
    if {[timing_netlist_exist]} { delete_timing_netlist }
    if {[is_project_open]} { project_close -dont_export_assignments }
    # Restore nominal delay annotation so later reports cannot reuse a load
    # scenario's cached delays with the original project configuration.
    project_open $project_name -current_revision
    create_timing_netlist -force_dat -model slow -temperature 85 -voltage 1100
    delete_timing_netlist
    project_close -dont_export_assignments
}
puts "VGA_SENSITIVITY_COMPLETE"
