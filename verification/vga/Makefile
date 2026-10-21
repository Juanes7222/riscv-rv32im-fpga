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

PALETTE_TB  := tb_vga_palette
PALETTE_RTL := ../../rtl/shared/vga_text_mode.sv \
               ../../rtl/shared/vga_font_rom.sv

HL_TB := tb_stage_highlight

PIPE_HL_TB  := tb_pipeline_stage_highlight
PIPE_HL_RTL := ../../rtl/pipeline/screen_writer_pipeline.sv

TABLE_TB  := tb_vga_table
TABLE_RTL := ../../rtl/pipeline/screen_writer_pipeline.sv \
             ../../rtl/single_cycle/screen_writer_sc.sv

PANEL_TB  := tb_vga_panel
PANEL_RTL := ../../rtl/pipeline/screen_writer_pipeline.sv \
             ../../rtl/single_cycle/screen_writer_sc.sv

# The shadow memories include ../shared/mem_config.vh, so the include path
# of the shared directory is needed.  MEM_CONFIG_VH switches the memory
# images off: the shadow tests start from an empty memory and need none.
SHADOW_INC   := -I../../rtl/shared
SHADOW_NOIMG := -DMEM_CONFIG_VH

SHADOW_TB  := tb_vga_shadow
SHADOW_RTL := ../../rtl/shared/vga_mem_shadow.sv

MIRROR_TB  := tb_vga_shadow_mirror
MIRROR_RTL := ../../rtl/shared/vga_mem_shadow.sv \
              ../../rtl/single_cycle/data_memory.sv

ROM_TB  := tb_vga_rom_shadow
ROM_RTL := ../../rtl/shared/vga_rom_shadow.sv
ROM_IMG := ../../build/vga_rom_shadow.mem

all: run

run: run-step run-palette run-highlight run-shadow run-rom run-table run-panel
	$(SIM) -g2012 -o $(TB).vvp $(TB).sv $(RTL)
	$(VVP) $(TB).vvp

run-step:
	$(SIM) -g2012 -o $(STEP_TB).vvp $(STEP_TB).sv $(STEP_RTL)
	$(VVP) $(STEP_TB).vvp

run-palette:
	$(SIM) -g2012 -o $(PALETTE_TB).vvp $(PALETTE_TB).sv $(PALETTE_RTL)
	$(VVP) $(PALETTE_TB).vvp

run-highlight:
	$(SIM) -g2012 -o $(HL_TB).vvp $(HL_TB).sv $(RTL)
	$(VVP) $(HL_TB).vvp
	$(SIM) -g2012 -o $(PIPE_HL_TB).vvp $(PIPE_HL_TB).sv $(PIPE_HL_RTL)
	$(VVP) $(PIPE_HL_TB).vvp

run-shadow:
	$(SIM) -g2012 $(SHADOW_NOIMG) $(SHADOW_INC) -o $(SHADOW_TB).vvp $(SHADOW_TB).sv $(SHADOW_RTL)
	$(VVP) $(SHADOW_TB).vvp
	$(SIM) -g2012 $(SHADOW_NOIMG) $(SHADOW_INC) -o $(MIRROR_TB).vvp $(MIRROR_TB).sv $(MIRROR_RTL)
	$(VVP) $(MIRROR_TB).vvp

run-rom: $(ROM_IMG)
	$(SIM) -g2012 $(SHADOW_INC) -DIMEM_FILE=\"$(abspath $(ROM_IMG))\" -o $(ROM_TB).vvp $(ROM_TB).sv $(ROM_RTL)
	$(VVP) $(ROM_TB).vvp

run-table:
	$(SIM) -g2012 -o $(TABLE_TB).vvp $(TABLE_TB).sv $(TABLE_RTL)
	$(VVP) $(TABLE_TB).vvp

run-panel:
	$(SIM) -g2012 -o $(PANEL_TB).vvp $(PANEL_TB).sv $(PANEL_RTL)
	$(VVP) $(PANEL_TB).vvp

$(ROM_IMG):
	@mkdir -p $(dir $@)
	@printf 'AABBCCDD\n11223344\n55667788\n99AABBCC\n' > $@

clean:
	rm -f $(TB).vvp $(STEP_TB).vvp $(PALETTE_TB).vvp $(HL_TB).vvp \
	      $(PIPE_HL_TB).vvp $(SHADOW_TB).vvp $(MIRROR_TB).vvp $(ROM_TB).vvp \
	      $(TABLE_TB).vvp $(PANEL_TB).vvp

.PHONY: all run run-step run-palette run-highlight run-shadow run-rom \
	run-table run-panel clean
