load_package report

project_open rv32im_pipeline -current_revision

read_sdc
update_timing_netlist

set paths [get_timing_paths -clock_filter {clk} -npaths 10 -setup]

puts "=== Top 10 Worst Paths on clk ==="
set i 1
foreach path $paths {
    set slack [get_path_info $path -slack]
    set src [get_path_info $path -from]
    set dst [get_path_info $path -to]
    puts "Path $i: slack=${slack}ns"
    puts "  From: $src"
    puts "  To:   $dst"
    incr i
}

project_close
