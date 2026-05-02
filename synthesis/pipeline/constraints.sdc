# Timing constraints for rv32im on DE1-SoC (Cyclone V 5CSEMA5F31C6)
#
# Both microarchitectures use identical constraints to satisfy the
# homogeneous measurement protocol. Do not modify one without the other.
#
# Target: 100 MHz (10 ns period). This is intentionally aggressive so that
# Quartus reports the true achievable Fmax after place-and-route rather than
# stopping at an artificially relaxed target.

# ---------------------------------------------------------------------------
# Primary clock
# DE1-SoC provides a 50 MHz oscillator on PIN_AF14. The PLL is not used
# in this project; the processor runs directly at 50 MHz or at the frequency
# derived from the clock port of the top-level module.
# TODO: update pin location if using a different clock source.
# ---------------------------------------------------------------------------
create_clock -period 10.000 -name clk [get_ports clk]

# ---------------------------------------------------------------------------
# Clock uncertainty
# Accounts for clock jitter on the Cyclone V device.
# ---------------------------------------------------------------------------
set_clock_uncertainty -rise_from [get_clocks clk] \
                      -rise_to   [get_clocks clk] 0.100
set_clock_uncertainty -fall_from [get_clocks clk] \
                      -fall_to   [get_clocks clk] 0.100

# ---------------------------------------------------------------------------
# Input and output delays
# Conservative estimates for FPGA-internal paths; adjust when interfacing
# with external components (switches, LEDs, HEX displays on DE1-SoC).
# ---------------------------------------------------------------------------
set_input_delay  -clock clk -max 2.000 [get_ports {rst}]
set_input_delay  -clock clk -min 0.500 [get_ports {rst}]

# ---------------------------------------------------------------------------
# False paths
# Asynchronous inputs that do not require timing analysis.
# ---------------------------------------------------------------------------
# set_false_path -from [get_ports {KEY[0]}]  ;# uncomment when reset is on KEY
