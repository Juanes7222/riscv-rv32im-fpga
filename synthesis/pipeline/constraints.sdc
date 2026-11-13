# Physical board clock. Both architectures share these constraints.
# Comparative characterization must use a separate diagnostic SDC, never
# change the physical oscillator frequency inferred by the PLLs.
create_clock -period 20.000 -name clk [get_ports clk]
derive_pll_clocks
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
# VGA pins retain their unconstrained status until the external interface
# budget is established from the board/DAC specification. Do not invent
# output delays or cut the video interface to obtain a clean summary.
