load_package report
project_open rv32im_single_cycle -current_revision
load_report
set panel_name "Fitter||Resource Section||Resource Usage Summary"
set panel_id [get_report_panel_id $panel_name]
if {$panel_id != -1} {
    set lines [get_report_panel_data $panel_id]
    puts "=== Single-cycle Resource Usage ==="
    foreach line $lines {
        puts $line
    }
}
unload_report
project_close
