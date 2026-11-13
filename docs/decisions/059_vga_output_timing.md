# ADR 059 - Registered VGA interface and forwarded sampling clock

Status: Accepted; simulated and checked on fitted candidate netlists.
Date: 2026-11-13.
Supersedes only the pending VGA interface budget in ADR 058.

## Context

The reset/CDC candidates left 28 output ports unconstrained: 24 RGB bits,
BLANK, the forwarded clock and horizontal/vertical sync. RGB came from a
combinational colour mux; blanking and sync used undelayed scan counters.
The ADV7123 samples RGB and BLANK on the rising edge of its clock. Sending
the same positive-edge pixel clock did not establish a half-cycle sampling
window or align blanking with the renderer's two-cycle memory pipeline.

## Decision

`vga_output_stage` registers RGB on the positive pixel edge and delays raw
blanking and sync by three registers: two renderer cycles plus the new RGB
register. It forwards the inverted pixel clock, placing the DAC's rising
sampling edge half a period after the RGB update. Reset clears RGB and all
three control pipelines. Both processor tops use this same stage.

Both SDC files create `vga_dac_clock` at the physical clock output, derived
from and inverted relative to the pixel PLL output. The clock-output routing
therefore participates in the DAC setup and hold reports. No VGA data path
is declared false.

The ADV7123 Rev. D, Table 6 specifies 0.2 ns setup and 1.5 ns hold at 3.3 V.
Use an explicit design budget of +/-0.5 ns for external data-minus-clock
delay. This budget is an assumption, not a measurement of DE1-SoC traces:

- Maximum output delay: 0.2 + 0.5 = 0.7 ns.
- Minimum output delay: -(1.5 + 0.5) = -2.0 ns.

Apply these delays to the 25 RGB/BLANK ports. H/V sync connect directly to
the monitor, so their registered output paths receive a separate maximum
delay of one pixel period and minimum delay of zero. These are output
latency bounds, not fictitious DAC setup/hold requirements. The constant
`vga_sync_n` requires no toggling-data check.

## Validation and limits

`make verify-timing` includes a full 1650 x 750 scan with the real controller,
font ROM and renderer. A synchronous character source changes colour across
cell boundaries; the test checks RGB/control alignment, all active pixels,
sync widths, opposite clock phase, RTL setup/hold intervals and reset.
RTL intervals are functional checks; fitted timing provides physical FPGA
delay estimates. Both architectures were compiled at seed 5 and analysed
with slow/fast models at 0/85 C and 1100 mV. Each corner reports all 25 DAC
and both sync endpoints, with positive margins and no unconstrained I/O.

The result is conditional on the external skew budget and Quartus I/O model.
No PCB extraction, receiver-load characterization, oscilloscope capture or
new on-board run was performed. The nominal forwarded half-period is about
6.734 ns; the DAC's external high/low pulse widths and signal integrity still
need board validation. The device pulse-width report covers FPGA checks,
not an independently imposed ADV7123 pin pulse-width requirement.

These post-campaign candidates do not replace the thesis's frozen replicas
or their measured performance. See [the validation report](../vga_output_timing_2026-11-13.md).

## Primary references

- [ADV7123 datasheet, Rev. D](https://www.analog.com/media/en/technical-documentation/data-sheets/adv7123.pdf), Table 6 and pin descriptions.
- `hardware/DE1-SoC_User_manual_revf.pdf`, section 3.6.6, Figure 3-22 and Table 3-16.
- [Terasic DE1-SoC schematic, revision F](https://people.ece.cornell.edu/land/courses/ece5760/DE1_SOC/DE1-SoC%20schematic.pdf), VGA sheet 16.
