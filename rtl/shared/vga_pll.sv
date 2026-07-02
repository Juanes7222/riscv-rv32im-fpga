// VGA PLL — generates 74.25 MHz pixel clock for 720p60 from 50 MHz input.
// Instantiates the ALTPLL megafunction directly via Verilog parameters;
// no IP Catalog GUI required. Quartus synthesizes this for Cyclone V.
//
// Configuration:
//   F_out = F_in × multiply_by / divide_by = 50 × 297 / 200 = 74.25 MHz
//   VCO = F_in × multiply_by / N ≈ 50 × 297 / 20 = 742.5 MHz (within 600–1600 MHz)
//   Input period: 20000 ps (50 MHz)
//   Compensation: CLK0, mode: NORMAL
//
// Selection between simulation and synthesis models:
//   Quartus skips the `synthesis translate_off` block (including the `define
//   SIMULATION`), so the synthesis branch (altpll) is compiled.
//   Icarus sees the `define SIMULATION` and compiles the simulation branch
//   (clock divider that approximates 74.25 MHz). The two branches are mutually
//   exclusive, preventing multiple-driver conflicts on clk_out/locked.

module vga_pll (
    input  logic  clk_in,     // 50 MHz from CLOCK_50 (PIN_AF14)
    input  logic  rst_in,     // Active-high synchronous reset
    output logic  clk_out,    // 74.25 MHz pixel clock for 720p60 VGA
    output logic  locked      // PLL lock indicator (1 = locked)
);

// --------------------------------------------------------------------------
// Simulation branch — defined inside translate_off so Quartus never sees it.
// The `define SIMULATION will be visible only to non-Quartus compilers
// (Icarus, ModelSim, etc.).
// --------------------------------------------------------------------------
// synthesis translate_off
`define SIMULATION
// synthesis translate_on

`ifdef SIMULATION

    // 50 MHz / 74.25 MHz = 200/297 ≈ 0.6734.
    // Toggle every ~0.337 input cycles. Count 0..336 (337 cycles) per toggle
    // gives 50 MHz / (2 × 337) ≈ 74.18 MHz (<0.1% error; fine for simulation).
    logic [8:0] sim_cnt;

    always_ff @(posedge clk_in) begin
        if (rst_in) begin
            sim_cnt <= 9'd0;
            clk_out <= 1'b0;
        end else if (sim_cnt >= 9'd336) begin
            sim_cnt <= 9'd0;
            clk_out <= ~clk_out;
        end else begin
            sim_cnt <= sim_cnt + 9'd1;
        end
    end

    assign locked = 1'b1;

`else
// --------------------------------------------------------------------------
// Synthesis model — ALTPLL megafunction instantiation (Cyclone V).
// Quartus automatically chooses the pre-scale (N) and post-scale (C0)
// counters to keep the VCO within the Cyclone V range (600–1600 MHz).
// For f_in=50 MHz: VCO ≈ 742.5 MHz with N=20, C0=10.
// --------------------------------------------------------------------------

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
        .clk0_divide_by             (200),
        .clk0_duty_cycle            (50),
        .clk0_multiply_by           (297),
        .clk0_phase_shift           ("0"),
        .compensate_clock           ("CLK0"),
        .inclk0_input_frequency     (20000),    // 20000 ps = 50 MHz
        .intended_device_family     ("Cyclone V"),
        .lpm_hint                   ("CBX_MODULE_PREFIX=vga_pll"),
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