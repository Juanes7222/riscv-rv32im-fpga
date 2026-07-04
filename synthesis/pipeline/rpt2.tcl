load_package report
project_open rv32im_pipeline -current_revision
create_timing_netlist -model slow
read_sdc
update_timing_netlist
report_timing -to_clock clk -setup -npaths 5 -detail full_path -stdout -panel_name {Critical Paths}
# Also list worst 3 paths programmatically
set paths [get_timing_paths -to_clock clk -setup -nworst 3]
puts "\n=== Path Summary ==="
set i 1
foreach path $paths {
    set slack [get_path_info $path -slack]
    set src [get_node_info -name [get_path_info $path -from]]
    set dst [get_node_info -name [get_path_info $path -to]]
    puts "  Path $i: Slack=${slack}ns"
    puts "    From: $src"
    puts "    To:   $dst"
    incr i
}
project_close
