# Regression tests for the VGA console and for the step mode.
SIM ?= iverilog
VVP ?= vvp

TB  := tb_screen_writer_snapshot
RTL := ../../rtl/single_cycle/screen_writer_sc.sv

STEP_TB  := tb_step_mode
STEP_RTL := ../../rtl/shared/step_mode_ctrl.sv \
            ../../rtl/shared/perf_counter.sv \
            ../../rtl/single_cycle/pc.sv \
            ../../rtl/pipeline/pc_unit.sv \
            ../../rtl/pipeline/if_id_register.sv

all: run

run: run-step
	$(SIM) -g2012 -o $(TB).vvp $(TB).sv $(RTL)
	$(VVP) $(TB).vvp

run-step:
	$(SIM) -g2012 -o $(STEP_TB).vvp $(STEP_TB).sv $(STEP_RTL)
	$(VVP) $(STEP_TB).vvp

clean:
	rm -f $(TB).vvp $(STEP_TB).vvp

.PHONY: all run run-step clean
