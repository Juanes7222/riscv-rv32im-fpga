# Regression test for the VGA screen writer snapshot bank.
SIM ?= iverilog
VVP ?= vvp
TB  := tb_screen_writer_snapshot
RTL := ../../rtl/single_cycle/screen_writer_sc.sv

all: run

run:
	$(SIM) -g2012 -o $(TB).vvp $(TB).sv $(RTL)
	$(VVP) $(TB).vvp

clean:
	rm -f $(TB).vvp

.PHONY: all run clean
