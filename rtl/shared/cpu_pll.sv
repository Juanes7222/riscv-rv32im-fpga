// CPU clock PLL - 40 MHz from the 50 MHz board oscillator (PIN_AF14).
//
// The single-cycle processor keeps CPI = 1 with a 4 KB M10K data memory whose
// read address is captured on the falling edge (ADR 048).  Its critical path
// is the multiply writeback (ADR 050), which measures 48.48 MHz at 85 C
// (replica mean 49.10 MHz) in results/results_report.md; the 46.17 MHz of an
// earlier run is kept only as a historical figure.  It cannot run from
// CLOCK_50 like the pipeline, so it runs from this 40 MHz output, which leaves
// about 17 % of margin on that path (ADR 049).
//
// Configuration: F_out = F_in x multiply_by / divide_by = 50 x 24 / 30 = 40 MHz
// with VCO = 50 x 24 / 1 = 1200 MHz (within 600-1600 MHz).
//
// The simulation model passes the input clock straight through: simulation
// verifies behaviour and counts CPU cycles, which do not depend on the clock
// period, and every testbench then drives one clock instead of two.

module cpu_pll (
    input  logic clk_in,     // 50 MHz from CLOCK_50 (PIN_AF14)
    input  logic rst_in,     // Active-high synchronous reset
    output logic clk_out,    // 40 MHz processor clock
    output logic locked      // PLL lock indicator (1 = locked)
);

// synthesis translate_off
`define SIMULATION
// synthesis translate_on

`ifdef SIMULATION

    assign clk_out = clk_in;
    assign locked  = 1'b1;

`else

    logic [1:0]  pll_inclk;
    logic [4:0]  pll_clk;
    logic        pll_locked;
    logic        pll_areset;

    assign pll_inclk  = {1'b0, clk_in};
    assign pll_areset = rst_in;
    assign clk_out    = pll_clk[0];
    assign locked     = pll_locked;

    altpll #(
        .bandwidth_type             ("AUTO"),
        .clk0_divide_by             (30),
        .clk0_duty_cycle            (50),
        .clk0_multiply_by           (24),
        .clk0_phase_shift           ("0"),
        .compensate_clock           ("CLK0"),
        .inclk0_input_frequency     (20000),    // 20000 ps = 50 MHz
        .intended_device_family     ("Cyclone V"),
        .lpm_hint                   ("CBX_MODULE_PREFIX=cpu_pll"),
        .lpm_type                   ("altpll"),
        .operation_mode             ("NORMAL"),
        .pll_type                   ("AUTO"),
        .port_activeclock           ("PORT_UNUSED"),
        .port_areset                ("PORT_USED"),
        .port_clkbad0               ("PORT_UNUSED"),
        .port_clkbad1               ("PORT_UNUSED"),
        .port_clkloss               ("PORT_UNUSED"),
        .port_clkswitch             ("PORT_UNUSED"),
        .port_configupdate          ("PORT_UNUSED"),
        .port_fbin                  ("PORT_UNUSED"),
        .port_inclk0                ("PORT_USED"),
        .port_inclk1                ("PORT_UNUSED"),
        .port_locked                ("PORT_USED"),
        .port_pfdena                ("PORT_UNUSED"),
        .port_phasecounterselect    ("PORT_UNUSED"),
        .port_phasedone             ("PORT_UNUSED"),
        .port_phasestep             ("PORT_UNUSED"),
        .port_phaseupdown           ("PORT_UNUSED"),
        .port_pllena                ("PORT_UNUSED"),
        .port_scanaclr              ("PORT_UNUSED"),
        .port_scanclk               ("PORT_UNUSED"),
        .port_scanclkena            ("PORT_UNUSED"),
        .port_scandata              ("PORT_UNUSED"),
        .port_scandataout           ("PORT_UNUSED"),
        .port_scandone              ("PORT_UNUSED"),
        .port_scanread              ("PORT_UNUSED"),
        .port_scanwrite             ("PORT_UNUSED"),
        .port_clk0                  ("PORT_USED"),
        .port_clk1                  ("PORT_UNUSED"),
        .port_clk2                  ("PORT_UNUSED"),
        .port_clk3                  ("PORT_UNUSED"),
        .port_clk4                  ("PORT_UNUSED"),
        .port_clk5                  ("PORT_UNUSED"),
        .port_clkena0               ("PORT_UNUSED"),
        .port_clkena1               ("PORT_UNUSED"),
        .port_clkena2               ("PORT_UNUSED"),
        .port_clkena3               ("PORT_UNUSED"),
        .port_clkena4               ("PORT_UNUSED"),
        .port_clkena5               ("PORT_UNUSED"),
        .port_extclk0               ("PORT_UNUSED"),
        .port_extclk1               ("PORT_UNUSED"),
        .port_extclk2               ("PORT_UNUSED"),
        .port_extclk3               ("PORT_UNUSED"),
        .self_reset_on_loss_lock    ("OFF"),
        .width_clock                (5)
    ) u_altpll (
        .inclk      (pll_inclk),
        .clk        (pll_clk),
        .areset     (pll_areset),
        .locked     (pll_locked),
        .activeclock(),
        .clkbad     (),
        .clkena     ({6{1'b1}}),
        .clkloss    (),
        .clkswitch  (1'b0),
        .configupdate(1'b0),
        .enable0    (),
        .enable1    (),
        .extclk     (),
        .extclkena  ({4{1'b1}}),
        .fbin       (1'b0),
        .fbmimicbidir(),
        .fbout      (),
        .fref       (),
        .icdrclk    (),
        .pfdena     (1'b1),
        .phasecounterselect(4'b0001),
        .phasedone  (),
        .phasestep  (1'b0),
        .phaseupdown(1'b0),
        .pllena     (1'b1),
        .scanaclr   (1'b0),
        .scanclk    (1'b0),
        .scanclkena (1'b1),
        .scandata   (1'b0),
        .scandataout(),
        .scandone   (),
        .scanread   (1'b0),
        .scanwrite  (1'b0),
        .sclkout0   (),
        .sclkout1   (),
        .vcooverrange(),
        .vcounderrange()
    );

`endif
endmodule
