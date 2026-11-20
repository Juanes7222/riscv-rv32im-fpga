# Physical board clock. Both architectures share these constraints.
# Comparative characterization must use a separate diagnostic SDC, never
# change the physical oscillator frequency inferred by the PLLs.
create_clock -period 20.000 -name clk [get_ports clk]
derive_pll_clocks
set pixel_clock [get_clocks *u_vga_pll*divclk*]
if {[get_collection_size $pixel_clock] != 1} { error "Expected one pixel clock" }
create_generated_clock -name vga_dac_clock \
    -source [get_clock_info -targets $pixel_clock] \
    -divide_by 1 -invert [get_ports vga_clock]
# Use the device model's recommended setup/hold uncertainty, including
# rising-to-falling transfers in the single-cycle memory interface.
derive_clock_uncertainty

# The raw reset drives PLL reset and asynchronous assertion of reset chains.
# Local release is registered and remains timed inside each domain.
set_false_path -from [get_ports rst_n]
set root_resets [get_registers {*u_cpu_reset|release_ready *u_video_reset|release_ready}]
set capture_reset_stages [get_registers {*u_capture*u_source_reset|release_* *u_capture*u_destination_reset|release_*}]
set_false_path -from $root_resets -to $capture_reset_stages

# Mechanical inputs are asynchronous. Only the input-to-first-stage paths
# are excluded; the register-to-register synchronizer paths remain timed.
set_false_path -from [get_ports key_step] -to [get_registers {*u_step_mode|key_sync*}]
set_false_path -from [get_ports step_mode] -to [get_registers {*u_step_mode|sw_sync*}]
set_false_path -from [get_ports key_load] -to [get_registers {*u_loader|key_meta}]
set_false_path -from [get_ports {sw[*]}] -to [get_registers {*u_loader|selector_meta*}]

# Four-phase control crossings enter exactly one metastability stage.
set_false_path -from [get_registers {*u_capture|request}] \
               -to [get_registers {*u_capture|req_meta}]
set_false_path -from [get_registers {*u_capture|acknowledge}] \
               -to [get_registers {*u_capture|ack_meta}]

# The complete payload is held until acknowledgement returns. The request
# crosses two destination registers before capture, leaving over two pixel
# periods for data to settle. Bound all payload bits to 10 ns; the protocol
# supplies hold protection until after the destination capture.
set payload_source [get_registers {*u_capture|payload_hold*}]
set payload_destination [get_registers {*u_capture|data_out*}]
set_max_delay -from $payload_source -to $payload_destination 10.000
set_false_path -hold -from $payload_source -to $payload_destination

# LEDs and seven-segment displays have no receiving clock.
set_false_path -to [get_ports {ledr[*] seven_seg_display*}]
# ADV7123 Rev. D, Table 6 (3.3 V): setup 0.2 ns, hold 1.5 ns.
# PCB data-minus-clock skew is a design budget of +/-0.5 ns, not a measured
# board property. Setup: 0.2+0.5=0.7; minimum output delay: -(1.5+0.5)=-2.0.
# The forwarded, inverted clock includes the FPGA clock-output routing.
set dac_data [get_ports {vga_r[*] vga_g[*] vga_b[*] vga_blank_n}]
set_output_delay -clock vga_dac_clock -max 0.700 $dac_data
set_output_delay -clock vga_dac_clock -min -2.000 $dac_data

# H/V sync go to the monitor rather than the DAC's sampling registers.
# Their registered outputs must settle within one pixel period. Pulse
# durations and pixel alignment are verified by the video-interface test.
set monitor_sync [get_ports {vga_hsync vga_vsync}]
set_max_delay -to $monitor_sync [get_clock_info -period $pixel_clock]
set_min_delay -to $monitor_sync 0.000
