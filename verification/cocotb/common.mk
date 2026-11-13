# verification/cocotb/common.mk
#
# Shared Makefile fragment for cocotb-based RTL verification.
#
# Per-design Makefiles should include this at the end after setting:
#   TOPLEVEL, COCOTB_TEST_MODULES, VERILOG_SOURCES
# and optionally:
#   COCOTB_PYTHONPATH, PYTHONPATH

TOPLEVEL_LANG  = verilog
SIM            = icarus

REPO_ROOT    = $(shell git rev-parse --show-toplevel)
RTL_ROOT     = $(REPO_ROOT)/rtl
SCRIPTS_ROOT = $(REPO_ROOT)/scripts
BUILD_DIR    = $(REPO_ROOT)/build

# Simulation memory images.  They live in build/sim/ because the FPGA flow
# owns build/imem.mem and build/dmem.mem (generated at the synthesis depths).
# The paths are injected from the command line so the simulation never has to
# write rtl/shared/mem_config.vh, which belongs to the Quartus build.
SIM_MEM_DIR  = $(BUILD_DIR)/sim
SIM_IMEM     = $(SIM_MEM_DIR)/imem.mem
SIM_DMEM     = $(SIM_MEM_DIR)/dmem.mem
SIM_TEST_ELF = $(firstword $(wildcard $(BUILD_DIR)/riscv-tests/rv32ui/*.elf))

COMPILE_ARGS ?= -I$(RTL_ROOT)/shared
COMPILE_ARGS += -DIMEM_FILE=\"$(abspath $(SIM_IMEM))\"
COMPILE_ARGS += -DDMEM_FILE=\"$(abspath $(SIM_DMEM))\"
COMPILE_ARGS += -DFONT_ROM_FILE=\"$(abspath $(RTL_ROOT)/shared/vga_font_rom.hex)\"
# The simulated arrays must have the depth of the images and of the hardware
# configuration, so a run at DMEM_DEPTH=1024 really exercises 1024 words.
COMPILE_ARGS += -P$(TOPLEVEL).IMEM_DEPTH=$(IMEM_DEPTH)
COMPILE_ARGS += -P$(TOPLEVEL).DMEM_DEPTH=$(DMEM_DEPTH)
# The same tohost address the bitstream will carry.  Without it the simulation
# keeps the RTL default 0x708 and the frozen-counter path of a program that
# writes somewhere else is never exercised, which is how the parameter bug of
# ADR 051 reached the board.
ifneq ($(TOHOST_ADDR),)
COMPILE_ARGS += -P$(TOPLEVEL).TOHOST_ADDR=$(shell printf %d $(TOHOST_ADDR))
endif

# The waveform dump is off unless it is asked for: a long benchmark run
# writes gigabytes and becomes I/O bound.
ifneq ($(DUMP_VCD),1)
COMPILE_ARGS += -DNO_VCD
endif

SHARED_SRCS = \
    $(RTL_ROOT)/shared/register_file.sv \
    $(RTL_ROOT)/shared/alu_rv32im.sv \
    $(RTL_ROOT)/shared/branch_unit.sv \
    $(RTL_ROOT)/shared/imm_gen.sv \
    $(RTL_ROOT)/shared/perf_counter.sv \
    $(RTL_ROOT)/shared/step_mode_ctrl.sv \
    $(RTL_ROOT)/shared/seven_segment.sv \
    $(RTL_ROOT)/shared/csr_file.sv

SHARED_VGA_SRCS = \
    $(RTL_ROOT)/shared/reset_release_sync.sv \
    $(RTL_ROOT)/shared/debug_snapshot_cdc.sv \
    $(RTL_ROOT)/shared/vga_pll.sv \
    $(RTL_ROOT)/shared/cpu_pll.sv \
    $(RTL_ROOT)/shared/vga_text_mode.sv \
    $(RTL_ROOT)/shared/vga_controller.sv \
    $(RTL_ROOT)/shared/vga_font_rom.sv \
    $(RTL_ROOT)/shared/video_memory.sv \
    $(RTL_ROOT)/shared/vga_mem_shadow.sv \
    $(RTL_ROOT)/shared/vga_rom_shadow.sv

export REPO_ROOT
export SCRIPTS_ROOT
export BUILD_DIR
export RTL_SHARED  = $(RTL_ROOT)/shared
export IMEM_DEPTH  ?= 16384
export DMEM_DEPTH  ?= 8192

include $(shell cocotb-config --makefiles)/Makefile.sim

# The simulation images only need to exist when the simulator starts; each
# test regenerates them for the ELF it exercises.  The two memories have
# separate decoders, so each gets its own image (ADR 047).
$(SIM_IMEM): $(SIM_TEST_ELF)
	@mkdir -p $(SIM_MEM_DIR)
	python3 $(SCRIPTS_ROOT)/elf_to_mem_split.py $< \
		--imem-depth $(IMEM_DEPTH) --imem-out $(SIM_IMEM) \
		--dmem-depth $(DMEM_DEPTH) --dmem-out $(SIM_DMEM)

$(SIM_DMEM): $(SIM_TEST_ELF)
	@mkdir -p $(SIM_MEM_DIR)
	python3 $(SCRIPTS_ROOT)/elf_to_mem_split.py $< \
		--imem-depth $(IMEM_DEPTH) --imem-out $(SIM_IMEM) \
		--dmem-depth $(DMEM_DEPTH) --dmem-out $(SIM_DMEM)

$(SIM_BUILD)/sim.vvp: $(SIM_IMEM) $(SIM_DMEM)

.PHONY: simulation-config-force
simulation-config-force:

# Icarus output depends on parameters and defines as well as source mtimes.
$(SIM_BUILD)/compile_flags: simulation-config-force
	@mkdir -p $(SIM_BUILD)
	@echo '$(TOPLEVEL) $(COMPILE_ARGS)' > $@.tmp
	@cmp -s $@.tmp $@ || cp $@.tmp $@

$(SIM_BUILD)/sim.vvp: $(SIM_BUILD)/compile_flags
